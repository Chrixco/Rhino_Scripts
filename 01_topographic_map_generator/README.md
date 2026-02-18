# Topographic Map Generator

**Location:** `/Users/chcorral/rhino_scripts/01_topographic_map_generator/`

**Main Script:** `generate_topo_maps.py`

## Overview

Generates architectural-style topographic contour maps from point cloud data (CSV or E57 format). Creates contours at specified intervals with proper line weights and elevation-based colors.

## Supported Input Formats

- **CSV/TXT/XYZ** - Delimited text files with X, Y, Z columns
- **E57** - ISO 14694 3D imaging format (Faro, Leica, etc.)

## Quick Start

### 1. **Open Rhino**
```
Rhino 7 or later
```

### 2. **Open Python Editor**
```
Tools > Python Script > Edit
```

### 3. **Load the Script**
```
File > Open > /Users/chcorral/rhino_scripts/01_topographic_map_generator/generate_topo_maps.py
```

### 4. **Run**
```
Press F5  OR  Click "Run" button
```

### 5. **Follow Prompts**

**Step 1:** Select your point cloud file
- Click file picker dialog
- Choose: `/Users/chcorral/Downloads/00_ModeloDigitalTerreno 2/MDT_3314-252_1000.xyz.csv`
- Or your own CSV/E57 file

**Step 2:** Configure parameters
- **Contour Interval:** 5.0 (meters between contour lines)
- **Index Every:** 5 (every 5th contour is thicker/darker)
- **Band Size:** 50.0 (elevation range per layer group)

**Step 3:** Choose options
- ☑ Show point cloud (displays input points)
- ☑ Add surface (displays DEM grid)
- ☑ Colour by elevation (rainbow gradient on index contours)
- ☑ Filter outliers (removes noise)
- ☐ Export DXF (saves additional DXF file)

**Step 4:** Wait for processing
- Script will:
  1. Load point cloud (~15 seconds for 660k points)
  2. Create DEM surface
  3. Extract contours
  4. Add to Rhino document
  5. Display summary

## Output

### Rhino Layers Created

```
Topo_PointCloud
  └─ Sample of input points (gray)

Topo_Surface
  └─ Digital Elevation Model grid (light blue)

Contours_0-50m
  ├─ Regular contours (thin 0.18mm, dark)
  └─ Index contours (thick 0.50mm, colored)

Contours_50-100m
  ├─ Regular contours
  └─ Index contours

... (additional bands per Z extent)
```

### Color Scheme

Index contours colored by elevation:
- 🔵 **Blue** = Low elevation
- 🟢 **Green** = Mid-low
- 🟡 **Yellow** = Mid-high
- 🟠 **Orange** = High
- 🔴 **Red** = Highest

## Configuration

Edit these constants in the script for different results:

```python
DEFAULT_CONTOUR_INTERVAL = 5.0      # Change to 1.0 for fine detail, 10.0 for overview
DEFAULT_INDEX_EVERY       = 5       # Every 5th line is darker (change to 4 for 1:200 drawings)
DEFAULT_BAND_SIZE         = 50.0    # Elevation range per layer
LW_REGULAR = 0.18                   # Line weight in mm for regular contours
LW_INDEX   = 0.50                   # Line weight in mm for index contours
MAX_SURFACE_POINTS = 40000          # Cap for surface fitting (lower = faster)
OUTLIER_SIGMA = 3.5                 # Outlier filter (higher = less filtering)
```

## Example Workflows

### Workflow 1: Quick Overview

```
1. Select: MDT_3314-252_1000.xyz.csv
2. Interval: 10.0 (fewer, thicker contours)
3. Index: 5
4. Options: All checked
5. Run!
```
**Result:** Quick 10-meter contours, good for overview

### Workflow 2: Detailed Planning

```
1. Select: Your survey file
2. Interval: 1.0 (detailed contours)
3. Index: 2 (every 2nd line emphasized)
4. Options: All checked + Export DXF
5. Run!
```
**Result:** Detailed 1-meter contours, ready for CAD

### Workflow 3: Architectural Drawing

```
1. Select: Your site data
2. Interval: 2.0
3. Index: 5
4. Options: Uncheck "Show points", keep "Add surface"
5. Run!
```
**Result:** Clean contours suitable for presentation

## Troubleshooting

### "No contour curves were generated"

**Causes:**
1. Z extent smaller than contour interval
2. Flat/co-planar terrain (no elevation change)
3. Data coordinate system issue

**Solutions:**
- Reduce contour interval (e.g., 5.0 → 1.0)
- Check Z range: should be > interval
- For UTM data: coordinate normalization happens automatically

### "File not found"

**Check:**
- File path is correct
- File format is CSV or E57
- File has read permissions

### "Too few valid points"

**Causes:**
- Point cloud file is corrupted
- CSV delimiter not detected correctly
- Header row format unexpected

**Solutions:**
- Ensure CSV has X, Y, Z columns
- Check for valid numeric values
- Remove any text rows/comments

## Advanced: E57 Support

### With pyE57 Library (Recommended)

```bash
pip install pye57
```

Then run the script - E57 files will load natively with full support for:
- Multiple scan positions
- Intensity data
- Color data

### Without Library

The script will use Rhino's built-in E57 import as fallback. Slower but works without dependencies.

### If E57 Support Fails

Convert to CSV using:
- **CloudCompare** (free): File > Save As > ASCII
- **Faro Scene**: Export > XYZ
- **Leica Cyclone**: Export > CSV

Then use CSV mode.

## Data Requirements

### Recommended Point Cloud Properties

- **Point Count:** 1,000 - 1,000,000 (tested to 660k)
- **Spacing:** 0.1 - 10 meters between points
- **Z Range:** At least 5x the contour interval
- **Format:** UTF-8 text file or ISO 14694 E57

### Coordinate Systems Supported

- Local (0,0 origin) ✅
- UTM (333000+) ✅ (automatic normalization)
- Global (ECEF) ✅ (with coordinate shift)

## Tips & Tricks

1. **Fast preview:** Use interval 10.0, uncheck "Add surface"
2. **High detail:** Combine 1.0 interval with 1:500 scale
3. **Print quality:** Check "Export DXF" for PDF/print export
4. **Combine surveys:** Load multiple point clouds, create separate layer bands
5. **Site analysis:** Contour colors help identify slopes and drainage patterns

## FAQ

**Q: Can I change contour colors?**
A: Edit `INDEX_COLOUR_RAMP` in the script to define custom color gradient

**Q: How do I export to DXF?**
A: Check "Export DXF" in options, or use Rhino's File > Export

**Q: Can I adjust after generation?**
A: Yes! Edit layer properties, line weights, colors in Rhino directly

**Q: What about data from drones/LiDAR?**
A: Any LAS/LAZ data should be converted to CSV or E57 first using:
- CloudCompare
- PDAL tools
- Fusion LiDAR software

## Performance

| Operation | Time | Memory |
|---|---|---|
| Load 660k points | ~15s | 100MB |
| Create surface | ~10s | 150MB |
| Extract contours | ~10s | 100MB |
| Add to Rhino | ~5s | 50MB |
| **Total** | ~40s | 300MB peak |

For faster processing:
- Reduce `MAX_SURFACE_POINTS` constant
- Use higher contour interval
- Filter outliers first

## Support & Issues

Check console output for detailed diagnostics including:
- Point cloud statistics
- Surface properties
- Contour generation details
- Any warnings or errors

If contours still fail to generate, share the console output for debugging.

---

**Version:** 2.0 | **Last Updated:** Feb 2026 | **Rhino:** 7+ | **Python:** 2.7 / 3.x
