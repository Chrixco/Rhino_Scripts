# Road Topography Adapter

**Location:** `/Users/chcorral/rhino_scripts/03_road_topography_adapter/`

**Main Script:** `adapt_road_to_topography.py`

## Overview

Adapts 2D road geometry (with thickness/width) to follow topographic terrain. Projects a road centerline onto terrain, creates perpendicular cross-sections at regular intervals, and lofts them together to create a 3D road surface that smoothly follows the terrain slope.

## Features

✅ **Project centerline to terrain** - Uses RhinoCommon projection
✅ **Perpendicular cross-sections** - Automatically oriented perpendicular to road direction
✅ **Terrain-aware banking** - Road surface banks with terrain slope
✅ **Smooth lofting** - Creates NURBS surface between cross-sections
✅ **Handles complex roads** - Works with curved, looped, and winding roads
✅ **Layer organization** - Separate layers for surface, centerline, debug geometry
✅ **Edge case handling** - Cliffs, holes in terrain, steep slopes
✅ **Full undo support** - Ctrl+Z to revert

## Approach

**Algorithm: Project Centerline → Create Cross-Sections → Loft**

```
1. Extract road centerline from 2D road geometry
   ├─ If input is curve: use directly
   ├─ If input is closed polyline: extract centerline
   └─ If input is surface: extract centerline curve

2. Project centerline onto terrain surface
   └─ Result: 3D curve following terrain

3. Sample projected centerline at regular intervals
   ├─ Points: every N meters (default 5m)
   ├─ Data: point, tangent, terrain normal
   └─ Result: array of sample stations

4. Create perpendicular cross-section at each station
   ├─ Plane perpendicular to road direction
   ├─ Banking angle from terrain slope
   ├─ Width offset (road width / 2)
   └─ Result: road profile curve (left edge, center, right edge)

5. Loft between all cross-sections
   ├─ Ensure curve direction consistency
   ├─ Create NURBS surface
   └─ Result: 3D road surface

6. Output to layers with documentation
```

## Quick Start

### 1. **Prepare Your Scene**

In Rhino, you need:
- **Terrain:** DEM surface, mesh, or extrusion
- **Road:** 2D centerline (polyline or curve)

Example setup:
```
Terrain layer: "Terrain" (surface)
Road layer: "Roads" (2D centerline polyline)
```

### 2. **Open Python Editor**

```
Tools > Python Script > Edit
```

### 3. **Load Script**

```
File > Open > /Users/chcorral/rhino_scripts/03_road_topography_adapter/adapt_road_to_topography.py
```

### 4. **Run**

```
Press F5  OR  Click "Run" button
```

### 5. **Follow Dialogs**

**Dialog 1: Terrain Layer**
```
"Terrain layer name? (default: Terrain)"
```
- Press ENTER for default
- Or type your terrain layer name

**Dialog 2: Road Geometry**
```
"Select road centerline or closed road polygon"
```
- Click on your road curve
- Press ENTER

**Dialog 3: Road Width**
```
"Road width in model units? (default: 10.0)"
```
- Enter width (e.g., 10 for 10m road)
- Press ENTER

**Dialog 4: Sample Spacing**
```
"Sample spacing (distance between cross-sections)? (default: 5.0)"
```
- Enter spacing (e.g., 5 for cross-section every 5m)
- Press ENTER

**Dialog 5: Height Offset**
```
"Height offset above terrain? (default: 0.0)"
```
- Enter clearance (0 for flush, 0.1 for 10cm)
- Press ENTER

**Dialog 6: Cross-Section Profile Points**
```
"Road profile density?"
  [1] 3 points  (fast)
  [2] 5 points  (balanced)
  [3] 7 points  (detailed)
  [4] 9 points  (very detailed)
```
- Select option (default: 5 points)

**Dialog 7: Include Debug Sections**
```
"Show cross-section curves for debugging?"
  [1] Yes
  [2] No
```
- Choose to visualize cross-sections (optional)

### 6. **Processing**

```
Road Adaptation to Topography v1.0
============================================================

Input Analysis:
  Terrain: Terrain_DEM (Brep)
  Road: Road_01 (Curve)
  Road width: 10.00 m
  Sample spacing: 5.00 m

Projection:
  Projecting centerline to terrain...
  Centerline length: 245.67 m
  Z range: 750.23 to 762.84 m (elevation change: 12.61 m)

Cross-Sections:
  Samples created: 50
  Cross-sections generated: 50

Lofting:
  Creating road surface...
  Road surface created: valid NURBS surface

Summary:
  ✓ Road surface successfully adapted to topography
  ✓ Use Ctrl+Z to undo
============================================================
```

### 7. **Result**

New layers created:
```
Roads_Projected      → 3D road surface following terrain
Roads_Centerline     → Projected centerline (reference)
Roads_CrossSections  → Cross-section profiles (debug, optional)
```

## Output Layers

### **Roads_Projected** (Main Output)
- NURBS surface representing the 3D road
- Smoothly follows terrain
- Maintains road width and slope
- Color: Cyan
- Print weight: 0.5mm

### **Roads_Centerline** (Reference)
- 3D centerline projected onto terrain
- Useful for road alignment verification
- Color: Green

### **Roads_CrossSections** (Debug)
- Individual cross-section curves at each sample point
- Shows how road banks with terrain
- Optional display
- Color: Yellow

## Configuration

Edit these constants in the script for different behavior:

```python
DEFAULT_SAMPLE_SPACING      = 5.0   # Distance between cross-sections (m)
DEFAULT_ROAD_WIDTH          = 10.0  # Road width if not specified (m)
DEFAULT_HEIGHT_OFFSET       = 0.0   # Clearance above terrain (m)
DEFAULT_CROSS_SECTION_POINTS = 3    # Profile points (3/5/7/9)
RAY_CAST_DISTANCE           = 10000.0  # Ray casting distance
MAX_TERRAIN_SLOPE_DEG       = 80.0  # Fallback threshold for steep slopes
```

## Example Workflows

### Workflow 1: Simple Road

```
1. Draw 2D road centerline (polyline)
2. Position above terrain
3. Run script
4. Use all defaults
5. Done!
```

**Result:** 3D road following terrain

---

### Workflow 2: Multi-Lane Highway

```
1. Draw centerline for highway
2. Set road width: 30.0 (for 30m wide highway)
3. Set sample spacing: 10.0 (wider spacing = smoother surface)
4. Set cross-section points: 7 (more points = more detail)
5. Run script
```

**Result:** Wide 3D highway with smooth banking

---

### Workflow 3: Winding Mountain Road

```
1. Draw curved/winding centerline
2. Set road width: 8.0 (narrow mountain road)
3. Set sample spacing: 2.0 (tight spacing for curves)
4. Set cross-section points: 9 (maximum detail)
5. Enable debug sections to visualize banking
6. Run script
```

**Result:** Detailed road with tight curves and banking

---

### Workflow 4: Road with Foundation

```
1. Draw road centerline
2. Set height offset: 0.5 (50cm above terrain)
3. This creates a road sitting on a 50cm foundation
4. Run script
```

**Result:** Road elevated above terrain by specified height

## Troubleshooting

### "Road does not intersect terrain"

**Causes:**
- Road centerline outside terrain bounds
- Terrain too small
- Road far from terrain

**Solutions:**
- Check that road X,Y position overlaps terrain
- Zoom to fit to verify positions
- Use smaller sample spacing

### "No cross-sections generated"

**Causes:**
- Sample spacing too large for road length
- Road too short

**Solutions:**
- Reduce sample spacing (e.g., 5.0 → 1.0)
- Make sure road is longer than spacing
- Check console for error messages

### "Loft failed / surface invalid"

**Causes:**
- Cross-sections not properly oriented
- Road curves too sharply
- Terrain too chaotic

**Solutions:**
- Increase sample spacing (smoother sections)
- Enable debug sections to visualize
- Simplify road geometry
- Reduce cross-section profile points

### "Road floating above terrain"

**Causes:**
- Height offset set too high
- Terrain projection failed

**Solutions:**
- Set height offset to 0.0
- Check that terrain is valid
- Verify road is above terrain before running

### "Banking looks wrong"

**Causes:**
- Steep terrain confuses normal calculation
- Road curves sharply

**Solutions:**
- Reduce sample spacing
- Enable debug sections to visualize
- Check terrain normal estimation
- Adjust MAX_TERRAIN_SLOPE_DEG if needed

## Advanced Features

### Debug Mode

Enable "Roads_CrossSections" layer to see:
- How road banks with terrain
- Cross-section placement
- Profile point locations
- Useful for troubleshooting

### Manual Adjustments

After generation, you can:
1. Edit road surface with **Gumball** for fine-tuning
2. Use **Blend Surfaces** to smooth transitions
3. Add **Pavement texture** to Roads_Projected layer
4. Combine with drainage analysis using contours

### Road Variations

Create variations by running script multiple times:
- Different road widths
- Different sample spacings
- Different height offsets

Use Ctrl+Z to undo and try different parameters.

## Performance

| Scenario | Time | Notes |
|----------|------|-------|
| Simple 100m road, 5m spacing | ~5s | Fast |
| Complex 500m road, 2m spacing | ~15s | Moderate |
| Very detailed, 1m spacing | ~30s | Slower |

**Tips for faster processing:**
- Increase sample spacing (5→10)
- Reduce cross-section profile points (9→5)
- Simplify terrain mesh if possible
- Close other applications

## Technical Details

### Supported Terrain Types

✅ **Brep Surfaces** - NURBS surfaces, polysurfaces
✅ **Mesh** - DEM grids, triangulated terrain
✅ **Extrusions** - Converted to Brep internally

### Supported Road Input

✅ **Polyline/Curve** - Used as centerline
✅ **Closed Curve** - Centerline extracted
✅ **Surface** - Centerline curve extracted

### Coordinate Systems

- Supports any Rhino coordinate system
- Maintains original units (meters, feet, etc.)
- Works with large coordinates (UTM, etc.)

### Undo Support

All operations wrapped in single undo block:
```
Ctrl+Z  → Undoes entire road generation
Ctrl+Y  → Redo
```

## FAQ

**Q: Can I use this for hiking trails?**
A: Yes! Just set road width smaller (e.g., 2m for trail).

**Q: Can I export the result?**
A: Yes! Export surface as DXF, STEP, or any Rhino format.

**Q: What if road has multiple lanes?**
A: Set road width to total width (all lanes).

**Q: Can I edit the road after creation?**
A: Yes! Surface is NURBS, fully editable in Rhino.

**Q: Does it work with very steep terrain?**
A: Yes, but results may need adjustment. Use debug mode to check.

**Q: Can I combine multiple roads?**
A: Yes! Run script separately, then join surfaces or use Bridge.

## Support

For issues or questions:
1. Check console output (F2) for error messages
2. Enable debug sections to visualize geometry
3. Check GitHub repository issues
4. Review troubleshooting section above

---

**Version:** 1.0 | **Last Updated:** Feb 2026 | **Rhino:** 7+ | **Python:** 2.7 / 3.x
