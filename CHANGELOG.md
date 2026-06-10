# Changelog

All notable changes to PMX to XPS Bone Renamer are documented in this file.

The format follows the spirit of Keep a Changelog, and this project uses
semantic versioning-style version labels.

## [0.1.6] - 2026-06-10

### Changed

- Added context-aware structured naming for hair and sleeve chains in the form
  `prefix_parent_child(_side)`.
- Added optional user-selected `.xlsx` rename mappings. Column A is the current
  bone name, and column B is the target bone name.
- Hair and sleeve parent numbers now determine the letter label in ascending
  order, while child numbers determine the final numeric segment.
- Structured hair and sleeve naming now runs before learned exact mappings so
  older per-model mappings do not interrupt consistent chain naming.
- Custom `.xlsx` mappings run before automatic and learned rules.
- Replaced unknown-bone `misc` prefix fallback with conservative numeric
  formatting.

### Fixed

- Corrected numbered hair/sleeve parsing based on source name shape.
- Names like `Sleeve_0_1_R` now treat the second number as the parent/letter
  index and the first number as the child segment.
- Names like `Sleeve1_1_R` and `MiddleBackHair1_2` now treat the number in the
  prefix as the parent/letter index and the suffix number as the child segment.
- Separated the two source-name formats internally so zero-based and one-based
  child numbering do not interfere with each other.
- Unknown bones in the form `prefix_numberA_numberB(_side)` now become
  `prefix side letter numberB`, while `prefix_number(_side)` becomes
  `prefix side number`.
- Unknown bones ending with a trailing number now get a space before the number;
  names without safe numeric structure remain unchanged.

## [0.1.5] - 2026-06-10

### Changed

- Reworked skirt grid fallback naming to use the full armature context instead
  of isolated per-bone matching.
- CATS-style skirt names in the form `name_child_parent` now use parent numbers
  to divide skirt chains into eight ordered groups:
  `skirt front left`, `skirt side left`, `skirt back left`,
  `skirt back right`, `skirt side right`, and `skirt front right`.
- Parent chains on the left half assign letters from smaller parent numbers to
  earlier letters, while right-half chains assign letters from larger parent
  numbers to earlier letters.

## [0.1.4] - 2026-06-10

### Fixed

- Changed side/front/back hair fallback names to keep the base structure first,
  for example `hair side left 2` instead of `side hair left 2`.
- Added tongue and teeth fallback naming so `Tongue_01`, `DownTeeth`, and
  `UpTeeth` become head-group bones instead of unknown `misc` bones.

## [0.1.3] - 2026-06-10

### Fixed

- Fixed side-hair bones such as `側長髮1_2_L` staying unchanged by adding
  Traditional Chinese hair keywords and side-hair detection.
- Fixed hair bones such as `Middle劉海1_1` and `MiddleBackHair1_2` being
  misclassified as middle-finger bones.
- Fixed right-side sleeve bones such as `Sleeve1_1_R` being classified as left
  side because of overly broad single-letter side matching.
- Fixed skirt grid bones such as `裙_6_1` and `裙_8_2` staying unchanged when
  only part of the same skirt structure existed in the learned mapping data.

### Added

- Added semantic priority for secondary object names, so hair/skirt/sleeve
  meaning is checked before generic body-part rules.
- Added structured fallback naming for Chinese skirt grid names in the form
  `裙_i_j`.
- Added sample rule checks for side hair, front hair, back hair, sleeve side
  detection, and skirt grid fallback naming.

## [0.1.2] - 2026-06-10

### Fixed

- Updated `bl_info` to require Blender 2.80+, resolving the Blender warning
  `upgrade to 2.8x required`.
- Ensured the add-on panel appears in the Blender 2.80+ 3D View sidebar under
  `XPS Rename`.

## [0.1.1] - 2026-06-10

### Added

- Added `learned_name_map.json`, generated from historical two-column rename
  references in `name_reference`.
- Added learned exact-name matching before rule-based fallback naming.
- Added a text summary of observed naming patterns in
  `name_reference/name_reference_findings.txt`.

### Changed

- Updated core humanoid naming to better match the user's existing XPS naming
  style, such as `head neck lower`, `head neck upper`, and
  `arm right finger index a`.
- Standardized Python functions with type annotations and Google-style
  docstrings.

## [0.1.0] - 2026-06-10

### Added

- Initial Blender add-on project structure.
- Added preview-only rename planning through the `Preview Rename` operator.
- Added high-confidence rename application through the `Apply Rename` operator.
- Added vertex group renaming so mesh weights remain connected after bone
  renames.
- Added core humanoid, secondary clothing, hair, accessory, and unknown-bone
  classification logic.
- Added PowerShell script for building an installable Blender add-on zip.
