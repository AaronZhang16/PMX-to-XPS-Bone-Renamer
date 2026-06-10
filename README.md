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
5. Click `Preview Rename`.
6. Check the generated Blender text block named `XPS Bone Rename Preview`.
7. Adjust `Min Confidence`.
8. Click `Apply Rename`.
9. Export to XPS.

## Naming Strategy

The add-on uses three levels:

- Core human bones are renamed to XPS-style names such as `pelvis`, `spine lower`, `arm left elbow`, and `leg right knee`.
- Secondary bones are grouped by category, such as `hair left 01`, `skirt front`, `sleeve right 03`, `ribbon`, `tail`, `wing`, `cloth`, `accessory`, and `weapon`.
- Unknown bones are left unchanged by default. You can enable `Prefix Unknown Bones` to rename them as `misc original_name`.

## Safety Notes

- Always run `Preview Rename` before applying.
- The add-on renames matching vertex groups on meshes using the selected armature, so skin weights stay connected.
- Low-confidence rows are skipped by default.
- For unusual clothes, props, or physics rigs, keep `Prefix Unknown Bones` disabled until you inspect the preview.
