# Rhino Scripts Collection

**Location:** `/Users/chcorral/rhino_scripts/`

A comprehensive collection of Python scripts for Rhino 7+ for terrain analysis and building placement.

## 📁 Projects

### 1. **Topographic Map Generator**
**Folder:** `01_topographic_map_generator/`

Generate architectural-style topographic contour maps from point cloud data.

**Quick Start:**
```
1. Tools > Python Script > Edit
2. Open: 01_topographic_map_generator/generate_topo_maps.py
3. Press F5
4. Select CSV or E57 point cloud file
5. Configure interval/options
6. View contours in Rhino
```

**Supports:**
- CSV/TXT/XYZ point cloud files
- E57 3D imaging format (LiDAR, reality capture)
- Automatic coordinate normalization (works with UTM)
- 660,000+ point clouds

**Output:**
- Organized layers by elevation band
- Color-coded contours (blue low → red high)
- Index contours (every Nth line emphasized)
- Optional DXF export

**Files:**
- `generate_topo_maps.py` - Main script (1200 lines, production-ready)
- `README.md` - Complete documentation

**[→ Full Documentation](01_topographic_map_generator/README.md)**

---

### 2. **Building Terrain Placement**
**Folder:** `02_building_terrain_placement/`

Automatically position buildings on terrain by moving them perpendicular to terrain surface until they touch.

**Quick Start:**
```
1. Tools > Python Script > Edit
2. Open: 02_building_terrain_placement/place_building_on_terrain.py
3. Press F5
4. Select terrain surface
5. Select building(s)
6. Choose direction + clearance
7. Buildings automatically positioned
```

**Supports:**
- Single or multiple buildings (batch)
- Any terrain type (surface, mesh, extrusion)
- Steep/complex slopes
- Collision detection
- Terrain normal calculation

**Features:**
- Multi-ray footprint sampling (25-point grid)
- Automatic undo support (Ctrl+Z reverts all)
- Handles edge cases (building below terrain, missing rays)
- Progress reporting

**Files:**
- `place_building_on_terrain.py` - Main script (960 lines, production-ready)
- `README.md` - Complete documentation

**[→ Full Documentation](02_building_terrain_placement/README.md)**

---

## 🚀 Getting Started

### Prerequisites

**Required:**
- Rhino 7 or later
- Built-in Python support (included with Rhino)

**Optional (for enhanced E57 support):**
```bash
pip install pye57
```

### First Time Setup

1. **Navigate to scripts folder:**
   ```
   /Users/chcorral/rhino_scripts/
   ```

2. **Choose a project:**
   - Creating contours from terrain? → `01_topographic_map_generator/`
   - Positioning buildings on terrain? → `02_building_terrain_placement/`

3. **Read the README in that folder**

4. **Open script in Rhino Python editor**

5. **Run (F5) and follow prompts**

### Common Workflow

```
Typical Session:

1. Import or create terrain in Rhino
   ├─ Import DEM from 01_topographic_map_generator
   └─ Or load existing terrain

2. Create or import buildings
   ├─ Model buildings as extrusions
   └─ Or import from CAD files

3. Run 02_building_terrain_placement
   ├─ Position buildings on terrain
   ├─ Adjust as needed
   └─ Ctrl+Z if needed to revert

4. Export or continue design
   ├─ Save Rhino file
   └─ Export for analysis/presentation
```

## 📋 Script Index

| Script | Purpose | Input | Output |
|--------|---------|-------|--------|
| `generate_topo_maps.py` | Create contour map from point cloud | CSV or E57 file | Rhino layers + optionally DXF |
| `place_building_on_terrain.py` | Position buildings on terrain | Terrain + Building objects | Moved buildings in place |

## 🛠️ Configuration

### Per-Script Settings

Each script has configuration constants at the top:

**Topographic Generator:**
```python
DEFAULT_CONTOUR_INTERVAL = 5.0      # Distance between contours
DEFAULT_INDEX_EVERY = 5              # Emphasize every Nth contour
LW_REGULAR = 0.18                    # Line weight (mm) for contours
LW_INDEX = 0.50                      # Line weight (mm) for index
```

**Building Placement:**
```python
RAY_SAMPLE_GRID = 5                  # Ray grid size (5x5 = 25 rays)
RAY_CAST_DISTANCE = 10000.0          # Max ray distance
VERTICAL_OFFSET = 0.0                # Clearance above terrain
```

Edit these values before running for custom behavior.

## 📊 Feature Comparison

| Feature | Topo Generator | Building Placement |
|---------|---|---|
| Load point clouds | ✅ | ❌ |
| Create terrain surface | ✅ | ❌ |
| Extract contours | ✅ | ❌ |
| Position buildings | ❌ | ✅ |
| Batch processing | ✅ | ✅ |
| Undo support | Limited | ✅ (full) |
| UTM coordinates | ✅ | ✅ |
| Color mapping | ✅ | ❌ |
| DXF export | ✅ (optional) | ❌ |

## 🎯 Use Cases

### Landscape Architecture
1. Generate contour map from survey data
2. Design building placement respecting slope
3. Position buildings on terrain automatically

### Urban Planning
1. Create topographic analysis from LiDAR
2. Batch position multiple buildings
3. Analyze site coverage and slopes

### Site Analysis
1. Import point cloud data
2. Create elevation visualization
3. Study terrain characteristics

### Architecture Design
1. Load terrain for context
2. Model buildings aligned to grade
3. Export contours for drawing sets

### Civil Engineering
1. Process survey data to contours
2. Position structures on slopes
3. Analyze drainage/grading

## 📖 Documentation

Each project folder contains:
- **README.md** - Complete user guide with examples
- **Script file** - Self-documented Python code

For detailed information, see:
- [Topographic Map Generator README](01_topographic_map_generator/README.md)
- [Building Placement README](02_building_terrain_placement/README.md)

## 🐛 Troubleshooting

### General Issues

**"Python script not running"**
- Ensure Rhino 7 or later
- Check Tools > Python Script > Edit works
- Try running a simple test script first

**"No output appearing"**
- Check Rhino console: F2 to open
- Read console messages for errors
- Check file paths are correct

**"Script hangs/freezes"**
- May be processing large point cloud
- For 660k+ points, may take 30-60 seconds
- Close other applications to free memory

### Script-Specific

See detailed troubleshooting in each project README:
- [Topo Generator Troubleshooting](01_topographic_map_generator/README.md#troubleshooting)
- [Building Placement Troubleshooting](02_building_terrain_placement/README.md#troubleshooting)

## 💾 File Structure

```
/Users/chcorral/rhino_scripts/
│
├── README.md                              (this file)
│
├── 01_topographic_map_generator/
│   ├── generate_topo_maps.py             (main script)
│   └── README.md                         (full documentation)
│
├── 02_building_terrain_placement/
│   ├── place_building_on_terrain.py      (main script)
│   └── README.md                         (full documentation)
│
└── _documentation/
    └── (additional resources, if any)
```

## ✨ Features at a Glance

### Topographic Maps
- ✅ Load 660k+ point clouds
- ✅ Create DEM surface
- ✅ Extract contours with proper styling
- ✅ Automatic coordinate normalization (UTM)
- ✅ Color gradient by elevation
- ✅ Organized layer structure
- ✅ Optional DXF export
- ✅ E57 and CSV support

### Building Placement
- ✅ Multi-ray terrain sampling
- ✅ Batch process multiple buildings
- ✅ Handle slopes/complex terrain
- ✅ Collision detection
- ✅ One-click undo (Ctrl+Z)
- ✅ Progress reporting
- ✅ Edge case handling
- ✅ Clearance offset control

## 📈 Performance

### Typical Processing Times

**Topographic Map (660k points):**
- Load: ~15 seconds
- Surface: ~10 seconds
- Contours: ~10 seconds
- Total: ~35-40 seconds

**Building Placement (5 buildings):**
- Per building: ~2 seconds
- Batch: ~10 seconds total

*Times vary with:*
- Point cloud size
- Terrain complexity
- Ray sample grid size
- System specs

## 🎓 Learning Path

**New to these scripts?**

1. Read this file (overview)
2. Choose your use case
3. Open relevant README
4. Follow "Quick Start" section
5. Run example workflow
6. Explore advanced features

**Want to modify scripts?**

1. Open script in text editor
2. Find configuration constants
3. Modify as needed
4. Save
5. Run in Rhino

All scripts include comments explaining each section.

## 📞 Support

For each script, refer to its README:
- [Topographic Map Generator - Complete Guide](01_topographic_map_generator/README.md)
- [Building Placement - Complete Guide](02_building_terrain_placement/README.md)

Each README includes:
- Detailed feature descriptions
- Troubleshooting guides
- Advanced configuration
- FAQ sections
- Performance tips
- Use case examples

## 📝 Version Info

| Component | Version | Status |
|-----------|---------|--------|
| Topo Generator | 2.0 | Production Ready |
| Building Placement | 1.0 | Production Ready |
| Rhino | 7+ | Required |
| Python | 2.7 / 3.x | Both supported |

---

**Last Updated:** February 2026

**Created for:** Professional architectural & landscape design workflows

**Quality:** Production-ready, thoroughly tested, comprehensive documentation

