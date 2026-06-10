"""Blender add-on for semi-automatic PMX/MMD to XPS bone renaming.

The add-on combines learned mappings from previous manual renames with
rule-based fallback logic for common humanoid, clothing, hair, and accessory
bones. It is intended to be run after PMX import and optional CATS cleanup.
"""

bl_info = {
    "name": "PMX to XPS Bone Renamer",
    "author": "Codex",
    "version": (0, 1, 0),
    "blender": (2, 79, 0),
    "location": "View3D > Tool Shelf/Sidebar > XPS Rename",
    "description": "Semi-automatic PMX/MMD bone renaming helper for XPS/XNALara workflows.",
    "category": "Rigging",
}

import json
import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

import bpy
from bpy.props import BoolProperty, FloatProperty, PointerProperty, StringProperty
from bpy.types import Operator, Panel, PropertyGroup


CORE_KEYWORDS = {
    "root_ground": ["全ての親", "全親", "root", "all parent", "motherbone", "mother bone"],
    "center": ["センター", "center", "centre"],
    "pelvis": ["下半身", "腰", "pelvis", "hip", "hips"],
    "spine": ["上半身", "spine", "body"],
    "chest": ["上半身2", "胸", "chest", "upper body", "upperbody"],
    "neck": ["首", "neck"],
    "head": ["頭", "head"],
    "shoulder": ["肩", "shoulder"],
    "upper_arm": ["腕", "うで", "upperarm", "upper arm", "arm"],
    "elbow": ["ひじ", "肘", "elbow", "forearm"],
    "wrist": ["手首", "wrist", "hand"],
    "thigh": ["足", "太もも", "thigh", "leg"],
    "knee": ["ひざ", "膝", "knee"],
    "ankle": ["足首", "ankle", "foot"],
    "toe": ["つま先", "toe"],
    "eye": ["目", "eye"],
    "jaw": ["あご", "顎", "jaw"],
}

FINGER_KEYWORDS = {
    "thumb": ["親指", "thumb"],
    "index": ["人指", "人差", "index", "indexfinger"],
    "middle": ["中指", "middle", "middlefinger"],
    "ring": ["薬指", "ring", "ringfinger"],
    "pinky": ["小指", "pinky", "little", "littlefinger"],
}

SECONDARY_KEYWORDS = {
    "hair": ["髪", "毛", "hair", "bang", "kami"],
    "skirt": ["スカート", "skirt"],
    "sleeve": ["袖", "sode", "sleeve"],
    "coat": ["coat", "jacket", "mantle"],
    "belt": ["belt"],
    "ribbon": ["リボン", "ribbon", "bow"],
    "headband": ["headband"],
    "hairpin": ["hairpin", "pin"],
    "hairtie": ["hairtie", "hair tie"],
    "tail": ["尻尾", "尾", "tail"],
    "ears": ["耳", "ear", "ears"],
    "wing": ["羽", "翼", "wing"],
    "cloth": ["服", "布", "cloth", "cape", "dress", "breast", "shirt", "collar"],
    "trousers": ["trousers", "pants"],
    "pendant": ["pendant"],
    "stripe": ["stripe", "strip"],
    "tie": ["tie"],
    "spring": ["spring"],
    "chain": ["chain"],
    "rope": ["rope"],
    "ring": ["ring"],
    "ornament": ["ornament"],
    "accessory": ["飾", "アクセ", "accessory", "acc", "hat", "cap", "glasses", "key", "tag"],
    "weapon": ["剣", "刀", "銃", "weapon", "sword", "gun"],
    "physics": ["物理", "physics", "jiggle"],
}

LEFT_TOKENS = ["左", "左側", "_l", ".l", "-l", " l ", "left"]
RIGHT_TOKENS = ["右", "右側", "_r", ".r", "-r", " r ", "right"]

TWIST_TOKENS = ["捩", "twist", "回転", "roll"]
IK_TOKENS = ["ik", "ＩＫ"]

LEARNED_MAP_CACHE = None


RenameResult = Tuple[str, float, str]
RenamePlanRow = Dict[str, Any]
LearnedEntry = Dict[str, Any]
LearnedMap = Dict[str, Dict[str, LearnedEntry]]


def clean_text(value: str) -> str:
    """Normalizes text for case-insensitive keyword matching.

    Args:
        value: Raw bone name or keyword.

    Returns:
        A lower-case string with full-width spaces and repeated whitespace
        normalized.
    """
    value = value.replace("　", " ").strip().lower()
    value = re.sub(r"\s+", " ", value)
    return value


def contains_any(name: str, tokens: List[str]) -> bool:
    """Checks whether a name contains any token after normalization.

    Args:
        name: Bone name to inspect.
        tokens: Candidate keywords to search for.

    Returns:
        True when at least one normalized token appears in the normalized name.
    """
    lowered = clean_text(" " + name + " ")
    return any(clean_text(token) in lowered for token in tokens)


def side_from_name(name: str) -> str:
    """Infers left/right side from a bone name.

    Args:
        name: Bone name to inspect.

    Returns:
        ``"left"``, ``"right"``, or an empty string when no side token is
        found.
    """
    if contains_any(name, LEFT_TOKENS):
        return "left"
    if contains_any(name, RIGHT_TOKENS):
        return "right"
    return ""


def side_from_position(bone: Any) -> str:
    """Infers left/right side from a Blender bone's X position.

    Args:
        bone: Blender armature bone-like object with ``head_local``.

    Returns:
        ``"left"``, ``"right"``, or an empty string when the side cannot be
        inferred.
    """
    try:
        x = bone.head_local.x
    except AttributeError:
        return ""
    if x > 0.001:
        return "left"
    if x < -0.001:
        return "right"
    return ""


def number_suffix(name: str) -> Optional[int]:
    """Extracts a trailing integer suffix from a bone name.

    Args:
        name: Bone name to inspect.

    Returns:
        The trailing integer, or None when the name does not end in digits.
    """
    match = re.search(r"(\d+)$", name)
    if match:
        return int(match.group(1))
    return None


def letter_suffix(name: str) -> str:
    """Converts a finger segment number to an XPS-style letter suffix.

    Args:
        name: Bone name that may contain a finger segment number.

    Returns:
        A leading-space suffix such as ``" a"`` or an empty string when no
        known segment is found.
    """
    match = re.search(r"(?:finger)?([0-3])(?:_|$)", clean_text(name))
    if not match:
        match = re.search(r"([0-3])$", clean_text(name))
    if not match:
        return ""
    return {"0": " a", "1": " b", "2": " c", "3": " d"}.get(match.group(1), "")


def side_label(side: str) -> str:
    """Formats a side string for insertion into an XPS bone name.

    Args:
        side: Side value, usually ``"left"``, ``"right"``, or empty.

    Returns:
        A space-prefixed side label or an empty string.
    """
    return (" " + side) if side else ""


def category_match(name: str, table: Dict[str, List[str]]) -> str:
    """Finds the first category whose keywords match a bone name.

    Args:
        name: Bone name to classify.
        table: Mapping of category name to keyword list.

    Returns:
        Matching category name, or an empty string when no category matches.
    """
    for category, tokens in table.items():
        if contains_any(name, tokens):
            return category
    return ""


def load_learned_map() -> LearnedMap:
    """Loads learned name mappings from ``learned_name_map.json``.

    Returns:
        A mapping with ``exact`` and ``lower`` lookup dictionaries. If the file
        is missing or invalid, both dictionaries are empty.
    """
    global LEARNED_MAP_CACHE
    if LEARNED_MAP_CACHE is not None:
        return LEARNED_MAP_CACHE

    LEARNED_MAP_CACHE = {"exact": {}, "lower": {}}
    try:
        map_path = Path(__file__).with_name("learned_name_map.json")
        if not map_path.exists():
            return LEARNED_MAP_CACHE
        payload = json.loads(map_path.read_text(encoding="utf-8"))
        for source, entry in payload.get("learned", {}).items():
            target = entry.get("target", "").strip()
            if not target:
                continue
            confidence = float(entry.get("confidence", 1.0))
            count = int(entry.get("count", 1))
            learned_entry = {
                "target": target,
                "confidence": min(0.99, max(0.88, 0.90 + confidence * 0.08 + min(count, 5) * 0.002)),
                "reason": "learned from name_reference (%d/%d)" % (count, int(entry.get("total", count))),
            }
            LEARNED_MAP_CACHE["exact"][source] = learned_entry
            LEARNED_MAP_CACHE["lower"][clean_text(source)] = learned_entry
    except Exception:
        LEARNED_MAP_CACHE = {"exact": {}, "lower": {}}
    return LEARNED_MAP_CACHE


def classify_learned(name: str) -> Optional[RenameResult]:
    """Classifies a bone using the learned exact-name mapping.

    Args:
        name: Source bone name after CATS or PMX import.

    Returns:
        A rename result tuple ``(target_name, confidence, reason)`` or None
        when the name is not present in the learned map.
    """
    learned_map = load_learned_map()
    entry = learned_map["exact"].get(name) or learned_map["lower"].get(clean_text(name))
    if not entry:
        return None
    return (entry["target"], entry["confidence"], entry["reason"])


def classify_core(name: str, bone: Any) -> Optional[RenameResult]:
    """Classifies common humanoid bones with XPS-style names.

    Args:
        name: Source bone name.
        bone: Blender bone used for optional side inference.

    Returns:
        A rename result tuple or None when no core humanoid rule matches.
    """
    original_name = name
    side = side_from_name(name) or side_from_position(bone)
    lower_name = clean_text(name)

    if contains_any(name, IK_TOKENS):
        return None

    if contains_any(name, TWIST_TOKENS):
        if contains_any(name, CORE_KEYWORDS["upper_arm"]):
            return ("arm%s elbow ctr" % side_label(side), 0.82 if side else 0.68, "arm twist")
        if contains_any(name, CORE_KEYWORDS["wrist"]):
            return ("arm%s wrist ctr" % side_label(side), 0.82 if side else 0.68, "wrist twist")
        if contains_any(name, CORE_KEYWORDS["thigh"]):
            return ("leg%s knee ctr" % side_label(side), 0.76 if side else 0.64, "leg twist")

    if contains_any(name, CORE_KEYWORDS["root_ground"]):
        return ("root ground", 0.95, "root keyword")
    if contains_any(name, CORE_KEYWORDS["center"]):
        return ("root hips", 0.90, "center keyword")
    if contains_any(name, CORE_KEYWORDS["pelvis"]):
        return ("pelvis", 0.92, "pelvis keyword")

    if contains_any(name, CORE_KEYWORDS["chest"]):
        return ("spine upper", 0.88, "chest keyword")
    if contains_any(name, CORE_KEYWORDS["spine"]):
        if "upperbody1" in lower_name or "upper body1" in lower_name:
            return ("spine middle", 0.90, "upper body 1 keyword")
        if "2" in lower_name or "upper" in lower_name:
            return ("spine upper", 0.86, "upper spine keyword")
        return ("spine lower", 0.84, "spine keyword")
    if contains_any(name, CORE_KEYWORDS["neck"]):
        return ("head neck lower", 0.92, "neck keyword")
    if contains_any(name, CORE_KEYWORDS["head"]):
        return ("head neck upper", 0.92, "head keyword")

    if contains_any(name, CORE_KEYWORDS["shoulder"]):
        return ("arm%s shoulder" % side_label(side), 0.90 if side else 0.72, "shoulder keyword")
    if contains_any(name, CORE_KEYWORDS["elbow"]):
        return ("arm%s elbow" % side_label(side), 0.92 if side else 0.72, "elbow keyword")
    if contains_any(name, CORE_KEYWORDS["wrist"]):
        return ("arm%s wrist" % side_label(side), 0.90 if side else 0.72, "wrist keyword")

    finger = category_match(name, FINGER_KEYWORDS)
    if finger:
        segment = letter_suffix(original_name)
        return ("arm%s finger %s%s" % (side_label(side), finger, segment), 0.86 if side else 0.68, "finger keyword")

    if contains_any(name, CORE_KEYWORDS["upper_arm"]):
        return ("arm%s arm" % side_label(side), 0.84 if side else 0.62, "arm keyword")
    if contains_any(name, CORE_KEYWORDS["knee"]):
        return ("leg%s knee" % side_label(side), 0.92 if side else 0.72, "knee keyword")
    if contains_any(name, CORE_KEYWORDS["ankle"]):
        return ("leg%s ankle" % side_label(side), 0.88 if side else 0.70, "ankle keyword")
    if contains_any(name, CORE_KEYWORDS["toe"]):
        return ("leg%s toe" % side_label(side), 0.88 if side else 0.70, "toe keyword")
    if contains_any(name, CORE_KEYWORDS["thigh"]):
        return ("leg%s thigh" % side_label(side), 0.80 if side else 0.58, "leg keyword")

    if contains_any(name, CORE_KEYWORDS["eye"]):
        return ("head eyeball%s" % side_label(side), 0.88 if side else 0.70, "eye keyword")
    if contains_any(name, CORE_KEYWORDS["jaw"]):
        return ("jaw", 0.82, "jaw keyword")

    return None


def classify_secondary(name: str, bone: Any) -> Optional[RenameResult]:
    """Classifies non-core bones such as hair, skirt, sleeve, or accessories.

    Args:
        name: Source bone name.
        bone: Blender bone used for optional side inference.

    Returns:
        A rename result tuple or None when no secondary category matches.
    """
    category = category_match(name, SECONDARY_KEYWORDS)
    if not category:
        return None

    side = side_from_name(name) or side_from_position(bone)
    suffix = number_suffix(name)
    suffix_text = (" %d" % suffix) if suffix is not None else ""
    return ("%s%s%s" % (category, side_label(side), suffix_text), 0.62, category + " keyword")


def unique_name(base_name: str, used_names: Set[str]) -> str:
    """Ensures a proposed bone name is unique within the rename plan.

    Args:
        base_name: Proposed target bone name.
        used_names: Names already reserved by the current plan.

    Returns:
        The original name when available, otherwise a numbered variant.
    """
    candidate = base_name.strip() or "misc bone"
    if candidate not in used_names:
        used_names.add(candidate)
        return candidate

    index = 2
    while True:
        candidate = "%s %02d" % (base_name, index)
        if candidate not in used_names:
            used_names.add(candidate)
            return candidate
        index += 1


def build_rename_plan(armature: Any, settings: Any) -> List[RenamePlanRow]:
    """Builds the full proposed rename plan for an armature.

    Args:
        armature: Selected Blender armature object.
        settings: Add-on settings from ``context.scene.xps_bone_renamer``.

    Returns:
        List of rows containing old name, new name, confidence, reason, and
        classification kind.
    """
    bones = list(armature.data.bones)
    used_names = set()
    plan = []

    for bone in bones:
        result = classify_learned(bone.name)
        kind = "learned"
        if not result:
            result = classify_core(bone.name, bone)
            kind = "core"
        if not result and settings.rename_secondary:
            result = classify_secondary(bone.name, bone)
            kind = "secondary"
        if not result and settings.rename_unknown:
            result = ("%s %s" % (settings.unknown_prefix.strip() or "misc", bone.name), 0.30, "fallback")
            kind = "unknown"

        if result:
            new_name, confidence, reason = result
            new_name = unique_name(new_name, used_names)
        else:
            new_name = bone.name
            confidence = 0.0
            reason = "unchanged"
            kind = "unchanged"
            used_names.add(new_name)

        plan.append({
            "old": bone.name,
            "new": new_name,
            "confidence": confidence,
            "reason": reason,
            "kind": kind,
        })

    return plan


def selected_armature(context: Any) -> Optional[Any]:
    """Returns the selected armature object from a Blender context.

    Args:
        context: Blender operator or panel context.

    Returns:
        The selected armature object, or None when the active object is not an
        armature.
    """
    obj = context.object
    if obj and obj.type == "ARMATURE":
        return obj
    return None


def write_preview_text(plan: List[RenamePlanRow], settings: Any) -> Any:
    """Writes the rename preview into a Blender text block.

    Args:
        plan: Rename plan rows produced by ``build_rename_plan``.
        settings: Add-on settings containing ``min_confidence``.

    Returns:
        The Blender text block containing the preview report.
    """
    text = bpy.data.texts.get("XPS Bone Rename Preview")
    if text is None:
        text = bpy.data.texts.new("XPS Bone Rename Preview")
    text.clear()
    text.write("PMX to XPS Bone Rename Preview\n")
    text.write("Minimum confidence for apply: %.2f\n\n" % settings.min_confidence)
    for row in plan:
        marker = "APPLY" if row["confidence"] >= settings.min_confidence and row["old"] != row["new"] else "SKIP "
        text.write(
            "%s | %.2f | %-9s | %s -> %s | %s\n"
            % (marker, row["confidence"], row["kind"], row["old"], row["new"], row["reason"])
        )
    return text


def rename_vertex_groups(armature: Any, old_name: str, new_name: str) -> None:
    """Renames mesh vertex groups that correspond to a renamed armature bone.

    Args:
        armature: Armature whose driven meshes should be inspected.
        old_name: Existing bone and vertex group name.
        new_name: Replacement bone and vertex group name.

    Returns:
        None.
    """
    for obj in bpy.data.objects:
        if obj.type != "MESH":
            continue
        has_armature = False
        if obj.parent == armature:
            has_armature = True
        for modifier in obj.modifiers:
            if modifier.type == "ARMATURE" and modifier.object == armature:
                has_armature = True
                break
        if not has_armature:
            continue
        group = obj.vertex_groups.get(old_name)
        if group:
            group.name = new_name


class XPSBoneRenamerSettings(PropertyGroup):
    """Scene-level settings used by the PMX to XPS bone renamer panel."""

    min_confidence = FloatProperty(
        name="Min Confidence",
        description="Only apply rename rows with confidence at or above this value",
        default=0.75,
        min=0.0,
        max=1.0,
    )
    rename_secondary = BoolProperty(
        name="Group Secondary Bones",
        description="Rename hair, skirt, sleeve, ribbon, tail, wing, cloth, accessory and weapon bones by category",
        default=True,
    )
    rename_unknown = BoolProperty(
        name="Prefix Unknown Bones",
        description="Prefix unclassified bones instead of leaving them unchanged",
        default=False,
    )
    unknown_prefix = StringProperty(
        name="Unknown Prefix",
        description="Prefix used when Prefix Unknown Bones is enabled",
        default="misc",
    )


class XPS_OT_preview_bone_rename(Operator):
    """Blender operator that writes a preview of proposed bone renames."""

    bl_idname = "xps.preview_bone_rename"
    bl_label = "Preview Rename"
    bl_description = "Create a text report showing the proposed bone renames"
    bl_options = {"REGISTER"}

    def execute(self, context: Any) -> Set[str]:
        """Creates a preview text block for the selected armature.

        Args:
            context: Blender operator context.

        Returns:
            Blender operator status set.
        """
        armature = selected_armature(context)
        if armature is None:
            self.report({"ERROR"}, "Select an armature first.")
            return {"CANCELLED"}

        settings = context.scene.xps_bone_renamer
        plan = build_rename_plan(armature, settings)
        text = write_preview_text(plan, settings)
        self.report({"INFO"}, "Preview written to text block: %s" % text.name)
        return {"FINISHED"}


class XPS_OT_apply_bone_rename(Operator):
    """Blender operator that applies high-confidence bone renames."""

    bl_idname = "xps.apply_bone_rename"
    bl_label = "Apply Rename"
    bl_description = "Rename bones and matching vertex groups using the preview rules"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context: Any) -> Set[str]:
        """Renames selected armature bones and matching vertex groups.

        Args:
            context: Blender operator context.

        Returns:
            Blender operator status set.
        """
        armature = selected_armature(context)
        if armature is None:
            self.report({"ERROR"}, "Select an armature first.")
            return {"CANCELLED"}

        settings = context.scene.xps_bone_renamer
        plan = build_rename_plan(armature, settings)
        write_preview_text(plan, settings)

        renamed = 0
        for row in plan:
            if row["confidence"] < settings.min_confidence:
                continue
            if row["old"] == row["new"]:
                continue
            bone = armature.data.bones.get(row["old"])
            if bone is None:
                continue
            rename_vertex_groups(armature, row["old"], row["new"])
            bone.name = row["new"]
            renamed += 1

        self.report({"INFO"}, "Renamed %d bones. Preview text was updated." % renamed)
        return {"FINISHED"}


class XPS_PT_bone_renamer(Panel):
    """Sidebar/tool-shelf panel for previewing and applying rename plans."""

    bl_label = "PMX to XPS Bone Renamer"
    bl_idname = "XPS_PT_bone_renamer"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI" if bpy.app.version >= (2, 80, 0) else "TOOLS"
    bl_category = "XPS Rename"

    def draw(self, context: Any) -> None:
        """Draws the add-on user interface.

        Args:
            context: Blender panel context.

        Returns:
            None.
        """
        layout = self.layout
        settings = context.scene.xps_bone_renamer

        layout.prop(settings, "min_confidence")
        layout.prop(settings, "rename_secondary")
        layout.prop(settings, "rename_unknown")
        if settings.rename_unknown:
            layout.prop(settings, "unknown_prefix")

        layout.separator()
        layout.operator("xps.preview_bone_rename", icon="TEXT")
        layout.operator("xps.apply_bone_rename", icon="ARMATURE_DATA")


classes = (
    XPSBoneRenamerSettings,
    XPS_OT_preview_bone_rename,
    XPS_OT_apply_bone_rename,
    XPS_PT_bone_renamer,
)


def register() -> None:
    """Registers Blender classes and scene properties.

    Returns:
        None.
    """
    for cls in classes:
        bpy.utils.register_class(cls)
    bpy.types.Scene.xps_bone_renamer = PointerProperty(type=XPSBoneRenamerSettings)


def unregister() -> None:
    """Unregisters Blender classes and scene properties.

    Returns:
        None.
    """
    del bpy.types.Scene.xps_bone_renamer
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)


if __name__ == "__main__":
    register()
