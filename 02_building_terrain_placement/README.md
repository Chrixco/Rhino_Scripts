# Building Terrain Placement

**Location:** `/Users/chcorral/rhino_scripts/02_building_terrain_placement/`

**Main Script:** `place_building_on_terrain.py`

## Overview

Automatically positions one or multiple buildings on terrain by moving them perpendicular to the terrain surface until they touch. Handles slopes, irregular terrain, and batch operations.

## Features

✅ Select terrain (surface, mesh, extrusion)
✅ Select single or multiple buildings
✅ Automatic vertical positioning
✅ Multi-ray footprint sampling (handles complex shapes)
✅ Collision detection
✅ Batch processing with undo support
✅ Terrain slope handling

## Quick Start

### 1. **Organize Objects by Layer** ⭐ NEW

In Rhino, create two layers and organize your objects:

**Create "Terrain" layer:**
```
1. Layer > New > Name: "Terrain"
2. Move your terrain surface/mesh to this layer
```

**Create "Buildings" layer:**
```
1. Layer > New > Name: "Buildings"
2. Move all buildings (extrusions, breps) to this layer
```

Your scene should now have:
```
Layers panel:
├─ Terrain (contains 1 terrain surface)
└─ Buildings (contains 1+ buildings)
```

### 2. **Open Python Editor**

```
Tools > Python Script > Edit
```

### 3. **Load Script**

```
File > Open > /Users/chcorral/rhino_scripts/02_building_terrain_placement/place_building_on_terrain.py
```

### 4. **Run**

```
Press F5  OR  Click "Run" button
```

### 5. **Follow Prompts**

**Prompt 1: Terrain Layer Name**
```
"Terrain layer name? (default: Terrain)"
```
- Press ENTER to use "Terrain" (if you created that layer)
- Or type a different layer name (e.g., "City")

**Prompt 2: Buildings Layer Name**
```
"Buildings layer name? (default: Buildings)"
```
- Press ENTER to use "Buildings"
- Or type a different layer name

**Prompt 3: Choose Movement Direction**
```
"How should buildings move?"
  [1] Straight Down (Z-axis)
  [2] Perpendicular to Terrain (follows slopes)
```
- **Option 1** - Simple vertical drop (faster)
- **Option 2** - Follows terrain slope (more natural, slower)

**Prompt 4: Clearance Offset**
```
"How high above terrain? (0 = touch, 0.1 = 10cm above)"
```
- Enter **0** to have building touch terrain
- Enter **0.1** for 10cm clearance above terrain
- Enter **-0.5** to sink 50cm into terrain (unusual but possible)

**Step 5: Processing & Results**
```
Processing Building 1...
  Sampled 25 terrain points under footprint
  Contact found at Z = 765.423m
  ✓ Building positioned

Processing Building 2...
  ✓ Building positioned

Summary: 2 buildings placed successfully!
```

**Step 6: Undo if Needed**
```
Ctrl+Z  (undoes ALL buildings at once)
```

## Workflow Examples

### Workflow 1: Simple Site - Single Building

```
1. Load: Terrain mesh + 1 building extrusion
2. Run script
3. Select: Terrain → Building
4. Direction: Straight Down
5. Clearance: 0
6. Result: Building sits on terrain
```

### Workflow 2: Complex Site - Multiple Buildings

```
1. Load: Terrain surface + 5 building extrusions
2. Run script
3. Select: Terrain → Building1 → Building2 → ... → Building5 (ENTER)
4. Direction: Perpendicular to Terrain
5. Clearance: 0.05 (5cm foundation clearance)
6. Result: All 5 buildings positioned on sloped terrain
```

### Workflow 3: Dense Urban Area

```
1. Load: High-resolution terrain mesh + 50+ buildings
2. Run script
3. Select: Terrain → Ctrl+A to select all buildings
4. Direction: Perpendicular to Terrain
5. Clearance: 0.1 (10cm)
6. Result: Batch positioning with one undo
```

### Workflow 4: Stilts/Elevated Structures

```
1. Load: Terrain + buildings that should float above
2. Run script
3. Select: Terrain → Building
4. Direction: Straight Down
5. Clearance: 3.5 (position 3.5m above terrain for stilt height)
6. Result: Building floats above terrain
```

## Configuration

Edit these constants at the top of the script:

```python
RAY_SAMPLE_GRID = 5           # Number of rays per side (5x5=25 rays)
                              # Increase to 7 or 9 for complex footprints

RAY_CAST_DISTANCE = 10000.0   # Maximum distance to cast rays downward
                              # Increase if buildings very high above terrain

VERTICAL_OFFSET = 0.0         # Default ground clearance in model units
                              # Set to 0.1 for 10cm, etc.
```

## Understanding the Output

### Ray Sampling Grid

The script casts rays from a grid across the building's footprint:

```
Building footprint (top view):

5x5 ray grid (25 points total):
  ○ ○ ○ ○ ○
  ○ ○ ○ ○ ○
  ○ ○ ○ ○ ○
  ○ ○ ○ ○ ○
  ○ ○ ○ ○ ○

The script finds the HIGHEST terrain point under the footprint
and positions the building to rest on it.
```

### Why 5x5?

- **Too few (3x3):** May miss terrain features under footprint
- **Good (5x5):** Balances accuracy vs. speed (default)
- **Detailed (7x7+):** Better for irregular terrain but slower

### Multiple Buildings

Processing order:
```
1. Building 1: Cast rays → Find contact → Move
2. Building 2: Cast rays → Find contact → Move
3. Building 3: Cast rays → Find contact → Move
...
All moves combined in single undo record
```

## Edge Cases & Solutions

### Building Already Below Terrain

**Problem:** Building is positioned below terrain surface

**What Script Does:**
- Skips the building
- Warns user: "Building already below terrain"
- Continues with next building

**Solution:**
- Move building above terrain first
- Rerun script
- Or use negative clearance offset (not recommended)

### Rays Miss Terrain (Building Very High Up)

**Problem:** No intersection found with terrain

**What Script Does:**
- Uses elevated fallback ray from 500km up
- Recalculates intersection
- Usually recovers automatically

**Solution:**
- Ensure building is within `RAY_CAST_DISTANCE` of terrain
- Increase `RAY_CAST_DISTANCE` if building very high

### Terrain Has Holes/Gaps

**Problem:** Some rays hit terrain, some miss

**What Script Does:**
- Uses rays that hit terrain
- Ignores rays that miss
- Uses highest contact point found

**Solution:**
- Fill holes in terrain mesh first
- Or increase `RAY_SAMPLE_GRID` for more samples

### Building is Locked

**Problem:** Cannot move locked building

**What Script Does:**
- Detects locked status
- Skips locked building
- Reports: "Skipped: [Building Name] (locked)"

**Solution:**
- Unlock building in Rhino first
- Or edit layers to unlock

### Very Complex Building Shape

**Problem:** Ray samples might miss contact points

**Solution:**
- Increase `RAY_SAMPLE_GRID` from 5 to 7 or 9
- Script will sample more points under footprint
- Slightly slower but more accurate

## Terrain Types

### Supported

✅ **Brep Surfaces** - Typical terrain surfaces
✅ **Meshes** - DEM grids, triangulated terrain
✅ **Extrusions** - If terrain is an extruded shape
✅ **Mixed** - Can batch process buildings on any terrain type

### Example Terrain

```
From topographic map:
  Topo_Surface (mesh DEM)

From CAD import:
  Terrain.dwg (Brep surface)

From LiDAR:
  DEM_mesh (mesh from point cloud)

From modeling:
  Site_extrusion (extruded footprint)
```

## Building Types

### Supported

✅ **Extrusions** - Standard building from footprint
✅ **Breps** - Polysurface buildings
✅ **Meshes** - Tessellated buildings
✅ **Multiple** - Batch process different types together

### Example Buildings

```
Simple extrusion:
  Building (Extrusion)

Complex model:
  Building_Model (PolySurface)

Imported model:
  Building.dwg (mixed geometry)

Multiple:
  Bldg_1, Bldg_2, Bldg_3 (all extrusions)
```

## Troubleshooting

### "No intersection with terrain found"

**Cause:** Ray completely misses terrain

**Fix:**
1. Zoom to fit both terrain and building
2. Verify building is above terrain
3. Increase `RAY_CAST_DISTANCE` in script
4. Re-run

### "Building is locked"

**Cause:** Building object is locked

**Fix:**
1. Select building layer
2. Right-click > Unlock
3. Re-run script

### "Invalid terrain selection"

**Cause:** Selected object is not a valid terrain surface

**Fix:**
1. Ensure selected object is:
   - A mesh
   - A Brep surface
   - Or an extrusion
2. Re-run and select correct object

### "Nothing happened"

**Cause:** Building already at correct height

**Fix:**
- Check console output for status messages
- May be working correctly - building already on terrain
- Use View > Zoom Extents to verify

### Script Runs But No Result

**Cause:** Ray sample grid too small or terrain too complex

**Fix:**
```python
RAY_SAMPLE_GRID = 9  # Increase from 5 to 9
```

Then re-run.

## Performance

| Scenario | Time | Notes |
|---|---|---|
| 1 building + terrain | ~2s | Fast |
| 5 buildings + terrain | ~10s | Normal |
| 50 buildings + terrain | ~60s | Batch processing |
| Complex terrain mesh | +30% | More rays to cast |

**Tips for faster processing:**
- Reduce `RAY_SAMPLE_GRID` from 5 to 3 (less accurate)
- Use simpler terrain mesh
- Reduce `RAY_CAST_DISTANCE` if applicable

## Undo/Redo

All building movements in a single run create **ONE undo record:**

```
Ctrl+Z  → Undoes ALL buildings moved in that run
Ctrl+Y  → Redo all movements
```

To move individual buildings:
- Run script once per building
- Then can Ctrl+Z individually

## Advanced Tips

### Batch with Different Terrains

Currently script uses same terrain for all buildings. To use different terrains:

```
Solution: Run script multiple times
  Run 1: Select Terrain1 + Buildings 1-3
  Run 2: Select Terrain2 + Buildings 4-6
  Each run can be Ctrl+Z independently
```

### Preserve Building Heights

If you want buildings to maintain their height above ground:

```python
VERTICAL_OFFSET = 2.5  # All buildings stay 2.5m above terrain
```

### Check Contact Points Visually

After running, buildings should:
1. Touch or just above terrain
2. Not intersect terrain
3. Maintain vertical orientation

If not:
- Ctrl+Z to undo
- Check clearance offset
- Re-run

## FAQ

**Q: Can I move buildings horizontally?**
A: No - this script only moves vertically. For horizontal placement, use Rhino's Move command first.

**Q: Will building angles change?**
A: No - buildings maintain orientation. Only Z (height) changes.

**Q: Can terrain be a solid object?**
A: Yes - Brep, mesh, or extrusion all work. Avoid solid polysurfaces (use outer surface only).

**Q: What if building has multiple levels?**
A: Script positions based on building's lowest point. All levels move together.

**Q: Can I save positions?**
A: Yes - save Rhino file after positioning. Run Ctrl+Z only if you need to revert.

## Support

Check console output (F2 in Rhino) for detailed messages:
- Ray hit locations
- Contact points
- Movement distances
- Any warnings

If issue persists, note the console messages for debugging.

---

**Version:** 1.0 | **Last Updated:** Feb 2026 | **Rhino:** 7+ | **Python:** 2.7 / 3.x
