# Building Placement - Debugging Guide

**If buildings didn't move, use this guide to diagnose.**

## Step 1: Check Console Output

**Open the Rhino Console:**
```
In Rhino: View > Panels > Python Console
Or press: F2
```

Look for output like:
```
============================================================
  TERRAIN-BUILDING PLACEMENT SCRIPT  v1.0.0
============================================================
```

## What Output Should Show

### ✅ Successful Run (Buildings Moved)

```
============================================================
  TERRAIN-BUILDING PLACEMENT SCRIPT  v1.0.0
============================================================

Document units: m | Tolerance: 0.0010

[1/1] Processing Building_Name...
    Terrain sample count: 25 (5x5 grid)
    Terrain Z (highest under footprint): 765.423
    Placement complete.

============================================================
TERRAIN PLACEMENT RESULTS
============================================================
  [OK]   Building_Name -> moved 1.234 m (terrain Z: 765.423m)

Summary: 1 placed, 0 skipped (no terrain), 0 errors
============================================================

Done. 1 building(s) placed on terrain. Use Ctrl+Z to undo.
```

### ⚠️ No Terrain Found

```
[1/1] Processing Building_Name...
    WARNING: No terrain intersections found under building footprint.
    (Building may be outside terrain bounds, or terrain beneath is a hole)

Summary: 0 placed, 1 skipped (no terrain), 0 errors
```

**Fix:** Check that building's X,Y position is directly above terrain

### ⚠️ Already at Terrain Level

```
[1/1] Processing Building_Name...
    Terrain Z (highest under footprint): 765.000
    Building already at terrain level (delta = 0.000000). No move needed.

Summary: 0 placed, 1 skipped, 0 errors
```

**Fix:** Building is already positioned correctly. This is normal!

### ❌ Building is Locked

```
[1/1] Processing Building_Name...
    ERROR: Transform operation failed (object may be locked)

Summary: 0 placed, 0 skipped, 1 error
```

**Fix:** Unlock the building or its layer in Rhino

## Step 2: Verify Your Setup

### Checklist Before Running Script

- [ ] Terrain is loaded in Rhino (visible on screen)
- [ ] Building(s) are loaded in Rhino (visible on screen)
- [ ] Building is positioned ABOVE terrain (not below)
- [ ] Building is not locked (can select and move manually)
- [ ] Terrain is a single object (surface, mesh, or extrusion)

### Check if Terrain Exists

**In Rhino Console:**
```python
# Type this in Python console to list all objects
for obj in sc.doc.Objects:
    if obj.IsValid:
        print(obj.Name, "-", obj.Geometry.GetType().Name)
```

Look for objects with type:
- `Surface` - ✅ Good for terrain
- `Mesh` - ✅ Good for terrain
- `Brep` - ✅ Good for terrain
- `Extrusion` - ✅ Good for terrain

## Step 3: Test Selection

### Make Sure You're Selecting Correctly

**When script asks "Click on terrain":**
1. Click directly ON the terrain object (the surface/mesh)
2. You should see it highlight
3. Press ENTER or click again

**When script asks "Select buildings":**
1. Click on each building
2. Each should highlight as you click
3. When done, press ENTER

## Step 4: Check Building Height

**How far above terrain is the building?**

1. Select the building in Rhino
2. View > Properties
3. Look for "Center" Z value
4. Compare to terrain Z value

**If difference is very small (< 0.01m):**
- Building is already nearly at terrain level
- No visible movement will occur
- This is normal!

## Step 5: Enable Debug Output

Add these lines to the top of `place_building_on_terrain.py`:

```python
# Add this after line 835 (after the header print)
import sys
print("DEBUG: Python version:", sys.version)
print("DEBUG: Rhino document objects:", len(sc.doc.Objects))
print("DEBUG: Valid objects:", sum(1 for o in sc.doc.Objects if o.IsValid))
```

Then run the script again and check the console output.

## Common Problems & Solutions

### Problem: "No terrain intersections found"

**Causes:**
1. Building's X,Y not above terrain
2. Terrain has holes/gaps beneath building
3. Ray sample grid too small

**Solutions:**
```python
# In script, increase ray sample density:
RAY_SAMPLE_GRID = 7  # Changed from 5

# Or move building above terrain in X,Y first
```

### Problem: "Already at terrain level"

**Cause:** Building is already positioned correctly

**Solution:** This is normal! The script worked - no movement needed.

### Problem: "Building is locked"

**Cause:** Building object is locked in Rhino

**Solution:**
1. Right-click building in layer panel
2. Click "Unlock"
3. Re-run script

### Problem: Console shows nothing

**Cause:** Console window not open

**Solution:**
1. Press F2 in Rhino
2. Scroll up to see output
3. Check "Show all" or "Show Recent"

## Step 6: Manual Test

**Try moving a building manually to verify it works:**

1. Select a building
2. Transform > Move (or press M)
3. Select a point, then move up/down
4. Building should move

If manual move doesn't work, the object is locked or invalid.

## Step 7: Create Test Scene

**Simple test to verify script works:**

1. Create terrain:
   ```
   - Draw a rectangle
   - Loft or extrude into a surface
   - Place at Z = 100
   ```

2. Create building:
   ```
   - Draw a small rectangle (smaller than terrain)
   - Extrude upward to 20 units tall
   - Place at Z = 150 (above terrain)
   - Center it on the terrain
   ```

3. Run script:
   ```
   - Select terrain (the surface)
   - Select building (the extrusion)
   - Building should move down to Z = 120
   ```

If this works, your scene is set up correctly.

## Enable Full Debug Mode

Create a debug version with extra output:

**Option 1: Run in Python Editor with Print Statements**

1. Open the script in Rhino Python Editor
2. Before the selection prompts, add:
```python
print("\n=== DEBUG MODE ===")
print("Document objects:", len(sc.doc.Objects))
for obj in sc.doc.Objects:
    if obj.IsValid:
        bbox = obj.Geometry.GetBoundingBox(rg.Transform.Identity)
        print(f"  {obj.Name}: Z range {bbox.Min.Z:.2f} to {bbox.Max.Z:.2f}")
print("=================\n")
```

3. Run with F5
4. Check console (F2) for output

## Still Not Working?

**Please collect this information:**

1. **Console output** - Copy the full output from F2 console
2. **Number of objects** - How many terrain + building objects?
3. **Heights** - What's the Z value of terrain? Building?
4. **File** - If possible, attach the Rhino file to help diagnose

**Then share:**
- The console text
- A screenshot of your scene (View > Zoom Extents, then Print Screen)
- The Rhino file (if small)

## Quick Checklist Summary

```
Before running script:
☐ Terrain is visible in Rhino
☐ Building(s) are visible in Rhino
☐ Building is ABOVE terrain (higher Z)
☐ Building is not locked
☐ Building X,Y is over terrain (not off to the side)

When running script:
☐ Console window (F2) is open
☐ Script prints header message
☐ I select terrain (click on surface)
☐ I select building(s) (click on them)
☐ I see "Placement complete" message

Expected result:
☐ Building moves down
☐ Console shows distance moved
☐ Undo works (Ctrl+Z)
```

---

If your setup passes all checks but still doesn't work, the script might have an issue. Please share:
1. Console output (F2)
2. Scene screenshot
3. Rhino file (if < 10MB)

