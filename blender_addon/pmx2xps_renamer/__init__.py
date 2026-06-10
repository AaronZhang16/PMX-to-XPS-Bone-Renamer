bl_info = {
    "name": "PMX to XPS Bone Renamer",
    "author": "Codex",
    "version": (0, 1, 0),
    "blender": (2, 79, 0),
    "location": "View3D > Tool Shelf/Sidebar > XPS Rename",
    "description": "Semi-automatic PMX/MMD bone renaming helper for XPS/XNALara workflows.",
    "category": "Rigging",
}

import re

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
    "index": ["人指", "人差", "index"],
    "middle": ["中指", "middle"],
    "ring": ["薬指", "ring"],
    "pinky": ["小指", "pinky", "little"],
}

SECONDARY_KEYWORDS = {
    "hair": ["髪", "毛", "hair", "bang", "kami"],
    "skirt": ["スカート", "skirt"],
    "sleeve": ["袖", "sode", "sleeve"],
    "ribbon": ["リボン", "ribbon", "bow"],
    "tail": ["尻尾", "尾", "tail"],
    "wing": ["羽", "翼", "wing"],
    "cloth": ["服", "布", "cloth", "coat", "cape", "dress"],
    "accessory": ["飾", "アクセ", "accessory", "acc", "hat", "cap", "glasses"],
    "weapon": ["剣", "刀", "銃", "weapon", "sword", "gun"],
    "physics": ["物理", "physics", "jiggle"],
}

LEFT_TOKENS = ["左", "左側", "_l", ".l", "-l", " l ", "left"]
RIGHT_TOKENS = ["右", "右側", "_r", ".r", "-r", " r ", "right"]

TWIST_TOKENS = ["捩", "twist", "回転", "roll"]
IK_TOKENS = ["ik", "ＩＫ"]


def clean_text(value):
    value = value.replace("　", " ").strip().lower()
    value = re.sub(r"\s+", " ", value)
    return value


def contains_any(name, tokens):
    lowered = clean_text(" " + name + " ")
    return any(clean_text(token) in lowered for token in tokens)


def side_from_name(name):
    if contains_any(name, LEFT_TOKENS):
        return "left"
    if contains_any(name, RIGHT_TOKENS):
        return "right"
    return ""


def side_from_position(bone):
    try:
        x = bone.head_local.x
    except AttributeError:
        return ""
    if x > 0.001:
        return "left"
    if x < -0.001:
        return "right"
    return ""


def number_suffix(name):
    match = re.search(r"(\d+)$", name)
    if match:
        return int(match.group(1))
    return None


def side_label(side):
    return (" " + side) if side else ""


def category_match(name, table):
    for category, tokens in table.items():
        if contains_any(name, tokens):
            return category
    return ""


def classify_core(name, bone):
    original_name = name
    side = side_from_name(name) or side_from_position(bone)
    lower_name = clean_text(name)

    if contains_any(name, IK_TOKENS):
        return None

    if contains_any(name, TWIST_TOKENS):
        if contains_any(name, CORE_KEYWORDS["upper_arm"]):
            return ("arm%s twist" % side_label(side), 0.70, "arm twist")
        if contains_any(name, CORE_KEYWORDS["thigh"]):
            return ("leg%s twist" % side_label(side), 0.70, "leg twist")

    if contains_any(name, CORE_KEYWORDS["root_ground"]):
        return ("root ground", 0.95, "root keyword")
    if contains_any(name, CORE_KEYWORDS["center"]):
        return ("root hips", 0.90, "center keyword")
    if contains_any(name, CORE_KEYWORDS["pelvis"]):
        return ("pelvis", 0.92, "pelvis keyword")

    if contains_any(name, CORE_KEYWORDS["chest"]):
        return ("spine upper", 0.88, "chest keyword")
    if contains_any(name, CORE_KEYWORDS["spine"]):
        if "2" in lower_name or "upper" in lower_name:
            return ("spine upper", 0.86, "upper spine keyword")
        return ("spine lower", 0.84, "spine keyword")
    if contains_any(name, CORE_KEYWORDS["neck"]):
        return ("neck", 0.92, "neck keyword")
    if contains_any(name, CORE_KEYWORDS["head"]):
        return ("head", 0.92, "head keyword")

    if contains_any(name, CORE_KEYWORDS["shoulder"]):
        return ("shoulder%s" % side_label(side), 0.90 if side else 0.72, "shoulder keyword")
    if contains_any(name, CORE_KEYWORDS["elbow"]):
        return ("arm%s elbow" % side_label(side), 0.92 if side else 0.72, "elbow keyword")
    if contains_any(name, CORE_KEYWORDS["wrist"]):
        return ("arm%s wrist" % side_label(side), 0.90 if side else 0.72, "wrist keyword")

    finger = category_match(name, FINGER_KEYWORDS)
    if finger:
        suffix = number_suffix(original_name)
        segment = (" %02d" % suffix) if suffix is not None else ""
        return ("finger%s %s%s" % (side_label(side), finger, segment), 0.82 if side else 0.68, "finger keyword")

    if contains_any(name, CORE_KEYWORDS["upper_arm"]):
        return ("arm%s shoulder" % side_label(side), 0.84 if side else 0.62, "arm keyword")
    if contains_any(name, CORE_KEYWORDS["knee"]):
        return ("leg%s knee" % side_label(side), 0.92 if side else 0.72, "knee keyword")
    if contains_any(name, CORE_KEYWORDS["ankle"]):
        return ("leg%s ankle" % side_label(side), 0.88 if side else 0.70, "ankle keyword")
    if contains_any(name, CORE_KEYWORDS["toe"]):
        return ("leg%s toe" % side_label(side), 0.88 if side else 0.70, "toe keyword")
    if contains_any(name, CORE_KEYWORDS["thigh"]):
        return ("leg%s thigh" % side_label(side), 0.80 if side else 0.58, "leg keyword")

    if contains_any(name, CORE_KEYWORDS["eye"]):
        return ("eye%s" % side_label(side), 0.86 if side else 0.70, "eye keyword")
    if contains_any(name, CORE_KEYWORDS["jaw"]):
        return ("jaw", 0.82, "jaw keyword")

    return None


def classify_secondary(name, bone):
    category = category_match(name, SECONDARY_KEYWORDS)
    if not category:
        return None

    side = side_from_name(name) or side_from_position(bone)
    suffix = number_suffix(name)
    suffix_text = (" %02d" % suffix) if suffix is not None else ""
    return ("%s%s%s" % (category, side_label(side), suffix_text), 0.62, category + " keyword")


def unique_name(base_name, used_names):
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


def build_rename_plan(armature, settings):
    bones = list(armature.data.bones)
    used_names = set()
    plan = []

    for bone in bones:
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


def selected_armature(context):
    obj = context.object
    if obj and obj.type == "ARMATURE":
        return obj
    return None


def write_preview_text(plan, settings):
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


def rename_vertex_groups(armature, old_name, new_name):
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
    bl_idname = "xps.preview_bone_rename"
    bl_label = "Preview Rename"
    bl_description = "Create a text report showing the proposed bone renames"
    bl_options = {"REGISTER"}

    def execute(self, context):
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
    bl_idname = "xps.apply_bone_rename"
    bl_label = "Apply Rename"
    bl_description = "Rename bones and matching vertex groups using the preview rules"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
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
    bl_label = "PMX to XPS Bone Renamer"
    bl_idname = "XPS_PT_bone_renamer"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI" if bpy.app.version >= (2, 80, 0) else "TOOLS"
    bl_category = "XPS Rename"

    def draw(self, context):
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


def register():
    for cls in classes:
        bpy.utils.register_class(cls)
    bpy.types.Scene.xps_bone_renamer = PointerProperty(type=XPSBoneRenamerSettings)


def unregister():
    del bpy.types.Scene.xps_bone_renamer
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)


if __name__ == "__main__":
    register()
