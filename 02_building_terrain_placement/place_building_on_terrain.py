# =============================================================================
# place_building_on_terrain.py
# =============================================================================
# Terrain-Building Vertical Placement Script for Rhino Python
#
# PURPOSE:
#   Moves one or more building objects downward (along world Z) until each
#   building's lowest point contacts the terrain surface directly beneath it.
#   The algorithm performs a vertical ray-cast from beneath each building's
#   bounding box base and projects the building to rest on the terrain.
#
# WORKFLOW:
#   1. Script asks for terrain layer name (default: "Terrain")
#   2. Script asks for buildings layer name (default: "Buildings")
#   3. All objects on each layer are detected automatically - no clicking
#   4. First object on the terrain layer is used as the terrain surface
#   5. All objects on the buildings layer are seated on the terrain
#   6. Results are reported; full undo support is provided
#
# LAYER-BASED DETECTION:
#   - Objects are discovered via layer name using rs.ObjectsByLayer()
#   - No manual selection is required; run the script and press Enter twice
#     to accept the defaults "Terrain" and "Buildings"
#   - Terrain and building objects may be any geometry type supported by the
#     original script (surface, polysurface, mesh, extrusion, block instance)
#
# CONSTRAINTS ASSUMED:
#   - World Z = up (standard architectural workflow)
#   - Buildings are already positioned above the terrain in X,Y
#   - The "Terrain" layer contains exactly one terrain object (first is used)
#   - The "Buildings" layer contains one or more building objects
#   - Terrain is a single continuous surface, polysurface, or mesh object
#   - Buildings may be meshes, Breps, extrusions, or block instances
#
# AUTHOR:  Rhino Python Script
# VERSION: 2.0.0
# TARGET:  Rhino 7+ (rhinoscriptsyntax + RhinoCommon)
# CHANGES: v2.0.0 - Replaced manual object selection with layer-based detection
# =============================================================================

import rhinoscriptsyntax as rs
import Rhino
import Rhino.Geometry as rg
import scriptcontext as sc
import System


# =============================================================================
# CONFIGURATION CONSTANTS
# =============================================================================

# Number of sample rays cast per building footprint to find terrain contact.
# Higher values are slower but handle irregular terrain better.
# 9 = 3x3 grid (fast), 25 = 5x5 grid (thorough), 49 = 7x7 grid (precise)
RAY_SAMPLE_GRID = 5  # NxN grid of vertical rays per building

# Vertical search distance: how far above/below to cast rays.
# Should exceed the maximum expected vertical distance between building base
# and terrain. Units match the Rhino document units.
RAY_CAST_DISTANCE = 10000.0

# Tolerance for geometry operations (matched to Rhino document tolerance).
# Will be overridden at runtime by sc.doc.ModelAbsoluteTolerance.
DEFAULT_TOLERANCE = 0.001

# If True, the script will leave original building positions as reference
# objects (hidden, locked) before moving. Set False for clean workflow.
KEEP_POSITION_REFERENCE = False

# Offset applied after seating the building on terrain (positive = lift above).
# Use 0.0 for flush contact. Increase for a foundation gap.
VERTICAL_OFFSET = 0.0

# Default layer names used when the user presses Enter without typing.
DEFAULT_TERRAIN_LAYER   = "terrain"
DEFAULT_BUILDINGS_LAYER = "buildings"


# =============================================================================
# LAYER UTILITIES
# =============================================================================

def get_objects_from_layer(layer_name):
    """
    Returns all Rhino object GUIDs that reside on the named layer.

    Uses rs.ObjectsByLayer() which returns objects on the layer itself.
    Sub-layer objects are NOT included unless their full path is specified.

    If the layer does not exist in the document, an empty list is returned
    and a warning is printed so the caller can provide a clear error message.

    Parameters
    ----------
    layer_name : str
        The exact layer name as it appears in the Rhino layer panel.
        For nested layers use the full path syntax: "Parent::Child".

    Returns
    -------
    list of System.Guid
        Possibly empty if the layer does not exist or has no objects.
    """
    # Verify the layer exists before querying its objects
    if not rs.IsLayer(layer_name):
        print("  Warning: Layer '{}' does not exist in this document.".format(
            layer_name
        ))
        return []

    objects = rs.ObjectsByLayer(layer_name)
    if objects is None:
        return []

    return list(objects)


def list_layer_summary(layer_name):
    """
    Prints a one-line summary of what was found on a layer.

    Parameters
    ----------
    layer_name : str
    """
    objects = get_objects_from_layer(layer_name)
    if not objects:
        print("  Layer '{}': 0 objects found.".format(layer_name))
    else:
        print("  Layer '{}': {} object(s) found.".format(
            layer_name, len(objects)
        ))


# =============================================================================
# GEOMETRY UTILITIES
# =============================================================================

def get_object_bounding_box(obj_id):
    """
    Returns the world-space bounding box of any Rhino object.

    Handles all geometry types by going through the RhinoCommon geometry
    object rather than relying on rs type-specific methods.

    Parameters
    ----------
    obj_id : System.Guid
        The Rhino object identifier.

    Returns
    -------
    Rhino.Geometry.BoundingBox or None
        World-aligned bounding box, or None if the object is invalid.
    """
    obj = sc.doc.Objects.Find(obj_id)
    if obj is None:
        return None

    bbox = obj.Geometry.GetBoundingBox(rg.Transform.Identity)
    if not bbox.IsValid:
        return None

    return bbox


def get_terrain_as_brep(terrain_id):
    """
    Extracts the terrain object as a RhinoCommon Brep (if surface/polysurface)
    or returns the mesh directly for ray intersection.

    Returns the actual geometry object and a type string.

    Parameters
    ----------
    terrain_id : System.Guid

    Returns
    -------
    tuple : (geometry_object, type_string)
        geometry_object is Brep, Mesh, or None.
        type_string is 'brep', 'mesh', or None.
    """
    obj = sc.doc.Objects.Find(terrain_id)
    if obj is None:
        return None, None

    geom = obj.Geometry

    if isinstance(geom, rg.Brep):
        return geom, 'brep'
    elif isinstance(geom, rg.Extrusion):
        brep = geom.ToBrep()
        if brep and brep.IsValid:
            return brep, 'brep'
    elif isinstance(geom, rg.Mesh):
        return geom, 'mesh'
    elif isinstance(geom, rg.Surface):
        brep = geom.ToBrep()
        if brep and brep.IsValid:
            return brep, 'brep'

    return None, None


# =============================================================================
# TERRAIN INTERSECTION ENGINE
# =============================================================================

def cast_vertical_ray_brep(brep, x, y, ray_cast_distance, tolerance):
    """
    Casts a downward vertical ray at (x, y) and finds the highest intersection
    Z value on the given Brep terrain.

    Strategy: Fire a ray from high above (x, y, +ray_cast_distance) straight
    down. Collect all face intersection parameters, convert to 3D points, and
    return the maximum Z (highest terrain contact point for that XY location).

    Parameters
    ----------
    brep : Rhino.Geometry.Brep
    x : float
    y : float
    ray_cast_distance : float
        Vertical search extent above the ray origin.
    tolerance : float

    Returns
    -------
    float or None
        The Z value of the highest terrain hit, or None if no intersection.
    """
    ray_origin    = rg.Point3d(x, y, ray_cast_distance)
    ray_direction = rg.Vector3d(0.0, 0.0, -1.0)
    ray           = rg.Ray3d(ray_origin, ray_direction)

    # CORRECT RayShoot signature: RayShoot(geometry_list, ray, max_reflections)
    intersection_params = rg.Intersect.Intersection.RayShoot(
        [brep], ray, 1
    )

    if intersection_params is None or len(intersection_params) == 0:
        return None

    # RayShoot returns RayShootEvent objects with Point3d property
    z_values = []
    for event in intersection_params:
        hit_point = event.Point  # Get the Point3d from RayShootEvent
        z_values.append(hit_point.Z)

    if not z_values:
        return None

    # Return the highest terrain Z at this XY (topmost surface contact)
    return max(z_values)


def cast_vertical_ray_mesh(mesh, x, y, ray_cast_distance):
    """
    Casts a downward vertical ray at (x, y) and finds the highest intersection
    Z value on the given Mesh terrain.

    Parameters
    ----------
    mesh : Rhino.Geometry.Mesh
    x : float
    y : float
    ray_cast_distance : float

    Returns
    -------
    float or None
        The Z value of the terrain hit, or None if no intersection.
    """
    ray_origin    = rg.Point3d(x, y, ray_cast_distance)
    ray_direction = rg.Vector3d(0.0, 0.0, -1.0)
    ray           = rg.Ray3d(ray_origin, ray_direction)

    t = rg.Intersect.Intersection.MeshRay(mesh, ray)

    if t < 0.0:
        return None

    hit_point = ray_origin + ray_direction * t
    return hit_point.Z


def sample_terrain_z_under_footprint(terrain_geom, terrain_type, bbox,
                                     sample_grid, ray_cast_distance, tolerance):
    """
    Samples terrain Z values across the building's XY footprint using a
    regular NxN grid of vertical ray-casts.

    Design rationale:
        We want the building to rest so that no part of it sinks below the
        terrain. Therefore we find the HIGHEST terrain Z under the footprint
        and use that as the seating elevation.

    Parameters
    ----------
    terrain_geom : Brep or Mesh
    terrain_type : str ('brep' or 'mesh')
    bbox : Rhino.Geometry.BoundingBox
        Bounding box of the building object.
    sample_grid : int
        Number of sample points per axis (NxN total rays).
    ray_cast_distance : float
    tolerance : float

    Returns
    -------
    dict with keys:
        'max_z'  : float or None  - highest terrain Z under footprint
        'min_z'  : float or None  - lowest terrain Z under footprint
        'hits'   : int            - number of successful ray hits
        'misses' : int            - number of rays that missed terrain
    """
    min_x = bbox.Min.X
    max_x = bbox.Max.X
    min_y = bbox.Min.Y
    max_y = bbox.Max.Y

    # Build sample point grid across the XY footprint
    x_step = (max_x - min_x) / (sample_grid - 1) if sample_grid > 1 else 0.0
    y_step = (max_y - min_y) / (sample_grid - 1) if sample_grid > 1 else 0.0

    z_hits = []
    misses = 0

    for i in range(sample_grid):
        for j in range(sample_grid):
            sx = min_x + i * x_step
            sy = min_y + j * y_step

            if terrain_type == 'brep':
                z = cast_vertical_ray_brep(
                    terrain_geom, sx, sy, ray_cast_distance, tolerance
                )
            elif terrain_type == 'mesh':
                z = cast_vertical_ray_mesh(
                    terrain_geom, sx, sy, ray_cast_distance
                )
            else:
                z = None

            if z is not None:
                z_hits.append(z)
            else:
                misses += 1

    return {
        'max_z':  max(z_hits) if z_hits else None,
        'min_z':  min(z_hits) if z_hits else None,
        'hits':   len(z_hits),
        'misses': misses
    }


# =============================================================================
# BUILDING PLACEMENT ENGINE
# =============================================================================

def compute_vertical_translation(building_bbox, terrain_z, vertical_offset):
    """
    Computes the Z translation vector needed to seat the building on the
    terrain at the given terrain_z elevation.

    The building's lowest point (bbox.Min.Z) will be moved to terrain_z.
    vertical_offset is then added to lift the building above terrain contact
    (useful for foundation clearance or floating geometry).

    Parameters
    ----------
    building_bbox : Rhino.Geometry.BoundingBox
    terrain_z : float
        The target Z elevation for the building base.
    vertical_offset : float
        Additional lift above terrain_z (0.0 = flush contact).

    Returns
    -------
    Rhino.Geometry.Vector3d
        Translation vector (only Z component is non-zero).
    """
    current_base_z = building_bbox.Min.Z
    target_z       = terrain_z + vertical_offset
    delta_z        = target_z - current_base_z

    return rg.Vector3d(0.0, 0.0, delta_z)


def move_object_by_vector(obj_id, translation_vector):
    """
    Applies a translation transform to a Rhino object in-place.

    Uses RhinoCommon Transform.Translation for precision. The operation
    is registered in the Rhino undo stack because we route through
    sc.doc.Objects.Transform with the historyUpdate flag set to True.

    Parameters
    ----------
    obj_id : System.Guid
    translation_vector : Rhino.Geometry.Vector3d

    Returns
    -------
    bool : True if the move succeeded.
    """
    xform   = rg.Transform.Translation(translation_vector)
    success = sc.doc.Objects.Transform(obj_id, xform, True)
    return success


# =============================================================================
# USER DIALOG - LAYER NAMES
# =============================================================================

def ask_layer_names():
    """
    Prompts the user for the terrain layer name and the buildings layer name
    using rs.GetString dialogs with sensible defaults.

    The user can press Enter to accept the default value displayed in brackets.
    Pressing Escape (which returns None from GetString) cancels the script.

    Returns
    -------
    tuple : (terrain_layer, buildings_layer) or (None, None) if cancelled.
    """
    print("\nLayer name configuration (press Enter to accept defaults):")

    # --- Terrain layer ---
    terrain_layer = rs.GetString(
        message="Terrain layer name",
        defaultString=DEFAULT_TERRAIN_LAYER
    )
    if terrain_layer is None:
        # User pressed Escape
        return None, None

    terrain_layer = terrain_layer.strip()
    if not terrain_layer:
        terrain_layer = DEFAULT_TERRAIN_LAYER

    # --- Buildings layer ---
    buildings_layer = rs.GetString(
        message="Buildings layer name",
        defaultString=DEFAULT_BUILDINGS_LAYER
    )
    if buildings_layer is None:
        return None, None

    buildings_layer = buildings_layer.strip()
    if not buildings_layer:
        buildings_layer = DEFAULT_BUILDINGS_LAYER

    print("  Terrain layer  : '{}'".format(terrain_layer))
    print("  Buildings layer: '{}'".format(buildings_layer))

    return terrain_layer, buildings_layer


def confirm_options():
    """
    Presents configuration options to the user via dialogs.

    Allows override of sample grid density and vertical offset.
    Returns a dict with confirmed settings, or None if user cancelled.

    Returns
    -------
    dict or None
    """
    print("\nPlacement options (press Enter to accept defaults):")

    # Sample grid density
    grid_options = [
        "3x3  (Fast, 9 rays)",
        "5x5  (Balanced, 25 rays)",
        "7x7  (Precise, 49 rays)",
        "9x9  (Accurate, 81 rays)"
    ]
    grid_values = [3, 5, 7, 9]

    grid_choice = rs.ListBox(
        items=grid_options,
        message="Select ray sampling density per building footprint:",
        title="Terrain Placement - Sample Density",
        default=grid_options[1]  # 5x5 default
    )

    if grid_choice is None:
        return None

    sample_grid = grid_values[grid_options.index(grid_choice)]

    # Vertical offset
    v_offset = rs.GetReal(
        message="Vertical offset above terrain contact point (0 = flush):",
        number=VERTICAL_OFFSET,
        minimum=0.0,
        maximum=1000.0
    )

    if v_offset is None:
        v_offset = VERTICAL_OFFSET

    return {
        'sample_grid':     sample_grid,
        'vertical_offset': v_offset
    }


# =============================================================================
# REPORTING
# =============================================================================

def format_z(z_value, doc_units):
    """Formats a Z value with document units for display."""
    if z_value is None:
        return "N/A"
    return "{:.4f} {}".format(z_value, doc_units)


def report_results(results, doc_units):
    """
    Prints a formatted summary table of placement results to the Rhino
    command line / Python console.

    Parameters
    ----------
    results : list of dict
        Each dict has keys: building_id, name, status, delta_z,
        terrain_z_max, hits, misses, error.
    doc_units : str
        Document unit string (e.g., 'mm', 'm', 'ft').
    """
    print("\n" + "=" * 60)
    print("TERRAIN PLACEMENT RESULTS")
    print("=" * 60)

    succeeded = [r for r in results if r['status'] == 'placed']
    skipped   = [r for r in results if r['status'] == 'no_terrain']
    errored   = [r for r in results if r['status'] == 'error']

    for r in results:
        name   = r.get('name') or "<unnamed>"
        status = r['status']

        if status == 'placed':
            print("  [OK]   {} -> moved {:.4f} {} (terrain Z: {})".format(
                name,
                r.get('delta_z', 0.0),
                doc_units,
                format_z(r.get('terrain_z_max'), doc_units)
            ))
            hit_info = "({} hits, {} misses)".format(
                r.get('hits', 0), r.get('misses', 0)
            )
            print("         Ray samples: {}".format(hit_info))

        elif status == 'no_terrain':
            print("  [SKIP] {} -> no terrain found under footprint".format(name))
            print("         All {} rays missed terrain.".format(
                r.get('total_rays', 0)
            ))

        elif status == 'already_placed':
            print("  [SKIP] {} -> already at terrain level "
                  "(delta < tolerance)".format(name))

        elif status == 'error':
            print("  [ERR]  {} -> {}".format(name, r.get('error', 'unknown error')))

    print("-" * 60)
    print("Summary: {} placed, {} skipped (no terrain), {} errors".format(
        len(succeeded), len(skipped), len(errored)
    ))
    print("=" * 60 + "\n")


# =============================================================================
# MAIN PLACEMENT ROUTINE
# =============================================================================

def place_buildings_on_terrain(terrain_id, building_ids, sample_grid,
                                vertical_offset, tolerance):
    """
    Core placement routine. Processes each building, performs terrain sampling,
    computes the vertical translation, and moves buildings.

    Parameters
    ----------
    terrain_id : System.Guid
    building_ids : list of System.Guid
    sample_grid : int
        NxN ray grid per building footprint.
    vertical_offset : float
        Additional lift above terrain contact (0.0 = flush).
    tolerance : float

    Returns
    -------
    list of dict
        Result records for each building (used for reporting).
    """
    # Extract terrain geometry once; it is reused for all buildings
    terrain_geom, terrain_type = get_terrain_as_brep(terrain_id)

    if terrain_geom is None:
        print("Error: Could not extract terrain geometry. "
              "Ensure terrain is a valid surface, polysurface, or mesh.")
        return []

    print("\nTerrain type: {}".format(terrain_type.upper()))
    print("Processing {} building(s)...".format(len(building_ids)))

    results    = []
    total_rays = sample_grid * sample_grid

    for idx, building_id in enumerate(building_ids):
        obj_name = rs.ObjectName(building_id) or "<unnamed>"
        print("\n  [{}] Processing: {}".format(idx + 1, obj_name))

        result = {
            'building_id':  building_id,
            'name':         obj_name,
            'status':       'error',
            'delta_z':      0.0,
            'terrain_z_max': None,
            'hits':         0,
            'misses':       0,
            'total_rays':   total_rays,
            'error':        None
        }

        # --- Step 1: Get building bounding box ---
        bbox = get_object_bounding_box(building_id)
        if bbox is None or not bbox.IsValid:
            result['error'] = "Invalid or empty bounding box"
            results.append(result)
            print("    Error: Could not compute bounding box.")
            continue

        print("    Bounding box: Z range [{:.3f}, {:.3f}]".format(
            bbox.Min.Z, bbox.Max.Z
        ))

        # --- Step 2: Sample terrain Z under building footprint ---
        terrain_sample = sample_terrain_z_under_footprint(
            terrain_geom, terrain_type, bbox,
            sample_grid, RAY_CAST_DISTANCE, tolerance
        )

        result['hits']   = terrain_sample['hits']
        result['misses'] = terrain_sample['misses']

        print("    Ray cast results: {}/{} hits".format(
            terrain_sample['hits'], total_rays
        ))

        if terrain_sample['max_z'] is None:
            result['status'] = 'no_terrain'
            results.append(result)
            print("    Warning: No terrain intersections found. "
                  "Building not moved.")
            continue

        terrain_z              = terrain_sample['max_z']
        result['terrain_z_max'] = terrain_z

        print("    Terrain Z (highest under footprint): {:.4f}".format(terrain_z))

        # --- Step 3: Compute translation vector ---
        translation = compute_vertical_translation(bbox, terrain_z, vertical_offset)
        delta_z     = translation.Z
        result['delta_z'] = delta_z

        # Skip if the building is already effectively at terrain level
        if abs(delta_z) < tolerance:
            result['status'] = 'already_placed'
            results.append(result)
            print("    Building already at terrain level "
                  "(delta = {:.6f}). No move needed.".format(delta_z))
            continue

        print("    Translating building by Z = {:.4f}".format(delta_z))

        # --- Step 4: Apply transformation ---
        success = move_object_by_vector(building_id, translation)

        if success:
            result['status'] = 'placed'
            print("    Placement complete.")
        else:
            result['error'] = ("Transform operation failed "
                               "(object may be locked or on a locked layer)")
            print("    Error: Transform failed. "
                  "Check object/layer is not locked.")

        results.append(result)

    return results


# =============================================================================
# UNDO BLOCK MANAGEMENT
# =============================================================================

def begin_undo_record(label):
    """
    Opens a Rhino undo record block. All geometry operations within this
    block can be reverted in a single Ctrl+Z.

    Parameters
    ----------
    label : str
        Name shown in Rhino's Undo history.

    Returns
    -------
    int : Undo record serial number, or -1 if unavailable.
    """
    try:
        return sc.doc.BeginUndoRecord(label)
    except Exception:
        return -1


def end_undo_record(serial_number):
    """
    Closes the undo record block.

    Parameters
    ----------
    serial_number : int
        Serial number returned by begin_undo_record.
    """
    if serial_number >= 0:
        try:
            sc.doc.EndUndoRecord(serial_number)
        except Exception:
            pass


# =============================================================================
# VALIDATION
# =============================================================================

def validate_terrain_geometry(terrain_id):
    """
    Validates that the terrain object is suitable for ray intersection.

    Checks:
    - Object exists and is valid
    - Geometry type is supported (Brep, Surface, Extrusion, or Mesh)
    - Bounding box is valid (non-degenerate)
    - Non-zero XY extent

    Parameters
    ----------
    terrain_id : System.Guid

    Returns
    -------
    tuple : (bool, str)
        (is_valid, error_message_or_empty_string)
    """
    obj = sc.doc.Objects.Find(terrain_id)
    if obj is None:
        return False, "Terrain object not found in document."

    geom = obj.Geometry
    if not isinstance(geom, (rg.Brep, rg.Mesh, rg.Surface, rg.Extrusion)):
        return False, (
            "Terrain geometry type '{}' is not supported. "
            "Use a surface, polysurface, or mesh.".format(type(geom).__name__)
        )

    bbox = geom.GetBoundingBox(rg.Transform.Identity)
    if not bbox.IsValid:
        return False, "Terrain bounding box is invalid (degenerate geometry)."

    if (bbox.Max.X - bbox.Min.X) < DEFAULT_TOLERANCE:
        return False, "Terrain has zero X extent."
    if (bbox.Max.Y - bbox.Min.Y) < DEFAULT_TOLERANCE:
        return False, "Terrain has zero Y extent."

    return True, ""


def validate_buildings(building_ids):
    """
    Validates building objects before processing.

    Checks each building for:
    - Object exists and is valid
    - Has a valid bounding box
    - Is not locked at the object or layer level

    Parameters
    ----------
    building_ids : list of System.Guid

    Returns
    -------
    tuple : (valid_ids, warnings)
        valid_ids : list of GUIDs that passed validation
        warnings  : list of warning message strings
    """
    valid_ids = []
    warnings  = []

    for b_id in building_ids:
        obj = sc.doc.Objects.Find(b_id)
        if obj is None:
            warnings.append("Object {} not found - skipped.".format(b_id))
            continue

        if obj.IsLocked:
            warnings.append("'{}' is locked - skipped.".format(
                rs.ObjectName(b_id) or str(b_id)
            ))
            continue

        bbox = obj.Geometry.GetBoundingBox(rg.Transform.Identity)
        if not bbox.IsValid:
            warnings.append("'{}' has invalid bounding box - skipped.".format(
                rs.ObjectName(b_id) or str(b_id)
            ))
            continue

        valid_ids.append(b_id)

    return valid_ids, warnings


# =============================================================================
# ENTRY POINT
# =============================================================================

def main():
    """
    Main entry point for the terrain-building placement script.

    Execution sequence:
    1.  Print header and read document context
    2.  Ask for terrain layer name (default: "Terrain")
    3.  Ask for buildings layer name (default: "Buildings")
    4.  Detect terrain objects from terrain layer (first object is used)
    5.  Detect building objects from buildings layer
    6.  Validate terrain geometry
    7.  Validate building objects
    8.  Confirm configuration options (sample density, vertical offset)
    9.  Open undo record block
    10. Run placement routine for all valid buildings
    11. Close undo record block
    12. Redraw viewport and report results
    """
    print("\n" + "=" * 60)
    print("  TERRAIN-BUILDING PLACEMENT SCRIPT  v2.0.0")
    print("=" * 60)
    print("  Seats building objects onto terrain surface/mesh")
    print("  using vertical ray-casting from building footprints.")
    print("  Objects are detected automatically from named layers.")
    print("  Full undo support: Ctrl+Z to revert all moves.")
    print("=" * 60)

    # --- Document context ---
    tolerance = sc.doc.ModelAbsoluteTolerance
    doc_units = rs.UnitSystemName(abbreviate=True)
    print("\nDocument units: {} | Tolerance: {}".format(doc_units, tolerance))

    # =========================================================================
    # Step 1-2: Ask for layer names
    # =========================================================================
    terrain_layer, buildings_layer = ask_layer_names()

    if terrain_layer is None or buildings_layer is None:
        print("Aborted: Layer name dialog cancelled.")
        return

    # =========================================================================
    # Step 3: Detect terrain object from layer
    # =========================================================================
    print("\nDetecting terrain from layer '{}'...".format(terrain_layer))
    terrain_objects = get_objects_from_layer(terrain_layer)

    if not terrain_objects:
        rs.MessageBox(
            "No objects found on the '{}' layer.\n\n"
            "Please ensure your terrain surface or mesh is on "
            "that layer and try again.".format(terrain_layer),
            title="Terrain Placement - No Terrain Found"
        )
        print("Aborted: No terrain objects on layer '{}'.".format(terrain_layer))
        return

    # Use the first object as the terrain; warn if multiple exist
    terrain_id = terrain_objects[0]
    if len(terrain_objects) > 1:
        print("  Warning: {} objects found on '{}'; "
              "using the first one as terrain.".format(
                  len(terrain_objects), terrain_layer
              ))
    else:
        print("  Terrain object found: {}".format(
            rs.ObjectName(terrain_id) or "<unnamed>"
        ))

    # =========================================================================
    # Step 4: Validate terrain geometry
    # =========================================================================
    is_valid, error_msg = validate_terrain_geometry(terrain_id)
    if not is_valid:
        rs.MessageBox(
            "Terrain validation failed:\n\n{}".format(error_msg),
            title="Terrain Placement - Invalid Terrain"
        )
        print("Aborted: {}".format(error_msg))
        return

    # =========================================================================
    # Step 5: Detect building objects from layer
    # =========================================================================
    print("\nDetecting buildings from layer '{}'...".format(buildings_layer))
    building_ids = get_objects_from_layer(buildings_layer)

    # Exclude the terrain object in case both layers share an object
    building_ids = [b for b in building_ids if b != terrain_id]

    if not building_ids:
        rs.MessageBox(
            "No building objects found on the '{}' layer.\n\n"
            "Please ensure your building geometry is on that layer "
            "and try again.".format(buildings_layer),
            title="Terrain Placement - No Buildings Found"
        )
        print("Aborted: No building objects on layer '{}'.".format(
            buildings_layer
        ))
        return

    print("  {} building(s) found on layer '{}'.".format(
        len(building_ids), buildings_layer
    ))

    # =========================================================================
    # Step 6: Validate buildings
    # =========================================================================
    valid_building_ids, build_warnings = validate_buildings(building_ids)

    if build_warnings:
        print("\nValidation warnings:")
        for w in build_warnings:
            print("  Warning: {}".format(w))

    if len(valid_building_ids) == 0:
        rs.MessageBox(
            "No valid building objects to process.\n\n"
            "All buildings on layer '{}' were locked or had invalid geometry.\n"
            "Unlock objects/layers and try again.".format(buildings_layer),
            title="Terrain Placement - No Valid Buildings"
        )
        print("Aborted: No valid buildings after validation.")
        return

    if len(valid_building_ids) < len(building_ids):
        print("\n{}/{} buildings passed validation and will be processed.".format(
            len(valid_building_ids), len(building_ids)
        ))

    # =========================================================================
    # Step 7: Confirm placement options
    # =========================================================================
    options = confirm_options()
    if options is None:
        print("Aborted: User cancelled options dialog.")
        return

    sample_grid     = options['sample_grid']
    vertical_offset = options['vertical_offset']

    print("\nSettings:")
    print("  Terrain layer   : '{}'".format(terrain_layer))
    print("  Buildings layer : '{}'".format(buildings_layer))
    print("  Buildings count : {}".format(len(valid_building_ids)))
    print("  Sample grid     : {}x{} = {} rays per building".format(
        sample_grid, sample_grid, sample_grid * sample_grid
    ))
    print("  Vertical offset : {:.4f} {}".format(vertical_offset, doc_units))
    print("  Ray distance    : +/- {:.0f} {} from building".format(
        RAY_CAST_DISTANCE, doc_units
    ))

    # =========================================================================
    # Step 8: Prepare viewport and undo record
    # =========================================================================
    rs.UnselectAllObjects()
    rs.EnableRedraw(False)

    undo_serial = begin_undo_record("PlaceBuildingOnTerrain")
    print("\nUndo record opened (serial: {})".format(undo_serial))

    # =========================================================================
    # Step 9: Run placement routine
    # =========================================================================
    results = []
    try:
        results = place_buildings_on_terrain(
            terrain_id=terrain_id,
            building_ids=valid_building_ids,
            sample_grid=sample_grid,
            vertical_offset=vertical_offset,
            tolerance=tolerance
        )
    except Exception as e:
        print("\nUnexpected error during placement: {}".format(str(e)))
        import traceback
        traceback.print_exc()
    finally:
        # Always close undo record even if an exception occurred
        end_undo_record(undo_serial)
        print("Undo record closed.")

    # =========================================================================
    # Step 10: Redraw and report
    # =========================================================================
    rs.EnableRedraw(True)
    sc.doc.Views.Redraw()

    if results:
        report_results(results, doc_units)

        placed_count = sum(1 for r in results if r['status'] == 'placed')
        if placed_count > 0:
            print("Done. {} building(s) placed on terrain. "
                  "Use Ctrl+Z to undo.".format(placed_count))
        else:
            print("Done. No buildings were moved "
                  "(already placed or no terrain found under any footprint).")
    else:
        print("No results returned. Check error messages above.")


# =============================================================================
# SCRIPT EXECUTION
# =============================================================================

if __name__ == "__main__":
    main()
