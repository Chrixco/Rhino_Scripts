# Quick Start Guide

**Last Updated:** February 2026

## 30-Second Setup

### Option 1: Generate Contour Map

```bash
# 1. Open Rhino
rhino

# 2. Open Python editor
Tools > Python Script > Edit

# 3. Open script
File > Open > /Users/chcorral/rhino_scripts/01_topographic_map_generator/generate_topo_maps.py

# 4. Run
Press F5

# 5. Select point cloud file
/Users/chcorral/Downloads/00_ModeloDigitalTerreno\ 2/MDT_3314-252_1000.xyz.csv

# 6. Use defaults (all checkboxes on)
# 7. Watch console for progress
# 8. View result in Rhino!
```

### Option 2: Position Buildings on Terrain

```bash
# 1. Open Rhino with your terrain + buildings
rhino scene.3dm

# 2. Open Python editor
Tools > Python Script > Edit

# 3. Open script
File > Open > /Users/chcorral/rhino_scripts/02_building_terrain_placement/place_building_on_terrain.py

# 4. Run
Press F5

# 5. Select:
  - Terrain surface (click on it)
  - Building(s) (click one or more, then ENTER)
  - Movement direction (choose 1 or 2)
  - Clearance (enter 0 or your preference)

# 6. Done! Buildings positioned
```

## Keyboard Shortcuts

| Action | Shortcut |
|--------|----------|
| Run script | F5 |
| Open Python editor | Tools > Python Script > Edit |
| Show console | F2 |
| Undo all | Ctrl+Z |
| Redo all | Ctrl+Y |
| Zoom extents | Ctrl+0 |

## File Locations

| Purpose | Path |
|---------|------|
| Main scripts | `/Users/chcorral/rhino_scripts/` |
| Contour generator | `01_topographic_map_generator/generate_topo_maps.py` |
| Building placer | `02_building_terrain_placement/place_building_on_terrain.py` |
| Documentation | See README.md in each folder |
| Test data | `/Users/chcorral/Downloads/00_ModeloDigitalTerreno\ 2/` |

## Configuration Cheat Sheet

### Topographic Maps

**Fastest (preview only):**
```python
DEFAULT_CONTOUR_INTERVAL = 10.0
```

**Standard (recommended):**
```python
DEFAULT_CONTOUR_INTERVAL = 5.0
DEFAULT_INDEX_EVERY = 5
```

**Detailed (planning):**
```python
DEFAULT_CONTOUR_INTERVAL = 1.0
DEFAULT_INDEX_EVERY = 2
```

### Building Placement

**Fast (simple terrain):**
```python
RAY_SAMPLE_GRID = 3
```

**Standard (recommended):**
```python
RAY_SAMPLE_GRID = 5
```

**Accurate (complex terrain):**
```python
RAY_SAMPLE_GRID = 9
```

## Common Workflows

### Workflow: Create Contours from Survey Data

```
1. Have: Survey CSV file (X, Y, Z columns)

2. Open Rhino
   Tools > Python Script > Edit

3. Load: 01_topographic_map_generator/generate_topo_maps.py
   Press F5

4. Select file dialog
   Navigate to your CSV

5. Configure
   Interval: 5.0 (or your preference)
   Index: 5
   Options: All checked

6. Wait (~30 seconds for 660k points)

7. Result: Layers in Rhino with contours
```

### Workflow: Position 5 Buildings on Slope

```
1. Have:
   - Terrain mesh/surface
   - 5 building extrusions

2. Open Rhino with scene

3. Open Python script
   Tools > Python Script > Edit

4. Load: 02_building_terrain_placement/place_building_on_terrain.py
   Press F5

5. Select:
   Terrain → Terrain mesh (click it)
   Buildings → Bldg1, Bldg2, Bldg3, Bldg4, Bldg5 (click each, ENTER when done)
   Direction → 2 (Perpendicular to Terrain)
   Clearance → 0.05 (5cm clearance)

6. Wait (~10 seconds)

7. Result: All 5 buildings positioned on slope
```

### Workflow: Undo Last Operation

```
Ctrl+Z
(All buildings/contours from last script run are reverted)

Ctrl+Y
(Redo the operation)
```

## Troubleshooting Quick Fixes

| Problem | Fix |
|---------|-----|
| "File not found" | Check path spelling, verify file exists |
| Script doesn't run | Make sure Rhino 7+ and Python is installed |
| No contours generated | Increase interval (e.g., 5→1), check Z range |
| Building not moved | Check terrain was selected correctly |
| Script hangs | Close other apps, wait (large files take time) |
| Undo doesn't work | Press Ctrl+Z multiple times if needed |

## FAQ - Quick Answers

**Q: Can I modify the scripts?**
A: Yes! Edit constants at top of script, save, run

**Q: Can I use my own data?**
A: Yes! Any CSV (X,Y,Z) or E57 format supported

**Q: How many buildings can I position?**
A: As many as you want - batch processing works

**Q: Do I need to install anything?**
A: No - everything works with built-in Rhino Python (optionally: `pip install pye57` for E57)

**Q: What if something goes wrong?**
A: Press Ctrl+Z to undo, read console (F2) for error messages

**Q: Can I run scripts from command line?**
A: Yes - use Rhino batch mode or `RunPythonScript` command

## Common Tasks

### Change Contour Interval

```python
# Open script in text editor
# Find this line (~line 89):
DEFAULT_CONTOUR_INTERVAL = 5.0

# Change to:
DEFAULT_CONTOUR_INTERVAL = 2.0   # For 2m contours

# Save and run in Rhino
```

### Change Line Weights

```python
# Find (~line 91-92):
LW_REGULAR = 0.18
LW_INDEX = 0.50

# Change to:
LW_REGULAR = 0.12
LW_INDEX = 0.35

# Save and run
```

### Add Clearance to Buildings

```python
# In building placement script
# Find (~line 40):
VERTICAL_OFFSET = 0.0

# Change to:
VERTICAL_OFFSET = 0.1   # 10cm above terrain

# Save and run
```

### Process Multiple Terrains

Run script separately for each terrain:
```
Run 1: Terrain1 + Buildings 1-5
  (Ctrl+Z to undo if needed)

Run 2: Terrain2 + Buildings 6-10
  (Ctrl+Z to undo if needed)
```

## Performance Tips

**Make scripts faster:**
- Reduce point cloud size (thin/subsample first)
- Use higher contour interval (fewer contours = faster)
- Reduce `RAY_SAMPLE_GRID` from 5 to 3 for buildings
- Close other applications

**Make scripts more accurate:**
- Increase `RAY_SAMPLE_GRID` from 5 to 7 or 9
- Reduce contour interval (more detailed)
- Use full point cloud (don't subsample)

## Next Steps

1. **Read full documentation:**
   - [Topo Generator Guide](01_topographic_map_generator/README.md)
   - [Building Placement Guide](02_building_terrain_placement/README.md)

2. **Try with your data:**
   - Prepare CSV or E57 file
   - Follow workflow examples
   - Adjust settings as needed

3. **Customize for your needs:**
   - Edit configuration constants
   - Modify colors, line weights, intervals
   - Save modified scripts with new names

## File Paths Reference

```
Copy-paste these paths into Rhino:

Contour generator:
/Users/chcorral/rhino_scripts/01_topographic_map_generator/generate_topo_maps.py

Building placer:
/Users/chcorral/rhino_scripts/02_building_terrain_placement/place_building_on_terrain.py

Test data:
/Users/chcorral/Downloads/00_ModeloDigitalTerreno\ 2/MDT_3314-252_1000.xyz.csv
```

---

**Ready to start?** Pick a script above and open it in Rhino!

For more help, see the full README.md files in each project folder.
