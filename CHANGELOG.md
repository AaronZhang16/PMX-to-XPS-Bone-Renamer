# Changelog

All notable changes to PMX to XPS Bone Renamer are documented in this file.

The format follows the spirit of Keep a Changelog, and this project uses
semantic versioning-style version labels.

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

