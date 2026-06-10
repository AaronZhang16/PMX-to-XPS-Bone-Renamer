# (WORK IN PROGRESS)

# PMX to XPS Bone Renamer

This workspace contains a Blender add-on for semi-automatic PMX/MMD bone renaming before exporting to XPS/XNALara.

## Install

1. In Blender, open `Edit > Preferences > Add-ons`.
2. Click `Install...`.
3. Select `xps_bone_renamer_blender_addon.py`.
4. Enable `PMX to XPS Bone Renamer`.

The panel appears in `View3D > Sidebar > XPS Rename` on Blender 2.80+, or in the Tool Shelf on Blender 2.79.

## Suggested Workflow

1. Import the PMX model.
2. Run your usual CATS cleanup if needed.
3. Select the armature.
4. Open `XPS Rename`.
5. Optional: choose a custom `.xlsx` rename table with `Choose Rename XLSX`.
6. Click `Preview Rename`.
7. Check the generated Blender text block named `XPS Bone Rename Preview`.
8. Adjust `Min Confidence`.
9. Click `Apply Rename`.
10. Export to XPS.

## Naming Strategy

The add-on uses three levels:

- Custom `.xlsx` mappings are applied first when selected. Column A must contain the current bone name, and column B must contain the target XPS bone name.
- Core human bones are renamed to XPS-style names such as `pelvis`, `spine lower`, `arm left elbow`, and `leg right knee`.
- Secondary bones are grouped by category, such as `hair left 01`, `skirt front`, `sleeve right 03`, `ribbon`, `tail`, `wing`, `cloth`, `accessory`, and `weapon`.
- Unknown bones are left unchanged by default. You can enable `Format Unknown Bones` to safely format numeric names without assigning a semantic category.

## Safety Notes

- Always run `Preview Rename` before applying.
- The add-on renames matching vertex groups on meshes using the selected armature, so skin weights stay connected.
- Low-confidence rows are skipped by default.
- For unusual clothes, props, or physics rigs, keep `Format Unknown Bones` disabled until you inspect the preview.

## Development Style

- All Python functions should include parameter and return type annotations.
- Function and method documentation should use Google-style docstrings with `Args:` and `Returns:` sections.
- Keep Blender 2.79 compatibility in mind when editing the add-on, so avoid syntax that requires newer Python versions.
