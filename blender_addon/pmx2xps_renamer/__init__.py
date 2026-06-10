"""Blender add-on for semi-automatic PMX/MMD to XPS bone renaming.

The add-on combines learned mappings from previous manual renames with
rule-based fallback logic for common humanoid, clothing, hair, and accessory
bones. It is intended to be run after PMX import and optional CATS cleanup.
"""

bl_info = {
    "name": "PMX to XPS Bone Renamer",
    "author": "Codex",
    "version": (0, 1, 6),
    "blender": (2, 80, 0),
    "location": "View3D > Sidebar > XPS Rename",
    "description": "Semi-automatic PMX/MMD bone renaming helper for XPS/XNALara workflows.",
    "category": "Rigging",
}

import json
import re
import zipfile
import xml.etree.ElementTree as ElementTree
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

import bpy
from bpy.props import BoolProperty, FloatProperty, PointerProperty, StringProperty
from bpy.types import Operator, Panel, PropertyGroup
from bpy_extras.io_utils import ImportHelper


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
    "tongue": ["舌", "tongue"],
    "teeth": ["歯", "牙", "teeth", "tooth"],
}

FINGER_KEYWORDS = {
    "thumb": ["親指", "thumb"],
    "index": ["人指", "人差", "index", "indexfinger"],
    "middle": ["中指", "middle", "middlefinger"],
    "ring": ["薬指", "ring", "ringfinger"],
    "pinky": ["小指", "pinky", "little", "littlefinger"],
}

SECONDARY_KEYWORDS = {
    "side_hair": ["側長髮", "侧长发", "側hair", "sidehair", "side hair"],
    "front_hair": ["劉海", "刘海", "bang", "fronthair", "front hair"],
    "back_hair": ["backhair", "back hair"],
    "hair": ["髪", "髮", "发", "毛", "hair", "bang", "kami", "劉海", "刘海", "長髮", "长发"],
    "skirt": ["スカート", "skirt", "裙"],
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

LEFT_TOKENS = ["左", "左側", "_l", ".l", "-l", "left"]
RIGHT_TOKENS = ["右", "右側", "_r", ".r", "-r", "right"]
LEFT_SUFFIX_PATTERN = re.compile(r"(?:^|[^a-z0-9])(?:l|left)$", re.IGNORECASE)
RIGHT_SUFFIX_PATTERN = re.compile(r"(?:^|[^a-z0-9])(?:r|right)$", re.IGNORECASE)

TWIST_TOKENS = ["捩", "twist", "回転", "roll"]
IK_TOKENS = ["ik", "ＩＫ"]

LEARNED_MAP_CACHE = None


RenameResult = Tuple[str, float, str]
RenamePlanRow = Dict[str, Any]
LearnedEntry = Dict[str, Any]
LearnedMap = Dict[str, Dict[str, LearnedEntry]]
SkirtGridInfo = Dict[str, RenameResult]
StructuredChainInfo = Dict[str, RenameResult]
CustomRenameMap = Dict[str, str]


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
    normalized = clean_text(name)
    if RIGHT_SUFFIX_PATTERN.search(normalized):
        return "right"
    if LEFT_SUFFIX_PATTERN.search(normalized):
        return "left"
    if contains_any(name, RIGHT_TOKENS):
        return "right"
    if contains_any(name, LEFT_TOKENS):
        return "left"
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


def xml_text(element: Optional[Any]) -> str:
    """Collects all text under an XML element.

    Args:
        element: XML element or None.

    Returns:
        Concatenated text content.
    """
    if element is None:
        return ""
    return "".join(element.itertext())


def read_shared_strings(workbook_zip: zipfile.ZipFile) -> List[str]:
    """Reads shared strings from an XLSX archive.

    Args:
        workbook_zip: Open XLSX zip archive.

    Returns:
        Shared string table. Returns an empty list when the workbook has no
        shared string part.
    """
    try:
        raw_xml = workbook_zip.read("xl/sharedStrings.xml")
    except KeyError:
        return []

    root = ElementTree.fromstring(raw_xml)
    namespace = {"main": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}
    strings = []
    for item in root.findall("main:si", namespace):
        strings.append(xml_text(item).strip())
    return strings


def cell_column(cell_reference: str) -> str:
    """Extracts the column letters from an Excel cell reference.

    Args:
        cell_reference: Cell reference such as ``A1`` or ``BC12``.

    Returns:
        Uppercase column letters.
    """
    match = re.match(r"([A-Za-z]+)", cell_reference or "")
    return match.group(1).upper() if match else ""


def read_cell_value(cell: Any, shared_strings: List[str]) -> str:
    """Reads a text value from a worksheet cell element.

    Args:
        cell: XML cell element.
        shared_strings: Shared string table from the workbook.

    Returns:
        Cell value as a stripped string.
    """
    cell_type = cell.attrib.get("t", "")
    value_element = cell.find("{http://schemas.openxmlformats.org/spreadsheetml/2006/main}v")
    inline_element = cell.find("{http://schemas.openxmlformats.org/spreadsheetml/2006/main}is")

    if cell_type == "inlineStr":
        return xml_text(inline_element).strip()

    raw_value = xml_text(value_element).strip()
    if cell_type == "s":
        try:
            return shared_strings[int(raw_value)].strip()
        except (IndexError, ValueError):
            return ""
    return raw_value


def load_custom_rename_map(file_path: str) -> CustomRenameMap:
    """Loads exact bone rename mappings from a two-column XLSX file.

    Args:
        file_path: Local path to an ``.xlsx`` file. Column A is the source bone
            name, and column B is the target bone name.

    Returns:
        Mapping from source name to target name. Empty rows and rows without a
        target name are ignored.
    """
    if not file_path:
        return {}

    path = Path(bpy.path.abspath(file_path))
    if not path.exists() or path.suffix.lower() != ".xlsx":
        return {}

    rename_map = {}
    with zipfile.ZipFile(str(path), "r") as workbook_zip:
        shared_strings = read_shared_strings(workbook_zip)
        try:
            raw_xml = workbook_zip.read("xl/worksheets/sheet1.xml")
        except KeyError:
            return {}

        root = ElementTree.fromstring(raw_xml)
        namespace = {"main": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}
        for row in root.findall(".//main:row", namespace):
            row_values = {}
            for cell in row.findall("main:c", namespace):
                column = cell_column(cell.attrib.get("r", ""))
                if column in {"A", "B"}:
                    row_values[column] = read_cell_value(cell, shared_strings)
            source_name = row_values.get("A", "").strip()
            target_name = row_values.get("B", "").strip()
            if source_name and target_name:
                rename_map[source_name] = target_name
    return rename_map


def classify_custom(name: str, custom_map: CustomRenameMap) -> Optional[RenameResult]:
    """Classifies a bone with the user-selected custom XLSX mapping.

    Args:
        name: Source bone name.
        custom_map: Mapping loaded from the selected XLSX file.

    Returns:
        A high-confidence rename result or None when the bone name is not in
        the custom mapping.
    """
    target_name = custom_map.get(name)
    if not target_name:
        return None
    return (target_name, 0.99, "custom xlsx mapping")


def has_secondary_semantic(name: str) -> bool:
    """Checks whether a name contains an object/category keyword.

    Args:
        name: Bone name to inspect.

    Returns:
        True when the name is more likely a secondary object bone than a core
        body bone.
    """
    return bool(category_match(name, SECONDARY_KEYWORDS))


def chain_suffix(name: str) -> str:
    """Extracts a stable chain number from names such as ``Hair1_2_L``.

    Args:
        name: Bone name containing one or more numeric fragments.

    Returns:
        A leading-space numeric suffix, or an empty string when no number is
        found.
    """
    numbers = re.findall(r"\d+", name)
    if not numbers:
        return ""
    return " %d" % int(numbers[-1])


def semantic_chain_prefix(name: str, bone: Any) -> str:
    """Builds a semantic XPS prefix for hair and sleeve chain bones.

    Args:
        name: Source bone name.
        bone: Blender bone used for optional side inference.

    Returns:
        XPS prefix such as ``hair side left`` or ``sleeve right``. Returns an
        empty string when the name is not a supported chain category.
    """
    category = category_match(name, SECONDARY_KEYWORDS)
    side = side_from_name(name) or side_from_position(bone)
    if category == "side_hair":
        return "hair side%s" % side_label(side)
    if category == "front_hair":
        return "hair front%s" % side_label(side)
    if category == "back_hair":
        return "hair back%s" % side_label(side)
    if category == "hair":
        return "hair%s" % side_label(side)
    if category == "sleeve":
        return "sleeve%s" % side_label(side)
    return ""


def parse_numbered_chain_name(name: str) -> Optional[Tuple[str, int, int, str]]:
    """Parses ``prefix_parent_child_side`` style hair/sleeve names.

    Args:
        name: Source bone name.

    Returns:
        Tuple of ``(raw_prefix, parent_number, child_number, side_suffix)`` or
        None when the name does not contain a supported structural pattern.
    """
    no_number_prefix = re.match(r"^([^0-9_]+)_(\d+)_(\d+)(?:_([LR]))?$", name, re.IGNORECASE)
    if no_number_prefix:
        return (
            no_number_prefix.group(1) + "#two_number",
            int(no_number_prefix.group(3)),
            int(no_number_prefix.group(2)),
            (no_number_prefix.group(4) or "").upper(),
        )

    numbered_prefix = re.match(r"^(.*\D)(\d+)_(\d+)(?:_([LR]))?$", name, re.IGNORECASE)
    if numbered_prefix:
        return (
            numbered_prefix.group(1) + "#numbered_prefix",
            int(numbered_prefix.group(2)),
            int(numbered_prefix.group(3)),
            (numbered_prefix.group(4) or "").upper(),
        )

    return None


def build_numbered_chain_map(bones: List[Any]) -> StructuredChainInfo:
    """Builds context-aware names for numbered hair and sleeve chains.

    Names such as ``Sleeve1_2_R`` or ``BackHair3_1_L`` are grouped by their
    semantic XPS prefix and raw source prefix. Within each group, the first
    number is treated as the parent-chain number and converted to a letter.
    The second number is treated as the child segment number.

    Args:
        bones: Blender bone objects from an armature.

    Returns:
        Mapping from original bone name to rename result tuple.
    """
    rows = []
    for bone in bones:
        parsed = parse_numbered_chain_name(bone.name)
        if not parsed:
            continue
        raw_prefix, parent_number, child_number, side_suffix = parsed
        semantic_prefix = semantic_chain_prefix(bone.name, bone)
        if not semantic_prefix:
            continue
        group_key = (semantic_prefix, raw_prefix, side_suffix)
        rows.append((bone.name, group_key, semantic_prefix, parent_number, child_number))

    groups = {}
    for name, group_key, semantic_prefix, parent_number, child_number in rows:
        groups.setdefault(group_key, []).append((name, semantic_prefix, parent_number, child_number))

    chain_map = {}
    for group_rows in groups.values():
        parents = sorted({parent_number for _, _, parent_number, _ in group_rows})
        children = sorted({child_number for _, _, _, child_number in group_rows})
        parent_to_letter = {
            parent_number: letter_for_index(index)
            for index, parent_number in enumerate(parents)
        }
        child_offset = 1 if children and children[0] == 0 else 0
        for name, semantic_prefix, parent_number, child_number in group_rows:
            new_name = "%s %s %d" % (
                semantic_prefix,
                parent_to_letter[parent_number],
                child_number + child_offset,
            )
            chain_map[name] = (new_name, 0.84, "structured hair/sleeve chain")
    return chain_map


def strip_side_suffix(name: str) -> Tuple[str, str]:
    """Removes a trailing side suffix from a source bone name.

    Args:
        name: Source bone name that may end in ``_L`` or ``_R``.

    Returns:
        Tuple of ``(name_without_side, side_label)``.
    """
    match = re.match(r"^(.*)_([LR])$", name, re.IGNORECASE)
    if not match:
        return (name, "")
    side = "left" if match.group(2).upper() == "L" else "right"
    return (match.group(1), side)


def classify_unknown(name: str) -> Optional[RenameResult]:
    """Formats unknown bones without assigning them to a semantic category.

    The fallback intentionally keeps the original prefix intact. It only
    normalizes common numeric structures so unclassified bones are easier to
    scan in XPS.

    Args:
        name: Source bone name.

    Returns:
        A low-confidence rename result or None when no safe formatting rule
        applies.
    """
    name_without_side, side = strip_side_suffix(name)

    two_number_match = re.match(r"^(.+?)_(\d+)_(\d+)$", name_without_side)
    if two_number_match:
        prefix = two_number_match.group(1)
        parent_number = int(two_number_match.group(2))
        child_number = int(two_number_match.group(3))
        side_text = side_label(side)
        return (
            "%s%s %s %d" % (prefix, side_text, letter_for_index(parent_number), child_number),
            0.30,
            "unknown numbered chain",
        )

    one_number_match = re.match(r"^(.+?)_(\d+)$", name_without_side)
    if one_number_match:
        prefix = one_number_match.group(1)
        number = int(one_number_match.group(2))
        side_text = side_label(side)
        return (
            "%s%s %d" % (prefix, side_text, number),
            0.30,
            "unknown numeric suffix",
        )

    trailing_number_match = re.match(r"^(.*?)(\d+)$", name_without_side)
    if trailing_number_match and trailing_number_match.group(1):
        prefix = trailing_number_match.group(1).rstrip("_ ")
        number = int(trailing_number_match.group(2))
        side_text = side_label(side)
        return (
            "%s%s %d" % (prefix, side_text, number),
            0.30,
            "unknown trailing number",
        )

    return None


def classify_structured_skirt(name: str) -> Optional[RenameResult]:
    """Classifies common Chinese skirt-grid names such as ``裙_6_1``.

    Args:
        name: Source bone name.

    Returns:
        A rename result tuple or None when the name is not a supported skirt
        grid name.
    """
    match = re.match(r"^(?:裙|skirt)_(\d+)_(\d+)$", name, re.IGNORECASE)
    if not match:
        return None

    row_index = int(match.group(1)) + 1
    column_index = int(match.group(2))
    column_names = {
        0: "front middle",
        1: "front left a",
        2: "front left b",
        3: "front left c",
        4: "back left c",
        5: "back left b",
        6: "back left a",
        7: "back right a",
        8: "back right b",
        9: "side right c",
        10: "side right b",
        11: "side right a",
        12: "front right a",
        13: "front right b",
        14: "front right c",
        15: "front right d",
    }
    column_name = column_names.get(column_index)
    if not column_name:
        return None
    return ("skirt %s %d" % (column_name, row_index), 0.86, "structured skirt pattern")


def parse_skirt_grid_name(name: str) -> Optional[Tuple[int, int]]:
    """Parses CATS-style skirt grid names.

    Args:
        name: Bone name in the form ``name_child_parent``.

    Returns:
        Tuple of ``(child_number, parent_number)`` or None when the name does
        not look like a skirt grid bone.
    """
    if not contains_any(name, SECONDARY_KEYWORDS["skirt"]):
        return None
    match = re.match(r"^.+_(\d+)_(\d+)$", name)
    if not match:
        return None
    return (int(match.group(1)), int(match.group(2)))


def group_items_evenly(items: List[int], group_count: int) -> Dict[int, int]:
    """Assigns sorted items to evenly distributed one-based groups.

    Args:
        items: Sorted parent numbers.
        group_count: Number of target groups.

    Returns:
        Mapping from parent number to one-based group number.
    """
    if not items:
        return {}

    item_count = len(items)
    groups = {}
    for index, item in enumerate(items):
        group = int(index * group_count / item_count) + 1
        groups[item] = min(group, group_count)
    return groups


def skirt_prefix_for_group(group_number: int) -> str:
    """Returns the XPS skirt prefix for an eight-way parent group.

    Args:
        group_number: One-based group number from 1 to 8.

    Returns:
        Prefix such as ``skirt front left``.
    """
    if group_number == 1:
        return "skirt front left"
    if group_number in {2, 3}:
        return "skirt side left"
    if group_number == 4:
        return "skirt back left"
    if group_number == 5:
        return "skirt back right"
    if group_number in {6, 7}:
        return "skirt side right"
    return "skirt front right"


def letter_for_index(index: int) -> str:
    """Converts a zero-based index to a lowercase letter label.

    Args:
        index: Zero-based position.

    Returns:
        A letter label. Values beyond ``z`` continue as ``z`` to avoid
        generating unusual multi-letter labels in XPS names.
    """
    return chr(ord("a") + min(index, 25))


def build_skirt_grid_map(bones: List[Any]) -> SkirtGridInfo:
    """Builds context-aware skirt grid names for all matching skirt bones.

    CATS skirt names commonly contain two numbers: ``name_child_parent``. The
    parent number identifies a large skirt chain, while the child number is a
    segment within that chain. Parent numbers are evenly divided into eight
    groups around the skirt, then converted to XPS-style names.

    Args:
        bones: Blender bone objects from an armature.

    Returns:
        Mapping from original bone name to rename result tuple.
    """
    parsed_rows = []
    parent_numbers = set()
    for bone in bones:
        parsed = parse_skirt_grid_name(bone.name)
        if not parsed:
            continue
        child_number, parent_number = parsed
        parsed_rows.append((bone.name, child_number, parent_number))
        parent_numbers.add(parent_number)

    parent_to_group = group_items_evenly(sorted(parent_numbers), 8)
    prefix_to_parents = {}
    for parent_number in sorted(parent_numbers):
        prefix = skirt_prefix_for_group(parent_to_group[parent_number])
        prefix_to_parents.setdefault(prefix, []).append(parent_number)

    parent_to_letter = {}
    for prefix, parents in prefix_to_parents.items():
        reverse = "right" in prefix
        ordered_parents = sorted(parents, reverse=reverse)
        for index, parent_number in enumerate(ordered_parents):
            parent_to_letter[parent_number] = letter_for_index(index)

    skirt_map = {}
    for name, child_number, parent_number in parsed_rows:
        prefix = skirt_prefix_for_group(parent_to_group[parent_number])
        letter = parent_to_letter[parent_number]
        new_name = "%s %s %d" % (prefix, letter, child_number + 1)
        skirt_map[name] = (new_name, 0.88, "structured skirt grid")
    return skirt_map


def classify_hair(name: str, bone: Any) -> Optional[RenameResult]:
    """Classifies hair bones before positional words can trigger core rules.

    Args:
        name: Source bone name.
        bone: Blender bone used for optional side inference.

    Returns:
        A rename result tuple or None when the name does not look like hair.
    """
    category = category_match(name, SECONDARY_KEYWORDS)
    if category not in {"hair", "side_hair", "front_hair", "back_hair"}:
        return None

    side = side_from_name(name) or side_from_position(bone)
    suffix = chain_suffix(name)
    if category == "side_hair":
        return ("hair side%s%s" % (side_label(side), suffix), 0.76, "side hair keyword")
    if category == "front_hair":
        return ("hair front%s%s" % (side_label(side), suffix), 0.76, "front hair keyword")
    if category == "back_hair":
        return ("hair back%s%s" % (side_label(side), suffix), 0.76, "back hair keyword")
    return ("hair%s%s" % (side_label(side), suffix), 0.72, "hair keyword")


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
    if has_secondary_semantic(name):
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
    if contains_any(name, CORE_KEYWORDS["tongue"]):
        suffix = number_suffix(name)
        suffix_text = (" %d" % suffix) if suffix is not None else ""
        return ("head tongue%s" % suffix_text, 0.82, "tongue keyword")
    if contains_any(name, CORE_KEYWORDS["teeth"]):
        lower = clean_text(name)
        if "down" in lower or "lower" in lower or "下" in lower:
            return ("head teeth lower", 0.82, "teeth keyword")
        if "up" in lower or "upper" in lower or "上" in lower:
            return ("head teeth upper", 0.82, "teeth keyword")
        return ("head teeth", 0.78, "teeth keyword")

    return None


def classify_secondary(name: str, bone: Any) -> Optional[RenameResult]:
    """Classifies non-core bones such as hair, skirt, sleeve, or accessories.

    Args:
        name: Source bone name.
        bone: Blender bone used for optional side inference.

    Returns:
        A rename result tuple or None when no secondary category matches.
    """
    structured_skirt = classify_structured_skirt(name)
    if structured_skirt:
        return structured_skirt

    hair_result = classify_hair(name, bone)
    if hair_result:
        return hair_result

    category = category_match(name, SECONDARY_KEYWORDS)
    if not category:
        return None

    side = side_from_name(name) or side_from_position(bone)
    suffix_text = chain_suffix(name)
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
    custom_map = load_custom_rename_map(settings.custom_mapping_path)
    skirt_grid_map = build_skirt_grid_map(bones)
    numbered_chain_map = build_numbered_chain_map(bones)

    for bone in bones:
        result = classify_custom(bone.name, custom_map)
        kind = "custom"
        if not result:
            result = skirt_grid_map.get(bone.name) or numbered_chain_map.get(bone.name)
            kind = "secondary"
        if not result:
            result = classify_learned(bone.name)
            kind = "learned"
        if not result:
            result = classify_hair(bone.name, bone) or classify_structured_skirt(bone.name)
            kind = "secondary"
        if not result:
            result = classify_core(bone.name, bone)
            kind = "core"
        if not result and settings.rename_secondary:
            result = classify_secondary(bone.name, bone)
            kind = "secondary"
        if not result and settings.rename_unknown:
            result = classify_unknown(bone.name)
            if result:
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
        name="Format Unknown Bones",
        description="Safely format numeric unknown bones instead of adding semantic categories",
        default=False,
    )
    unknown_prefix = StringProperty(
        name="Unknown Prefix",
        description="Legacy setting kept for saved Blender files; unknown bones are no longer prefixed",
        default="misc",
    )
    custom_mapping_path = StringProperty(
        name="Custom XLSX",
        description="Optional XLSX file with old bone names in column A and target XPS names in column B",
        default="",
        subtype="FILE_PATH",
    )


class XPS_OT_select_custom_mapping(Operator, ImportHelper):
    """Blender operator that selects a custom two-column XLSX mapping file."""

    bl_idname = "xps.select_custom_mapping"
    bl_label = "Choose Rename XLSX"
    bl_description = "Choose an XLSX file with source bone names in column A and target names in column B"
    bl_options = {"REGISTER"}

    filename_ext = ".xlsx"
    filter_glob = StringProperty(default="*.xlsx", options={"HIDDEN"})

    def execute(self, context: Any) -> Set[str]:
        """Stores the selected XLSX path in the add-on settings.

        Args:
            context: Blender operator context.

        Returns:
            Blender operator status set.
        """
        context.scene.xps_bone_renamer.custom_mapping_path = self.filepath
        self.report({"INFO"}, "Selected custom rename XLSX: %s" % self.filepath)
        return {"FINISHED"}


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
        layout.prop(settings, "custom_mapping_path")
        layout.operator("xps.select_custom_mapping", icon="FILE_FOLDER")
        layout.prop(settings, "rename_secondary")
        layout.prop(settings, "rename_unknown")
        layout.separator()
        layout.operator("xps.preview_bone_rename", icon="TEXT")
        layout.operator("xps.apply_bone_rename", icon="ARMATURE_DATA")


classes = (
    XPSBoneRenamerSettings,
    XPS_OT_select_custom_mapping,
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
