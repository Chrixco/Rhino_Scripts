# -*- coding: utf-8 -*-
"""
scene_diagnostic.py - Quick scene setup checker

Run this script BEFORE running the main placement script to verify your setup.

This will check:
1. What objects are in the Rhino document
2. Which are valid terrain objects
3. Which are valid building objects
4. Heights and positions of each
"""

import rhinoscriptsyntax as rs
import scriptcontext as sc
import Rhino.Geometry as rg

print("\n" + "=" * 70)
print("SCENE DIAGNOSTIC - BUILDING PLACEMENT SETUP CHECKER")
print("=" * 70)

# Get document
doc = sc.doc
print("\nDocument Settings:")
print("  Units: {}".format(rs.UnitSystemName(abbreviate=True)))
print("  Tolerance: {}".format(doc.ModelAbsoluteTolerance))

# Count all objects
all_objs = [o for o in doc.Objects if o.IsValid and not o.IsDeleted]
print("\nTotal valid objects: {}".format(len(all_objs)))

if len(all_objs) == 0:
    print("\n⚠ WARNING: No objects found in document!")
    print("Please load your terrain and buildings first.")
else:
    # Categorize objects
    terrain_types = ["Surface", "Brep", "Mesh", "Extrusion"]
    building_types = ["Brep", "Extrusion", "Mesh"]

    terrains = []
    buildings = []
    other = []

    print("\n" + "-" * 70)
    print("OBJECT INVENTORY:")
    print("-" * 70)

    for obj in all_objs:
        try:
            name = obj.Name if obj.Name else "<unnamed>"
            geom_type = obj.Geometry.GetType().Name
            bbox = obj.Geometry.GetBoundingBox(rg.Transform.Identity)

            z_min = bbox.Min.Z
            z_max = bbox.Max.Z
            z_height = z_max - z_min

            # Determine category
            is_terrain = False
            is_building = False

            if "Mesh" in geom_type or "Surface" in geom_type:
                is_terrain = True
                terrains.append((name, geom_type, z_min, z_max))
            elif "Brep" in geom_type or "Extrusion" in geom_type:
                is_building = True
                buildings.append((name, geom_type, z_min, z_max, z_height))
            else:
                other.append((name, geom_type))

            # Print object info
            if is_terrain:
                marker = "🌍 TERRAIN"
            elif is_building:
                marker = "🏢 BUILDING"
            else:
                marker = "❓ OTHER"

            print("\n{}  {}".format(marker, name))
            print("   Type: {}".format(geom_type))
            print("   Z: {:.3f} to {:.3f}".format(z_min, z_max))
            if z_height > 0:
                print("   Height: {:.3f}".format(z_height))

        except Exception as e:
            print("\n❌ ERROR reading object: {}".format(e))

    # Summary
    print("\n" + "=" * 70)
    print("SUMMARY:")
    print("=" * 70)
    print("\n✓ Terrain objects: {}".format(len(terrains)))
    for name, geom_type, z_min, z_max in terrains:
        print("    - {} ({}) at Z: {:.2f}-{:.2f}".format(name, geom_type, z_min, z_max))

    print("\n✓ Building objects: {}".format(len(buildings)))
    for name, geom_type, z_min, z_max, height in buildings:
        print("    - {} ({}) at Z: {:.2f}-{:.2f} (height: {:.2f})".format(
            name, geom_type, z_min, z_max, height))

    if len(other) > 0:
        print("\n❓ Other objects: {}".format(len(other)))
        for name, geom_type in other:
            print("    - {} ({})".format(name, geom_type))

    # Recommendations
    print("\n" + "=" * 70)
    print("RECOMMENDATIONS:")
    print("=" * 70)

    if len(terrains) == 0:
        print("\n❌ No terrain found!")
        print("   ACTION: Load or create a terrain (surface, mesh, or extrusion)")
    elif len(terrains) > 1:
        print("\n⚠ Multiple terrain objects found: {}".format(len(terrains)))
        print("   ACTION: The script will use the first one selected")
    else:
        print("\n✓ Terrain: {} object(s) found".format(len(terrains)))

    if len(buildings) == 0:
        print("\n❌ No buildings found!")
        print("   ACTION: Load or create buildings (extrusions or Breps)")
    else:
        print("\n✓ Buildings: {} object(s) found".format(len(buildings)))

    # Check building/terrain relationships
    if len(terrains) > 0 and len(buildings) > 0:
        print("\n" + "-" * 70)
        print("BUILDING-TERRAIN RELATIONSHIP:")
        print("-" * 70)

        terrain_z_min, terrain_z_max = terrains[0][2], terrains[0][3]

        for bldg_name, bldg_type, bldg_z_min, bldg_z_max, bldg_height in buildings:
            above = bldg_z_min - terrain_z_max

            print("\n{} vs {} ({})".format(bldg_name, terrains[0][0], terrains[0][1]))
            print("  Building base (Z={:.2f}) vs Terrain top (Z={:.2f})".format(
                bldg_z_min, terrain_z_max))
            print("  Gap: {:.2f}".format(above))

            if above > 0.1:
                print("  ✓ Building is above terrain (good for placement)")
            elif above > 0:
                print("  ⚠ Building is just barely above terrain")
            elif above > -0.1:
                print("  ⚠ Building is nearly touching terrain")
            else:
                print("  ❌ Building is BELOW terrain (may have issues)")

print("\n" + "=" * 70)
print("Ready to run the placement script!")
print("=" * 70 + "\n")
