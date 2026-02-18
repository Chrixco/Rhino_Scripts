# -*- coding: utf-8 -*-
# =============================================================================
# adapt_road_to_topography.py
# =============================================================================
# Road Topography Adapter - Rhino Python Script
#
# PURPOSE:
#   Takes a 2D road geometry (centerline curve, polyline, or surface) and
#   projects it onto a terrain surface or mesh to produce a 3D road surface
#   that accurately follows the topography.
#
# ALGORITHM (Approach 1: Project → Cross-Section → Loft):
#   1. Extract road centerline from input geometry
#   2. Project the 2D centerline onto the 3D terrain
#   3. Sample the projected 3D centerline at regular intervals
#   4. At each sample point, compute the terrain normal and build a
#      perpendicular cross-section plane
#   5. Generate a road-width cross-section profile at each station
#   6. Loft all cross-section profiles into a continuous NURBS surface
#   7. Organize results into named layers with statistics report
#
# WORKFLOW:
#   1. Place your terrain object on a layer named "Terrain" (configurable)
#   2. Place your 2D road centerline on a layer named "Roads" (configurable)
#      - Curve, polyline, or surface are all accepted
#   3. Run the script (F5 in Rhino's Python editor)
#   4. Accept or change layer names in the prompts
#   5. Configure parameters (road width, sample spacing, height offset)
#   6. Review output layers and console statistics
#
# OUTPUT LAYERS:
#   - Roads_Projected     : the final 3D road surface (NURBS loft)
#   - Roads_Centerline    : the projected 3D centerline (reference)
#   - Roads_CrossSections : cross-section curves at each station (debug)
#
# SUPPORTED TERRAIN TYPES:
#   - Brep (surface, polysurface, solid)
#   - Rhino.Geometry.Mesh
#   - Extrusion (converted to Brep internally)
#
# SUPPORTED ROAD INPUT TYPES:
#   - Open or closed NurbsCurve / PolylineCurve
#   - ArcCurve / PolyCurve (any curve type Rhino exposes)
#   - BrepFace / Brep surface (centerline extracted from mid-isocurve)
#
# CONSTRAINTS:
#   - World Z = up (standard architectural workflow)
#   - Road input should be roughly planar (XY), but height is ignored
#     during centerline extraction; the 3D projection handles Z
#   - Terrain must cover the full XY extent of the road
#   - Very short sample spacing (< 0.5 units) may cause loft failure
#
# AUTHOR:  Rhino Python Script
# VERSION: 1.0.0
# TARGET:  Rhino 7+ (rhinoscriptsyntax + RhinoCommon)
# =============================================================================

import rhinoscriptsyntax as rs
import Rhino
import Rhino.Geometry as rg
import Rhino.Geometry.Intersect as ri
import scriptcontext as sc
import System
import math


# =============================================================================
# CONFIGURATION CONSTANTS
# =============================================================================

# Distance between cross-section stations along the centerline.
# Smaller spacing = more sections = smoother result but slower computation.
# Recommended range: 1.0 - 20.0 (document units)
DEFAULT_SAMPLE_SPACING = 5.0

# Road width (distance from left edge to right edge of the road surface).
# Used when the input is a centerline curve; ignored if input is a surface.
DEFAULT_ROAD_WIDTH = 10.0

# Height offset above the terrain surface (positive = lifted above terrain).
# Useful for road bed clearance, curb height, or debugging separation.
DEFAULT_HEIGHT_OFFSET = 0.0

# Number of points in each cross-section profile.
# 3 = left edge, center, right edge (minimum, creates a flat profile)
# 5 = left edge, left shoulder, center, right shoulder, right edge
# Must be odd and >= 3 for symmetric road profiles.
DEFAULT_CROSS_SECTION_POINTS = 3

# Vertical ray-cast search distance above terrain bounding box max.
# Must be larger than any expected Z gap between road and terrain.
RAY_CAST_DISTANCE = 10000.0

# Tolerance for projection operations. Overridden by document tolerance at
# runtime via sc.doc.ModelAbsoluteTolerance.
DEFAULT_TOLERANCE = 0.001

# Minimum number of cross-sections required to attempt a loft.
# Lofting fewer than 2 sections is undefined.
MIN_SECTIONS_FOR_LOFT = 2

# Maximum perpendicular angle (degrees) allowed for cross-section tilt.
# If terrain slope exceeds this, the cross-section falls back to a
# world-Z perpendicular plane to prevent extreme geometry distortion.
MAX_TERRAIN_SLOPE_DEG = 80.0

# Layer names for output geometry
LAYER_ROAD_SURFACE      = "Roads_Projected"
LAYER_ROAD_CENTERLINE   = "Roads_Centerline"
LAYER_ROAD_SECTIONS     = "Roads_CrossSections"

# Layer colors (R, G, B) for each output layer
COLOR_ROAD_SURFACE    = (80, 80, 80)    # dark grey  - road surface
COLOR_ROAD_CENTERLINE = (255, 140, 0)   # orange     - centerline
COLOR_ROAD_SECTIONS   = (0, 180, 255)   # cyan       - cross-sections

# Default layer names from which to read terrain and road input objects
DEFAULT_TERRAIN_LAYER = "terrain"
DEFAULT_ROAD_LAYER    = "roads"


# =============================================================================
# LAYER MANAGEMENT
# =============================================================================

def ensure_layer(layer_name, color_rgb=None, parent_layer=None):
    """
    Creates a Rhino layer if it does not already exist.

    If the layer already exists, it is returned as-is without modification
    so that an artist's existing layer settings are preserved.

    Parameters
    ----------
    layer_name : str
        The target layer name. For nested layers use full path syntax
        "Parent::Child"; however this function creates top-level layers only
        unless parent_layer is provided.
    color_rgb : tuple of (int, int, int) or None
        RGB color to assign when creating a new layer.
    parent_layer : str or None
        If provided, the layer is nested under this parent.

    Returns
    -------
    str
        The layer name (unchanged from input).
    """
    if rs.IsLayer(layer_name):
        return layer_name

    if color_rgb is not None:
        color = System.Drawing.Color.FromArgb(
            color_rgb[0], color_rgb[1], color_rgb[2]
        )
        rs.AddLayer(layer_name, color)
    else:
        rs.AddLayer(layer_name)

    return layer_name


def add_object_to_layer(obj_id, layer_name):
    """
    Moves a Rhino object to the specified layer.

    Parameters
    ----------
    obj_id : System.Guid
    layer_name : str

    Returns
    -------
    bool : True if successful.
    """
    if obj_id is None:
        return False
    try:
        rs.ObjectLayer(obj_id, layer_name)
        return True
    except Exception:
        return False


def setup_output_layers():
    """
    Creates all required output layers for the road adaptation result.

    Layers are only created if they do not already exist in the document.
    This preserves any user-defined layer properties on repeat runs.
    """
    ensure_layer(LAYER_ROAD_SURFACE,    COLOR_ROAD_SURFACE)
    ensure_layer(LAYER_ROAD_CENTERLINE, COLOR_ROAD_CENTERLINE)
    ensure_layer(LAYER_ROAD_SECTIONS,   COLOR_ROAD_SECTIONS)


def get_objects_from_layer(layer_name):
    """
    Returns all Rhino object GUIDs on the named layer.

    Parameters
    ----------
    layer_name : str

    Returns
    -------
    list of System.Guid
        Empty list if the layer does not exist or has no objects.
    """
    if not rs.IsLayer(layer_name):
        print("  Warning: Layer '{}' does not exist.".format(layer_name))
        return []

    objects = rs.ObjectsByLayer(layer_name)
    return list(objects) if objects else []


# =============================================================================
# TERRAIN UTILITIES
# =============================================================================

def get_terrain_geometry(terrain_id):
    """
    Extracts a terrain object as a typed RhinoCommon geometry object.

    Supports Brep, Extrusion (converted to Brep), Mesh, and Surface.
    Returns a (geometry, type_string) tuple so the caller can dispatch
    type-specific operations (ray-cast vs. Brep projection).

    Parameters
    ----------
    terrain_id : System.Guid

    Returns
    -------
    tuple : (geometry_object, type_string)
        type_string is one of: 'brep', 'mesh', None
        Returns (None, None) if the terrain cannot be extracted.
    """
    obj = sc.doc.Objects.Find(terrain_id)
    if obj is None:
        return None, None

    geom = obj.Geometry

    if isinstance(geom, rg.Brep):
        return geom, 'brep'

    if isinstance(geom, rg.Extrusion):
        brep = geom.ToBrep()
        if brep and brep.IsValid:
            return brep, 'brep'

    if isinstance(geom, rg.Surface):
        brep = geom.ToBrep()
        if brep and brep.IsValid:
            return brep, 'brep'

    if isinstance(geom, rg.Mesh):
        return geom, 'mesh'

    return None, None


def get_terrain_name(terrain_id):
    """
    Returns a human-readable label for the terrain object combining its
    Rhino object name (if set) and geometry type class name.

    Parameters
    ----------
    terrain_id : System.Guid

    Returns
    -------
    str
    """
    obj = sc.doc.Objects.Find(terrain_id)
    if obj is None:
        return "<unknown>"

    obj_name  = rs.ObjectName(terrain_id) or "<unnamed>"
    geom_type = type(obj.Geometry).__name__

    return "{} ({})".format(obj_name, geom_type)


def cast_ray_to_terrain(terrain_geom, terrain_type, x, y, tolerance):
    """
    Casts a vertical downward ray at (x, y) and returns the highest Z
    intersection with the terrain.

    This is used both for normal estimation and for applying height offsets
    when projecting individual cross-section edge points back to terrain.

    Parameters
    ----------
    terrain_geom : Rhino.Geometry.Brep or Rhino.Geometry.Mesh
    terrain_type : str ('brep' or 'mesh')
    x : float
    y : float
    tolerance : float

    Returns
    -------
    float or None
        Z value of highest terrain hit, or None if no intersection.
    """
    ray_origin    = rg.Point3d(x, y, RAY_CAST_DISTANCE)
    ray_direction = rg.Vector3d(0.0, 0.0, -1.0)
    ray           = rg.Ray3d(ray_origin, ray_direction)

    if terrain_type == 'brep':
        hit_events = ri.Intersection.RayShoot([terrain_geom], ray, 1)
        if hit_events is None or len(hit_events) == 0:
            return None
        z_values = [ev.Point.Z for ev in hit_events]
        return max(z_values)

    elif terrain_type == 'mesh':
        t = ri.Intersection.MeshRay(terrain_geom, ray)
        if t < 0.0:
            return None
        hit_pt = ray_origin + ray_direction * t
        return hit_pt.Z

    return None


def estimate_terrain_normal_at_xy(terrain_geom, terrain_type, x, y, tolerance,
                                   sample_radius=0.5):
    """
    Estimates the terrain surface normal at the XY location by sampling
    three nearby points and computing the cross-product normal.

    For Brep terrain, uses Brep.ClosestPoint() for accurate normal.
    For Mesh terrain, uses mesh face normal at the hit face.

    Falls back to world Z-up if the estimation fails (e.g., point is
    outside the terrain boundary).

    Parameters
    ----------
    terrain_geom : Brep or Mesh
    terrain_type : str
    x : float
    y : float
    tolerance : float
    sample_radius : float
        XY offset used when sampling neighbouring points for normal
        estimation via cross-product (used for mesh terrain only when the
        direct face normal is unavailable).

    Returns
    -------
    Rhino.Geometry.Vector3d
        Normalized terrain normal. Defaults to (0, 0, 1) on failure.
    """
    world_up = rg.Vector3d(0.0, 0.0, 1.0)

    if terrain_type == 'brep':
        # Sample at the query point to find Z, then do a ClosestPoint query
        z = cast_ray_to_terrain(terrain_geom, 'brep', x, y, tolerance)
        if z is None:
            return world_up

        query_pt = rg.Point3d(x, y, z)
        success, u, v = terrain_geom.Faces[0].ClosestPoint(query_pt)

        # Try all faces to find the one closest to the query point
        best_dist  = float('inf')
        best_normal = world_up

        for face in terrain_geom.Faces:
            ok, fu, fv = face.ClosestPoint(query_pt)
            if ok:
                pt_on_face = face.PointAt(fu, fv)
                dist       = query_pt.DistanceTo(pt_on_face)
                if dist < best_dist:
                    best_dist   = dist
                    normal_raw  = face.NormalAt(fu, fv)
                    if normal_raw.IsValid and normal_raw.Length > 1e-10:
                        normal_raw.Unitize()
                        # Ensure normal points upward (positive Z component)
                        if normal_raw.Z < 0:
                            normal_raw = -normal_raw
                        best_normal = normal_raw

        return best_normal

    elif terrain_type == 'mesh':
        ray_origin    = rg.Point3d(x, y, RAY_CAST_DISTANCE)
        ray_direction = rg.Vector3d(0.0, 0.0, -1.0)
        ray           = rg.Ray3d(ray_origin, ray_direction)

        # MeshRay returns t parameter; we need the face index for the normal
        hit_mesh  = rg.Mesh()
        face_idx  = -1

        # Use MeshRay with face index output when available
        t = ri.Intersection.MeshRay(terrain_geom, ray)
        if t < 0.0:
            return world_up

        # Recover face normal by finding closest face at hit point
        hit_pt = ray_origin + ray_direction * t
        mesh_pt = terrain_geom.ClosestPoint(hit_pt)
        if not mesh_pt.IsValid:
            return world_up

        # Normals at mesh vertex (interpolated)
        pt_idx = terrain_geom.ClosestPoint(
            hit_pt,
            rg.Vector3d.Zero,
            0.0
        )

        # Cross-product fallback using three sampled Z values
        z0 = cast_ray_to_terrain(terrain_geom, 'mesh', x,                y,               tolerance)
        z1 = cast_ray_to_terrain(terrain_geom, 'mesh', x + sample_radius, y,               tolerance)
        z2 = cast_ray_to_terrain(terrain_geom, 'mesh', x,                y + sample_radius, tolerance)

        if z0 is None or z1 is None or z2 is None:
            return world_up

        p0 = rg.Point3d(x,                y,                z0)
        p1 = rg.Point3d(x + sample_radius, y,                z1)
        p2 = rg.Point3d(x,                y + sample_radius, z2)

        v1 = p1 - p0
        v2 = p2 - p0
        n  = rg.Vector3d.CrossProduct(v1, v2)

        if n.IsZero or n.Length < 1e-10:
            return world_up

        n.Unitize()
        if n.Z < 0:
            n = -n

        return n

    return world_up


# =============================================================================
# ROAD CENTERLINE EXTRACTION
# =============================================================================

def extract_centerline(road_id, tolerance):
    """
    Extracts or constructs a centerline curve from the input road geometry.

    Strategy by geometry type:
    - Curve / PolylineCurve / NurbsCurve: used directly as the centerline.
    - Brep (surface or extrusion): the mid-isocurve of the largest face
      is used as the centerline approximation.
    - If none of the above, returns None and reports the type.

    The returned curve lives in 2D/3D space (Z is retained from input but
    is typically flat since roads are drawn in plan view).

    Parameters
    ----------
    road_id : System.Guid
        Rhino object GUID of the road input.
    tolerance : float

    Returns
    -------
    Rhino.Geometry.Curve or None
    """
    obj = sc.doc.Objects.Find(road_id)
    if obj is None:
        print("  Error: Road object not found.")
        return None

    geom = obj.Geometry

    # --- Curve types: use directly ---
    if isinstance(geom, rg.Curve):
        print("  Input type: Curve -> using as centerline directly.")
        return geom.DuplicateCurve()

    # --- Brep / Surface: extract centerline via mid-isocurve ---
    if isinstance(geom, (rg.Brep, rg.Extrusion)):
        brep = geom if isinstance(geom, rg.Brep) else geom.ToBrep()
        if brep is None or not brep.IsValid:
            print("  Error: Could not convert road geometry to Brep.")
            return None

        print("  Input type: Brep surface -> extracting mid-isocurve centerline.")

        # Find the face with the largest area (most likely the road surface)
        largest_face   = None
        largest_area   = -1.0

        for face in brep.Faces:
            amp = rg.AreaMassProperties.Compute(face)
            if amp is not None and amp.Area > largest_area:
                largest_area = amp.Area
                largest_face = face

        if largest_face is None:
            print("  Error: Could not determine largest Brep face.")
            return None

        # Extract the V-midpoint isocurve (along the road length direction)
        domain_u = largest_face.Domain(0)
        domain_v = largest_face.Domain(1)
        mid_v    = domain_v.Mid

        centerline = largest_face.IsoCurve(1, mid_v)  # direction=1 → V isocurve
        if centerline is None or not centerline.IsValid:
            # Fallback: try U mid-isocurve
            mid_u      = domain_u.Mid
            centerline = largest_face.IsoCurve(0, mid_u)

        if centerline is None or not centerline.IsValid:
            print("  Error: Isocurve extraction failed.")
            return None

        return centerline

    print("  Error: Unsupported road geometry type: {}".format(
        type(geom).__name__
    ))
    return None


def flatten_curve_to_plane(curve, tolerance):
    """
    Projects a curve to the XY plane (Z = 0) to normalize the centerline
    to a flat, consistent starting geometry before terrain projection.

    This removes any incidental Z values the artist may have left on the
    road curve when drawing in plan view.

    Parameters
    ----------
    curve : Rhino.Geometry.Curve
    tolerance : float

    Returns
    -------
    Rhino.Geometry.Curve
        A new curve with all Z values set to 0.
    """
    xy_plane  = rg.Plane.WorldXY
    # Project the curve onto Z=0 plane using Curve.ProjectToPlane
    flat_curve = rg.Curve.ProjectToPlane(curve, xy_plane)
    if flat_curve is None or not flat_curve.IsValid:
        # Fallback: return original curve unchanged
        return curve.DuplicateCurve()
    return flat_curve


# =============================================================================
# CENTERLINE PROJECTION TO TERRAIN
# =============================================================================

def project_centerline_brep(centerline_flat, brep_terrain, tolerance):
    """
    Projects a flat centerline curve onto a Brep terrain surface using
    Rhino's built-in curve-to-surface projection.

    Uses Curve.ProjectToBrep() which fires rays along the world Z axis
    from each point on the curve to find terrain intersections.

    Parameters
    ----------
    centerline_flat : Rhino.Geometry.Curve
        The flat (Z=0) centerline curve.
    brep_terrain : Rhino.Geometry.Brep
    tolerance : float

    Returns
    -------
    Rhino.Geometry.Curve or None
        The longest projected curve segment, or None if projection fails.
    """
    projection_direction = rg.Vector3d(0.0, 0.0, -1.0)

    projected_curves = rg.Curve.ProjectToBrep(
        centerline_flat,
        brep_terrain,
        projection_direction,
        tolerance
    )

    if projected_curves is None or len(projected_curves) == 0:
        # Try projecting in the upward direction as fallback
        projection_direction = rg.Vector3d(0.0, 0.0, 1.0)
        projected_curves = rg.Curve.ProjectToBrep(
            centerline_flat,
            brep_terrain,
            projection_direction,
            tolerance
        )

    if projected_curves is None or len(projected_curves) == 0:
        return None

    # When multiple segments are returned (e.g. road crossing a hole),
    # select the longest one as the primary projected centerline.
    best_curve  = None
    best_length = -1.0

    for crv in projected_curves:
        if crv is not None and crv.IsValid:
            length = crv.GetLength()
            if length > best_length:
                best_length = length
                best_curve  = crv

    return best_curve


def project_centerline_mesh(centerline_flat, mesh_terrain, tolerance,
                             sample_count=500):
    """
    Projects a flat centerline curve onto a Mesh terrain by sampling
    the curve at regular parameter intervals, ray-casting each sample
    to the mesh, and rebuilding the projected curve as a polyline.

    This method is used when the terrain is a Mesh rather than a Brep,
    since Curve.ProjectToBrep does not operate on meshes.

    Parameters
    ----------
    centerline_flat : Rhino.Geometry.Curve
    mesh_terrain : Rhino.Geometry.Mesh
    tolerance : float
    sample_count : int
        Number of parameter samples along the curve. Higher = smoother
        projection but slower. Default 500 is adequate for most roads.

    Returns
    -------
    Rhino.Geometry.Curve or None
        A PolylineCurve following the mesh terrain, or None on failure.
    """
    domain = centerline_flat.Domain
    t_vals = [
        domain.ParameterAt(float(i) / (sample_count - 1))
        for i in range(sample_count)
    ]

    ray_dir = rg.Vector3d(0.0, 0.0, -1.0)
    points_3d = []

    for t in t_vals:
        pt_flat = centerline_flat.PointAt(t)

        ray_origin = rg.Point3d(pt_flat.X, pt_flat.Y, RAY_CAST_DISTANCE)
        ray        = rg.Ray3d(ray_origin, ray_dir)

        hit_t = ri.Intersection.MeshRay(mesh_terrain, ray)
        if hit_t >= 0.0:
            hit_pt = ray_origin + ray_dir * hit_t
            points_3d.append(hit_pt)

    if len(points_3d) < 2:
        return None

    # Build a polyline from hit points and convert to a smooth NurbsCurve
    polyline = rg.Polyline(points_3d)
    poly_crv  = polyline.ToNurbsCurve()

    if poly_crv is None or not poly_crv.IsValid:
        return None

    # Fit a smooth curve through the polyline points to avoid sharp kinks
    smooth = rg.Curve.CreateInterpolatedCurve(
        [polyline[i] for i in range(polyline.Count)],
        3,          # degree 3 (cubic)
        rg.CurveKnotStyle.ChordPeriodic if centerline_flat.IsClosed
        else rg.CurveKnotStyle.Chord
    )

    return smooth if (smooth and smooth.IsValid) else poly_crv


def project_centerline_to_terrain(centerline, terrain_geom, terrain_type,
                                   tolerance):
    """
    Dispatches centerline projection to the appropriate method based on
    terrain type (Brep or Mesh).

    This is the public interface for Step 3 of the algorithm. It:
    1. Flattens the centerline to Z=0 so projection direction is consistent
    2. Projects using the terrain-type-appropriate method
    3. Returns the 3D projected curve following the terrain surface

    Parameters
    ----------
    centerline : Rhino.Geometry.Curve
        The raw centerline (may have Z values from user input).
    terrain_geom : Brep or Mesh
    terrain_type : str ('brep' or 'mesh')
    tolerance : float

    Returns
    -------
    Rhino.Geometry.Curve or None
        The 3D projected centerline. None if projection fails.
    """
    print("  Flattening centerline to XY plane before projection...")
    flat_cl = flatten_curve_to_plane(centerline, tolerance)

    if terrain_type == 'brep':
        print("  Projecting onto Brep terrain (Curve.ProjectToBrep)...")
        return project_centerline_brep(flat_cl, terrain_geom, tolerance)

    elif terrain_type == 'mesh':
        print("  Projecting onto Mesh terrain (ray-sampling method)...")
        # Estimate sample count from curve length for ~0.5-unit density
        flat_len  = flat_cl.GetLength()
        n_samples = max(50, int(flat_len / 0.5))
        return project_centerline_mesh(
            flat_cl, terrain_geom, tolerance, n_samples
        )

    print("  Error: Unknown terrain type '{}'.".format(terrain_type))
    return None


# =============================================================================
# CENTERLINE SAMPLING WITH TERRAIN DATA
# =============================================================================

def sample_curve_with_terrain_data(projected_curve, terrain_geom, terrain_type,
                                    spacing, tolerance):
    """
    Divides the projected 3D centerline into stations at the specified
    spacing, and collects terrain data at each station.

    At each sample point the function records:
    - Point3d   : the 3D location on the projected centerline
    - Tangent   : unit tangent vector of the centerline at that parameter
    - Normal    : terrain surface normal at that XY location
    - Parameter : curve parameter t (for reference)

    Design note on normal estimation:
        The terrain normal is estimated from the projected centerline point's
        XY coordinates, NOT from the Brep parameter space, because the road
        may be passing over multiple Brep faces and we want a consistent
        cross-section orientation strategy.

    Parameters
    ----------
    projected_curve : Rhino.Geometry.Curve
        The 3D centerline following the terrain surface.
    terrain_geom : Brep or Mesh
    terrain_type : str
    spacing : float
        Distance between sample stations (document units).
    tolerance : float

    Returns
    -------
    list of dict, each with keys:
        't'       : float  - curve parameter
        'point'   : Point3d
        'tangent' : Vector3d (unit)
        'normal'  : Vector3d (unit, terrain surface normal)
    """
    crv_length = projected_curve.GetLength()
    if crv_length < tolerance:
        print("  Error: Projected centerline is degenerate (length ~0).")
        return []

    # Generate parameter array at equal chord-length intervals
    # We use DivideByLength which gives arc-length parameterisation
    params = projected_curve.DivideByLength(spacing, includeEnds=True)

    if params is None or len(params) == 0:
        # Fallback: divide into at least 2 segments
        params = projected_curve.DivideEquidistant(spacing)
        if params is None or len(params) == 0:
            # Last resort: two-point sample at domain start and end
            domain = projected_curve.Domain
            params = [domain.Min, domain.Max]

    stations = []

    for t in params:
        pt = projected_curve.PointAt(t)
        if not pt.IsValid:
            continue

        # Curve tangent at this parameter (unit vector)
        tangent_raw = projected_curve.TangentAt(t)
        if tangent_raw.IsZero:
            continue
        tangent_raw.Unitize()

        # Terrain normal at the XY location of this station
        normal = estimate_terrain_normal_at_xy(
            terrain_geom, terrain_type,
            pt.X, pt.Y,
            tolerance
        )

        stations.append({
            't':       t,
            'point':   pt,
            'tangent': tangent_raw,
            'normal':  normal
        })

    return stations


# =============================================================================
# CROSS-SECTION GENERATION
# =============================================================================

def build_cross_section_plane(point, tangent, normal, tolerance):
    """
    Constructs a Rhino.Geometry.Plane for a cross-section at the given
    station on the projected centerline.

    The plane is defined so that:
    - Origin = station point on the projected centerline
    - X axis = cross-section direction (perpendicular to tangent in terrain)
    - Y axis = terrain normal direction (road slope direction)
    - Z axis = tangent direction (road travel direction)

    Strategy for cross-section direction:
        We want the cross-section profile to lie perpendicular to the road
        direction AND respect the terrain slope. The cross-section X axis
        is computed as the cross product of the tangent and the terrain
        normal. This gives a vector that is:
        - Perpendicular to the road direction (no drift along road)
        - Lies in the terrain surface tangent plane

    Fallback: if tangent and normal are nearly parallel (very steep road
        going straight up a cliff), fall back to world-XY perpendicular.

    Parameters
    ----------
    point   : Rhino.Geometry.Point3d
    tangent : Rhino.Geometry.Vector3d (unit)
    normal  : Rhino.Geometry.Vector3d (unit)
    tolerance : float

    Returns
    -------
    Rhino.Geometry.Plane or None
    """
    # Cross-section X axis: perpendicular to road tangent, lies in terrain plane
    cross_dir = rg.Vector3d.CrossProduct(tangent, normal)

    # If cross product is near-zero the tangent and normal are parallel
    # (vertical cliff face). Fall back to using world Y as the cross-section.
    if cross_dir.Length < tolerance:
        # Tangent is nearly vertical; use world horizontal cross direction
        world_x   = rg.Vector3d(1.0, 0.0, 0.0)
        cross_dir = rg.Vector3d.CrossProduct(tangent, world_x)
        if cross_dir.Length < tolerance:
            world_y   = rg.Vector3d(0.0, 1.0, 0.0)
            cross_dir = rg.Vector3d.CrossProduct(tangent, world_y)
        if cross_dir.Length < tolerance:
            return None

    cross_dir.Unitize()

    # Ensure cross_dir has positive X component for consistency
    # (so left/right edge labelling is deterministic across sections)
    if cross_dir.X < 0:
        cross_dir = -cross_dir

    # Recompute a true Y axis that is orthogonal to both cross_dir and tangent
    y_axis = rg.Vector3d.CrossProduct(cross_dir, tangent)
    if y_axis.IsZero:
        y_axis = normal
    else:
        y_axis.Unitize()

    plane = rg.Plane(point, cross_dir, y_axis)
    return plane


def create_cross_section_curve(station, road_width, num_points,
                                terrain_geom, terrain_type,
                                height_offset, tolerance):
    """
    Generates a single cross-section profile curve at a terrain station.

    The cross-section runs from left edge (-width/2) to right edge (+width/2)
    along the cross-section plane's X axis, with the specified number of
    profile points distributed symmetrically.

    For each edge/profile point:
    1. Compute the XY location in world space (at half-width offset)
    2. Ray-cast to terrain to find the actual Z value
    3. Apply height offset
    4. Assemble into a smooth interpolated curve

    Parameters
    ----------
    station : dict
        Entry from sample_curve_with_terrain_data() containing
        'point', 'tangent', 'normal', 't'.
    road_width : float
        Total road width (left edge to right edge).
    num_points : int
        Number of profile points (must be odd and >= 3).
        3 = L, C, R; 5 = L, LS, C, RS, R.
    terrain_geom : Brep or Mesh
    terrain_type : str
    height_offset : float
        Constant Z lift above terrain surface.
    tolerance : float

    Returns
    -------
    Rhino.Geometry.Curve or None
        A degree-3 interpolated curve through the profile points,
        or None if insufficient terrain hits to construct the profile.
    """
    pt      = station['point']
    tangent = station['tangent']
    normal  = station['normal']

    # Build the cross-section reference plane
    plane = build_cross_section_plane(pt, tangent, normal, tolerance)
    if plane is None:
        return None

    # Distribute profile points from -half_width to +half_width
    half_w   = road_width * 0.5
    offsets  = []
    if num_points < 3:
        num_points = 3

    for i in range(num_points):
        # Symmetric distribution centred at 0.0
        t_norm  = float(i) / (num_points - 1)       # 0.0 to 1.0
        offset  = -half_w + t_norm * road_width      # -w/2 to +w/2
        offsets.append(offset)

    profile_points = []

    for offset in offsets:
        # Translate station point along the cross-section X axis
        world_pt = pt + plane.XAxis * offset

        # Ray-cast to terrain at this XY location to get true Z
        z_terrain = cast_ray_to_terrain(
            terrain_geom, terrain_type,
            world_pt.X, world_pt.Y,
            tolerance
        )

        if z_terrain is not None:
            final_pt = rg.Point3d(world_pt.X, world_pt.Y,
                                   z_terrain + height_offset)
        else:
            # If the edge point misses terrain, project from the station
            # point Z with a Z offset proportional to terrain normal slope
            slope_z = (offset / half_w) * (
                normal.Z if abs(normal.Z) > tolerance else 1.0
            )
            final_pt = rg.Point3d(world_pt.X, world_pt.Y,
                                   pt.Z + height_offset)

        profile_points.append(final_pt)

    if len(profile_points) < 2:
        return None

    # Interpolate a smooth curve through the profile points
    degree  = min(3, len(profile_points) - 1)
    section_crv = rg.Curve.CreateInterpolatedCurve(
        profile_points,
        degree,
        rg.CurveKnotStyle.Uniform
    )

    if section_crv is None or not section_crv.IsValid:
        # Fallback to a line/polyline if interpolation fails
        polyline   = rg.Polyline(profile_points)
        section_crv = polyline.ToNurbsCurve()

    return section_crv


def generate_all_cross_sections(stations, road_width, num_points,
                                  terrain_geom, terrain_type,
                                  height_offset, tolerance):
    """
    Generates cross-section curves for every station on the projected
    centerline.

    Progress is printed to the console for long roads. Stations that fail
    to produce a valid section are skipped with a warning; the loft will
    still proceed with the remaining valid sections.

    Parameters
    ----------
    stations : list of dict
        Output of sample_curve_with_terrain_data().
    road_width : float
    num_points : int
    terrain_geom : Brep or Mesh
    terrain_type : str
    height_offset : float
    tolerance : float

    Returns
    -------
    list of Rhino.Geometry.Curve
        Valid cross-section curves; length may be less than len(stations)
        if some stations failed.
    """
    sections = []
    n_total  = len(stations)
    n_failed = 0

    for idx, station in enumerate(stations):
        section = create_cross_section_curve(
            station, road_width, num_points,
            terrain_geom, terrain_type,
            height_offset, tolerance
        )

        if section is not None and section.IsValid:
            sections.append(section)
        else:
            n_failed += 1

        # Print progress at 10% intervals for long roads
        progress_interval = max(1, n_total // 10)
        if (idx + 1) % progress_interval == 0 or (idx + 1) == n_total:
            pct = int(100.0 * (idx + 1) / n_total)
            print("  Cross-sections: {}/{} ({}%)".format(idx + 1, n_total, pct))

    if n_failed > 0:
        print("  Warning: {} station(s) failed cross-section "
              "generation.".format(n_failed))

    return sections


# =============================================================================
# LOFTING
# =============================================================================

def unify_cross_section_directions(sections):
    """
    Ensures all cross-section curves have consistent start/end orientation
    before lofting to prevent the surface from twisting.

    Strategy:
    - The first section is the reference.
    - For each subsequent section, if its start point is closer to the
      previous section's end point than start point, reverse it.
    - This handles cases where the road turns sharply and the cross-section
      orientation flips.

    Parameters
    ----------
    sections : list of Rhino.Geometry.Curve

    Returns
    -------
    list of Rhino.Geometry.Curve
        Curves with consistent orientation.
    """
    if len(sections) < 2:
        return sections

    corrected = [sections[0]]

    for i in range(1, len(sections)):
        prev_crv   = corrected[i - 1]
        curr_crv   = sections[i]

        prev_end   = prev_crv.PointAtEnd
        curr_start = curr_crv.PointAtStart
        curr_end   = curr_crv.PointAtEnd

        dist_start = prev_end.DistanceTo(curr_start)
        dist_end   = prev_end.DistanceTo(curr_end)

        if dist_end < dist_start:
            # Reverse this section so it aligns with the previous
            reversed_crv = curr_crv.DuplicateCurve()
            reversed_crv.Reverse()
            corrected.append(reversed_crv)
        else:
            corrected.append(curr_crv)

    return corrected


def create_road_surface(sections, tolerance):
    """
    Lofts the cross-section curves into a continuous NURBS road surface.

    Uses Brep.CreateFromLoft() with Normal loft type for smooth interpolation
    between sections. The loft is closed only if the first and last section
    positions are within tolerance of each other (loop road).

    Loft configuration:
    - Type: Normal (smooth interpolation, not ruled/straight-line)
    - Closed: auto-detected from start/end proximity
    - SplitAtTangents: False (avoids unwanted seams on curved roads)

    Parameters
    ----------
    sections : list of Rhino.Geometry.Curve
        Cross-section curves, must be direction-unified before calling.
    tolerance : float

    Returns
    -------
    Rhino.Geometry.Brep or None
        The road surface Brep. None if lofting fails.
    """
    if len(sections) < MIN_SECTIONS_FOR_LOFT:
        print("  Error: Insufficient sections for loft "
              "(have {}, need {}).".format(len(sections), MIN_SECTIONS_FOR_LOFT))
        return None

    # Detect if the road is a closed loop
    first_start = sections[0].PointAtStart
    last_end    = sections[-1].PointAtEnd
    is_closed   = first_start.DistanceTo(last_end) < tolerance * 10

    try:
        loft_breps = rg.Brep.CreateFromLoft(
            sections,
            rg.Point3d.Unset,   # no start point override
            rg.Point3d.Unset,   # no end point override
            rg.LoftType.Normal,
            is_closed           # closed loft for loop roads
        )
    except Exception as e:
        print("  Loft exception: {}".format(str(e)))
        return None

    if loft_breps is None or len(loft_breps) == 0:
        print("  Error: Loft returned no geometry.")
        return None

    # Join multiple loft pieces into a single Brep if needed
    if len(loft_breps) == 1:
        result = loft_breps[0]
    else:
        joined = rg.Brep.JoinBreps(loft_breps, tolerance)
        if joined and len(joined) > 0:
            result = joined[0]
        else:
            result = loft_breps[0]

    if result is None or not result.IsValid:
        print("  Warning: Loft result is invalid. "
              "Attempting Brep repair...")
        if result is not None:
            result.Repair(tolerance)

    return result


# =============================================================================
# OUTPUT - ADD GEOMETRY TO RHINO DOCUMENT
# =============================================================================

def add_curve_to_layer(curve, layer_name, name=None):
    """
    Adds a RhinoCommon curve to the Rhino document on the specified layer.

    Parameters
    ----------
    curve : Rhino.Geometry.Curve
    layer_name : str
    name : str or None
        Optional object name.

    Returns
    -------
    System.Guid or None
    """
    if curve is None or not curve.IsValid:
        return None

    obj_id = sc.doc.Objects.AddCurve(curve)
    if obj_id == System.Guid.Empty:
        return None

    add_object_to_layer(obj_id, layer_name)
    if name:
        rs.ObjectName(obj_id, name)

    return obj_id


def add_brep_to_layer(brep, layer_name, name=None):
    """
    Adds a RhinoCommon Brep to the Rhino document on the specified layer.

    Parameters
    ----------
    brep : Rhino.Geometry.Brep
    layer_name : str
    name : str or None

    Returns
    -------
    System.Guid or None
    """
    if brep is None or not brep.IsValid:
        return None

    obj_id = sc.doc.Objects.AddBrep(brep)
    if obj_id == System.Guid.Empty:
        return None

    add_object_to_layer(obj_id, layer_name)
    if name:
        rs.ObjectName(obj_id, name)

    return obj_id


def publish_results(projected_centerline, road_surface, cross_sections,
                    add_debug_sections):
    """
    Adds all output geometry to the Rhino document on their respective layers.

    Parameters
    ----------
    projected_centerline : Rhino.Geometry.Curve
    road_surface : Rhino.Geometry.Brep
    cross_sections : list of Rhino.Geometry.Curve
    add_debug_sections : bool
        If True, all cross-section curves are added to Roads_CrossSections.

    Returns
    -------
    dict with keys 'centerline_id', 'surface_id', 'section_ids'
    """
    ids = {
        'centerline_id': None,
        'surface_id':    None,
        'section_ids':   []
    }

    # Published 3D centerline
    cl_id = add_curve_to_layer(
        projected_centerline, LAYER_ROAD_CENTERLINE, "Road_3D_Centerline"
    )
    ids['centerline_id'] = cl_id

    if cl_id:
        print("  Roads_Centerline: 3D centerline added.")
    else:
        print("  Warning: Could not add centerline to document.")

    # Road surface
    surf_id = add_brep_to_layer(
        road_surface, LAYER_ROAD_SURFACE, "Road_Surface"
    )
    ids['surface_id'] = surf_id

    if surf_id:
        print("  Roads_Projected: Road surface added.")
    else:
        print("  Warning: Could not add road surface to document.")

    # Debug cross-sections
    if add_debug_sections:
        n_added = 0
        for i, section in enumerate(cross_sections):
            sec_id = add_curve_to_layer(
                section, LAYER_ROAD_SECTIONS,
                "CrossSection_{:04d}".format(i)
            )
            if sec_id:
                ids['section_ids'].append(sec_id)
                n_added += 1

        print("  Roads_CrossSections: {} section(s) added.".format(n_added))

    return ids


# =============================================================================
# STATISTICS AND REPORTING
# =============================================================================

def calculate_statistics(projected_curve, cross_sections, road_width,
                          spacing, doc_units):
    """
    Computes road adaptation statistics for the console report.

    Parameters
    ----------
    projected_curve : Rhino.Geometry.Curve
    cross_sections  : list of Rhino.Geometry.Curve
    road_width : float
    spacing : float
    doc_units : str

    Returns
    -------
    dict with statistical fields.
    """
    stats = {
        'length':          0.0,
        'z_min':           0.0,
        'z_max':           0.0,
        'z_range':         0.0,
        'section_count':   len(cross_sections),
        'valid_sections':  0,
        'surface_area_est': 0.0,
        'doc_units':       doc_units
    }

    if projected_curve is None or not projected_curve.IsValid:
        return stats

    # Arc-length of the 3D projected centerline
    stats['length'] = projected_curve.GetLength()

    # Z range from bounding box of projected curve
    bbox = projected_curve.GetBoundingBox(True)
    if bbox.IsValid:
        stats['z_min']   = bbox.Min.Z
        stats['z_max']   = bbox.Max.Z
        stats['z_range'] = bbox.Max.Z - bbox.Min.Z

    # Count valid sections
    stats['valid_sections'] = sum(
        1 for s in cross_sections if s is not None and s.IsValid
    )

    # Estimated surface area: length × road width (approximate for flat)
    stats['surface_area_est'] = stats['length'] * road_width

    return stats


def print_report(stats, terrain_name, road_name, params, output_ids):
    """
    Prints the formatted adaptation report to the Rhino Python console.

    Parameters
    ----------
    stats : dict
        Output of calculate_statistics().
    terrain_name : str
    road_name : str
    params : dict
        User parameters: 'road_width', 'spacing', 'height_offset',
        'num_profile_points', 'add_debug_sections'.
    output_ids : dict
        Output of publish_results().
    """
    units = stats['doc_units']
    sep   = "=" * 60

    print("\n" + sep)
    print("Road Adaptation to Topography v1.0.0")
    print(sep)

    print("\nInput Analysis:")
    print("  Terrain : {}".format(terrain_name))
    print("  Road    : {}".format(road_name))
    print("  Road width      : {:.2f} {}".format(params['road_width'], units))
    print("  Sample spacing  : {:.2f} {}".format(params['spacing'], units))
    print("  Height offset   : {:.2f} {}".format(params['height_offset'], units))
    print("  Profile points  : {}".format(params['num_profile_points']))

    print("\nProjection:")
    print("  Centerline length  : {:.2f} {}".format(stats['length'], units))
    print("  Z range            : {:.3f} to {:.3f} {} "
          "(elevation change: {:.3f} {})".format(
              stats['z_min'], stats['z_max'], units,
              stats['z_range'], units
          ))

    print("\nCross-Sections:")
    print("  Stations sampled   : {}".format(stats['section_count']))
    print("  Sections generated : {}".format(stats['valid_sections']))
    if stats['section_count'] > 0:
        pct = 100.0 * stats['valid_sections'] / stats['section_count']
        print("  Success rate       : {:.1f}%".format(pct))

    print("\nLofting:")
    if output_ids['surface_id']:
        print("  Road surface created: valid Brep / NURBS surface")
        print("  Estimated road area : {:.1f} {}2".format(
            stats['surface_area_est'], units
        ))
    else:
        print("  Road surface: FAILED (check cross-sections and terrain coverage)")

    print("\nLayers:")
    if output_ids['centerline_id']:
        print("  [OK] {}".format(LAYER_ROAD_CENTERLINE))
    else:
        print("  [--] {} (not created)".format(LAYER_ROAD_CENTERLINE))

    if output_ids['surface_id']:
        print("  [OK] {}".format(LAYER_ROAD_SURFACE))
    else:
        print("  [--] {} (not created)".format(LAYER_ROAD_SURFACE))

    if params['add_debug_sections']:
        n_secs = len(output_ids['section_ids'])
        print("  [OK] {} ({} sections)".format(LAYER_ROAD_SECTIONS, n_secs))
    else:
        print("  [--] {} (disabled - set in options)".format(LAYER_ROAD_SECTIONS))

    print("\nSummary:")
    if output_ids['surface_id']:
        print("  Road surface successfully adapted to topography.")
        print("  Use Ctrl+Z to undo all changes.")
    else:
        print("  Adaptation incomplete. Review warnings above.")
        print("  Common causes: road extends beyond terrain boundary,")
        print("  insufficient cross-section hits, or degenerate geometry.")

    print(sep + "\n")


# =============================================================================
# USER DIALOG - PARAMETER INPUT
# =============================================================================

def ask_layer_names():
    """
    Prompts the user for terrain and road layer names.

    Returns
    -------
    tuple : (terrain_layer_str, road_layer_str)
        Either may be None if the user cancels (presses Escape).
    """
    print("\nLayer configuration (press Enter to accept defaults):")

    terrain_layer = rs.GetString(
        message="Terrain layer name",
        defaultString=DEFAULT_TERRAIN_LAYER
    )
    if terrain_layer is None:
        return None, None

    terrain_layer = terrain_layer.strip() or DEFAULT_TERRAIN_LAYER

    road_layer = rs.GetString(
        message="Road geometry layer name",
        defaultString=DEFAULT_ROAD_LAYER
    )
    if road_layer is None:
        return None, None

    road_layer = road_layer.strip() or DEFAULT_ROAD_LAYER

    print("  Terrain layer: '{}'".format(terrain_layer))
    print("  Road layer   : '{}'".format(road_layer))

    return terrain_layer, road_layer


def ask_road_parameters():
    """
    Prompts the user for road adaptation parameters using Rhino dialogs.

    Each parameter shows the default value and accepts the user's override.
    Pressing Escape on any dialog cancels the entire script.

    Returns
    -------
    dict or None
        Keys: 'road_width', 'spacing', 'height_offset',
              'num_profile_points', 'add_debug_sections'.
        None if the user cancels any dialog.
    """
    print("\nRoad parameters (press Enter to accept defaults):")

    # Road width
    road_width = rs.GetReal(
        message="Road width (left edge to right edge)",
        number=DEFAULT_ROAD_WIDTH,
        minimum=0.1,
        maximum=1000.0
    )
    if road_width is None:
        return None

    # Sample spacing
    spacing = rs.GetReal(
        message="Sample spacing (distance between cross-sections)",
        number=DEFAULT_SAMPLE_SPACING,
        minimum=0.1,
        maximum=10000.0
    )
    if spacing is None:
        return None

    # Height offset
    height_offset = rs.GetReal(
        message="Height offset above terrain (0 = flush contact)",
        number=DEFAULT_HEIGHT_OFFSET,
        minimum=0.0,
        maximum=100.0
    )
    if height_offset is None:
        height_offset = DEFAULT_HEIGHT_OFFSET

    # Number of cross-section profile points via ListBox
    profile_options = [
        "3 points  (Left, Center, Right - flat profile, fastest)",
        "5 points  (Left, LShld, Center, RShld, Right - crowned)",
        "7 points  (Detailed crowned profile)",
        "9 points  (High-detail, use for gentle terrain)"
    ]
    profile_values  = [3, 5, 7, 9]

    profile_choice = rs.ListBox(
        items=profile_options,
        message="Cross-section profile density:",
        title="Road Adaptation - Profile Points",
        default=profile_options[0]
    )

    if profile_choice is None:
        return None

    num_points = profile_values[profile_options.index(profile_choice)]

    # Debug sections toggle
    debug_options = [
        "No  - Hide cross-sections (clean result only)",
        "Yes - Show cross-sections on Roads_CrossSections layer"
    ]
    debug_choice = rs.ListBox(
        items=debug_options,
        message="Add cross-section curves for debugging?",
        title="Road Adaptation - Debug Options",
        default=debug_options[0]
    )

    if debug_choice is None:
        return None

    add_debug = debug_choice.startswith("Yes")

    return {
        'road_width':          road_width,
        'spacing':             spacing,
        'height_offset':       height_offset,
        'num_profile_points':  num_points,
        'add_debug_sections':  add_debug
    }


# =============================================================================
# VALIDATION
# =============================================================================

def validate_terrain(terrain_id):
    """
    Validates that the terrain object is usable for road projection.

    Checks geometry type support, bounding box validity, and non-zero
    XY extent. Returns (True, '') on success or (False, msg) on failure.

    Parameters
    ----------
    terrain_id : System.Guid

    Returns
    -------
    tuple : (bool, str)
    """
    obj = sc.doc.Objects.Find(terrain_id)
    if obj is None:
        return False, "Terrain object not found in document."

    geom = obj.Geometry
    if not isinstance(geom, (rg.Brep, rg.Mesh, rg.Surface, rg.Extrusion)):
        return False, (
            "Unsupported terrain type: '{}'. "
            "Use a surface, polysurface, or mesh.".format(type(geom).__name__)
        )

    bbox = geom.GetBoundingBox(rg.Transform.Identity)
    if not bbox.IsValid:
        return False, "Terrain has an invalid bounding box."

    if (bbox.Max.X - bbox.Min.X) < DEFAULT_TOLERANCE:
        return False, "Terrain has zero X extent (degenerate geometry)."
    if (bbox.Max.Y - bbox.Min.Y) < DEFAULT_TOLERANCE:
        return False, "Terrain has zero Y extent (degenerate geometry)."

    return True, ""


def validate_road_object(road_id):
    """
    Validates that the road object can produce a usable centerline.

    Parameters
    ----------
    road_id : System.Guid

    Returns
    -------
    tuple : (bool, str)
    """
    obj = sc.doc.Objects.Find(road_id)
    if obj is None:
        return False, "Road object not found."

    geom = obj.Geometry
    if not isinstance(geom, (rg.Curve, rg.Brep, rg.Extrusion)):
        return False, (
            "Unsupported road type: '{}'. "
            "Use a curve, polyline, or surface.".format(type(geom).__name__)
        )

    if isinstance(geom, rg.Curve):
        if not geom.IsValid:
            return False, "Road curve is invalid."
        if geom.GetLength() < DEFAULT_TOLERANCE:
            return False, "Road curve is zero-length."

    return True, ""


# =============================================================================
# UNDO RECORD MANAGEMENT
# =============================================================================

def begin_undo_record(label):
    """Opens a Rhino undo record block. Returns the serial number."""
    try:
        return sc.doc.BeginUndoRecord(label)
    except Exception:
        return -1


def end_undo_record(serial_number):
    """Closes the undo record block identified by serial_number."""
    if serial_number >= 0:
        try:
            sc.doc.EndUndoRecord(serial_number)
        except Exception:
            pass


# =============================================================================
# ENTRY POINT
# =============================================================================

def main():
    """
    Main entry point for the road topography adapter script.

    Execution sequence:
    1.  Print header and read document context
    2.  Ask user for terrain and road layer names
    3.  Load terrain object from terrain layer (first object used)
    4.  Load road object from road layer (first object used)
    5.  Validate terrain and road geometry
    6.  Ask user for road parameters (width, spacing, profile, debug)
    7.  Extract road centerline from input geometry
    8.  Project centerline onto terrain (Brep or Mesh path)
    9.  Sample projected centerline at regular intervals with terrain normals
    10. Generate cross-section curve at each station
    11. Unify cross-section directions to prevent loft twisting
    12. Loft cross-sections into continuous road surface Brep
    13. Set up output layers and add all geometry to document
    14. Calculate and print statistics report
    15. Redraw viewports
    """
    print("\n" + "=" * 60)
    print("  ROAD TOPOGRAPHY ADAPTER  v1.0.0")
    print("=" * 60)
    print("  Projects 2D road geometry onto 3D terrain surface")
    print("  using Project Centerline -> Cross-Sections -> Loft.")
    print("  Full undo support: Ctrl+Z to revert all changes.")
    print("=" * 60)

    # --- Document context ---
    tolerance = sc.doc.ModelAbsoluteTolerance
    doc_units = rs.UnitSystemName(abbreviate=True)
    print("\nDocument: units={}, tolerance={}".format(doc_units, tolerance))

    # =========================================================================
    # Step 1: Ask for layer names
    # =========================================================================
    terrain_layer, road_layer = ask_layer_names()
    if terrain_layer is None or road_layer is None:
        print("Aborted: Layer selection cancelled.")
        return

    # =========================================================================
    # Step 2: Detect terrain object
    # =========================================================================
    print("\nDetecting terrain from layer '{}'...".format(terrain_layer))
    terrain_objects = get_objects_from_layer(terrain_layer)

    if not terrain_objects:
        rs.MessageBox(
            "No objects found on the '{}' layer.\n\n"
            "Place your terrain surface or mesh on that layer "
            "and run again.".format(terrain_layer),
            title="Road Adapter - No Terrain Found"
        )
        print("Aborted: No objects on terrain layer.")
        return

    terrain_id = terrain_objects[0]
    if len(terrain_objects) > 1:
        print("  Note: {} terrain objects found; using first.".format(
            len(terrain_objects)
        ))

    terrain_name = get_terrain_name(terrain_id)
    print("  Terrain: {}".format(terrain_name))

    # =========================================================================
    # Step 3: Detect road object
    # =========================================================================
    print("\nDetecting road geometry from layer '{}'...".format(road_layer))
    road_objects = get_objects_from_layer(road_layer)

    if not road_objects:
        rs.MessageBox(
            "No objects found on the '{}' layer.\n\n"
            "Place your road centerline curve or surface on that "
            "layer and run again.".format(road_layer),
            title="Road Adapter - No Road Found"
        )
        print("Aborted: No objects on road layer.")
        return

    road_id = road_objects[0]
    if len(road_objects) > 1:
        print("  Note: {} road objects found; using first.".format(
            len(road_objects)
        ))

    road_obj  = sc.doc.Objects.Find(road_id)
    road_name = (rs.ObjectName(road_id) or "<unnamed>") + (
        " ({})".format(type(road_obj.Geometry).__name__) if road_obj else ""
    )
    print("  Road: {}".format(road_name))

    # =========================================================================
    # Step 4: Validate geometry
    # =========================================================================
    print("\nValidating geometry...")

    t_valid, t_err = validate_terrain(terrain_id)
    if not t_valid:
        rs.MessageBox(
            "Terrain validation failed:\n\n{}".format(t_err),
            title="Road Adapter - Invalid Terrain"
        )
        print("Aborted: {}".format(t_err))
        return

    r_valid, r_err = validate_road_object(road_id)
    if not r_valid:
        rs.MessageBox(
            "Road validation failed:\n\n{}".format(r_err),
            title="Road Adapter - Invalid Road"
        )
        print("Aborted: {}".format(r_err))
        return

    print("  Terrain: valid")
    print("  Road   : valid")

    # =========================================================================
    # Step 5: Ask for road parameters
    # =========================================================================
    params = ask_road_parameters()
    if params is None:
        print("Aborted: Parameter dialog cancelled.")
        return

    road_width      = params['road_width']
    spacing         = params['spacing']
    height_offset   = params['height_offset']
    num_pts         = params['num_profile_points']
    add_debug       = params['add_debug_sections']

    print("\nParameters:")
    print("  Road width      : {:.2f} {}".format(road_width, doc_units))
    print("  Sample spacing  : {:.2f} {}".format(spacing, doc_units))
    print("  Height offset   : {:.2f} {}".format(height_offset, doc_units))
    print("  Profile points  : {}".format(num_pts))
    print("  Debug sections  : {}".format("Yes" if add_debug else "No"))

    # =========================================================================
    # Step 6: Extract terrain geometry
    # =========================================================================
    print("\nLoading terrain geometry...")
    terrain_geom, terrain_type = get_terrain_geometry(terrain_id)
    if terrain_geom is None:
        print("Aborted: Could not extract terrain geometry.")
        return
    print("  Terrain type: {}".format(terrain_type.upper()))

    # =========================================================================
    # Step 7: Extract road centerline
    # =========================================================================
    print("\nExtracting road centerline...")
    centerline = extract_centerline(road_id, tolerance)
    if centerline is None:
        print("Aborted: Centerline extraction failed.")
        return

    cl_length = centerline.GetLength()
    print("  2D centerline length : {:.2f} {}".format(cl_length, doc_units))

    # Warn if spacing produces fewer than 2 sections
    expected_sections = int(cl_length / spacing) + 1
    if expected_sections < MIN_SECTIONS_FOR_LOFT:
        rs.MessageBox(
            "The sample spacing ({:.2f}) is too large for the road length "
            "({:.2f}).\n\nExpected sections: {}\nMinimum required: {}\n\n"
            "Reduce the sample spacing or use a longer road.".format(
                spacing, cl_length, expected_sections, MIN_SECTIONS_FOR_LOFT
            ),
            title="Road Adapter - Spacing Too Large"
        )
        print("Aborted: Spacing too large for road length.")
        return

    # =========================================================================
    # Step 8: Open undo record and project centerline
    # =========================================================================
    rs.UnselectAllObjects()
    rs.EnableRedraw(False)
    undo_serial = begin_undo_record("AdaptRoadToTopography")

    try:
        print("\nProjection:")
        print("  Projecting centerline to terrain...")
        projected_cl = project_centerline_to_terrain(
            centerline, terrain_geom, terrain_type, tolerance
        )

        if projected_cl is None or not projected_cl.IsValid:
            print("  Error: Projection failed. Possible causes:")
            print("    - Road extends beyond terrain boundary")
            print("    - Terrain does not cover the road's XY extent")
            print("    - Projection direction (Z) does not intersect terrain")
            rs.MessageBox(
                "Centerline projection to terrain failed.\n\n"
                "Ensure the terrain covers the full XY extent of the road.\n"
                "Check that the road is drawn in plan view (XY plane).",
                title="Road Adapter - Projection Failed"
            )
            end_undo_record(undo_serial)
            rs.EnableRedraw(True)
            return

        proj_length = projected_cl.GetLength()
        proj_bbox   = projected_cl.GetBoundingBox(True)
        print("  Projected length : {:.2f} {}".format(proj_length, doc_units))
        print("  Z range          : {:.3f} to {:.3f} {}".format(
            proj_bbox.Min.Z, proj_bbox.Max.Z, doc_units
        ))

        # =====================================================================
        # Step 9: Sample projected centerline with terrain data
        # =====================================================================
        print("\nSampling:")
        stations = sample_curve_with_terrain_data(
            projected_cl, terrain_geom, terrain_type, spacing, tolerance
        )

        if not stations:
            print("  Error: Sampling produced no valid stations.")
            end_undo_record(undo_serial)
            rs.EnableRedraw(True)
            return

        print("  Stations created: {}".format(len(stations)))

        # =====================================================================
        # Step 10: Generate cross-sections
        # =====================================================================
        print("\nCross-Sections:")
        sections = generate_all_cross_sections(
            stations, road_width, num_pts,
            terrain_geom, terrain_type,
            height_offset, tolerance
        )

        if len(sections) < MIN_SECTIONS_FOR_LOFT:
            print("  Error: Only {} valid section(s) generated. "
                  "Minimum is {}.".format(len(sections), MIN_SECTIONS_FOR_LOFT))
            end_undo_record(undo_serial)
            rs.EnableRedraw(True)
            return

        print("  Valid sections: {}".format(len(sections)))

        # =====================================================================
        # Step 11: Unify cross-section directions
        # =====================================================================
        sections = unify_cross_section_directions(sections)

        # =====================================================================
        # Step 12: Loft road surface
        # =====================================================================
        print("\nLofting:")
        print("  Creating road surface from {} sections...".format(len(sections)))
        road_surface = create_road_surface(sections, tolerance)

        if road_surface is None:
            print("  Error: Loft failed to produce a road surface.")
            # Still publish the centerline and sections as debug output
        else:
            surf_valid = "valid" if road_surface.IsValid else "INVALID (check geometry)"
            print("  Road surface: {}".format(surf_valid))

        # =====================================================================
        # Step 13: Set up output layers and publish geometry
        # =====================================================================
        print("\nLayers:")
        setup_output_layers()

        output_ids = publish_results(
            projected_cl, road_surface, sections, add_debug
        )

        # =====================================================================
        # Step 14: Calculate and print statistics
        # =====================================================================
        stats = calculate_statistics(
            projected_cl, sections, road_width, spacing, doc_units
        )

        print_report(stats, terrain_name, road_name, params, output_ids)

    except Exception as exc:
        print("\nUnexpected error: {}".format(str(exc)))
        import traceback
        traceback.print_exc()

    finally:
        end_undo_record(undo_serial)
        rs.EnableRedraw(True)
        sc.doc.Views.Redraw()


# =============================================================================
# SCRIPT EXECUTION
# =============================================================================

if __name__ == "__main__":
    main()
