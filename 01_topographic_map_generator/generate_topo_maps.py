# -*- coding: utf-8 -*-
"""
topo_map_generator.py
---------------------
Architectural Topographic Map Generator for Rhino 7+
Generates contour lines from a CSV or E57 point cloud with architectural
styling.

Workflow:
    1. User selects a CSV/TXT/XYZ or E57 file containing XYZ point data
    2. Script auto-detects the file format and parses accordingly
    3. The point cloud is validated and optionally filtered
    4. A NURBS surface is fitted through the points using RhinoCommon
    5. Contour curves are extracted at a user-defined interval
    6. Every N-th contour is designated an "index" contour (thicker / darker)
    7. All geometry is placed on organized, colour-coded layers
    8. Optional DXF export is offered at the end

Supported Input Formats:
    CSV / TXT / XYZ  -- delimited text files with X Y Z columns
    E57              -- ISO 14694 3D imaging standard (Faro, Leica, etc.)
                        Requires the 'pye57' Python package for native support.
                        Falls back to Rhino's built-in E57 import command, or
                        instructs the user to convert to CSV.

Layer Organisation (example for 5-unit interval, index every 5):
    Topo_PointCloud          -- raw input points (optionally hidden)
    Topo_Surface             -- interpolated terrain surface
    Contours_0-50m           -- regular contours in 0-50 elevation band
    Contours_0-50m_Index     -- index contours in same band
    Contours_50-100m         -- etc.
    ...

Requires: Rhino 7+, RhinoCommon (included), rhinoscriptsyntax (included)
Optional: pye57 (pip install pye57) for native E57 reading
Author:   Generated for production use
"""

# ---------------------------------------------------------------------------
# Standard imports
# ---------------------------------------------------------------------------
import os
import csv
import math
import time
import struct
import tempfile

import Rhino
import Rhino.Geometry as rg
import rhinoscriptsyntax as rs
import scriptcontext as sc
import System.Drawing as sd

# ---------------------------------------------------------------------------
# Optional E57 library detection
# ---------------------------------------------------------------------------
# pyE57 is a third-party Python binding for the libE57Format C++ library.
# It is NOT bundled with Rhino; users must install it separately.
# Installation: pip install pyE57  (requires libE57Format native libs)
#
# Graceful degradation order:
#   1. pyE57 native Python binding  (full featured, preferred)
#   2. pye57 (alternate package name used by some distributions)
#   3. Rhino _Import command bridge  (limited: imports into doc, then extracts)
#   4. Inform user and offer CSV conversion guidance
# ---------------------------------------------------------------------------
_PYE57_AVAILABLE = False
_pye57_module    = None

try:
    import pye57 as _pye57_module
    _PYE57_AVAILABLE = True
except ImportError:
    pass

if not _PYE57_AVAILABLE:
    try:
        import pyE57 as _pye57_module
        _PYE57_AVAILABLE = True
    except ImportError:
        pass


# ===========================================================================
# CONSTANTS  –  edit these to change default behaviour
# ===========================================================================

DEFAULT_CONTOUR_INTERVAL = 5.0      # vertical distance between contours
DEFAULT_INDEX_EVERY       = 5       # every N-th contour becomes an index contour
DEFAULT_BAND_SIZE         = 50.0    # elevation range grouped into one layer band

# Line-weight token IDs used by Rhino (plotWeight in mm)
LW_REGULAR = 0.18   # regular contour plot weight  (mm)
LW_INDEX   = 0.50   # index contour plot weight     (mm)
LW_SURFACE = 0.09   # terrain surface plot weight   (mm)

# Surface fitting quality
SURFACE_U_DEGREE = 3
SURFACE_V_DEGREE = 3

# Maximum points to use for surface fitting (sparse large clouds for speed)
MAX_SURFACE_POINTS = 40000

# Outlier filtering: discard points beyond N standard deviations in Z
OUTLIER_SIGMA = 3.5

# Colour ramp for index contours (low → high elevation)
# Each entry: (normalised_value_0_to_1, R, G, B)
INDEX_COLOUR_RAMP = [
    (0.00,  41, 128, 185),   # deep blue  (low)
    (0.25,  39, 174,  96),   # green
    (0.50, 241, 196,  15),   # amber
    (0.75, 230, 126,  34),   # orange
    (1.00, 192,  57,  43),   # red        (high)
]


# ===========================================================================
# UTILITY HELPERS
# ===========================================================================

def _lerp(a, b, t):
    """Linear interpolation between a and b by factor t."""
    return a + (b - a) * t


def _colour_from_ramp(t, ramp=INDEX_COLOUR_RAMP):
    """
    Sample a colour from a multi-stop ramp.

    Parameters
    ----------
    t    : float  normalised elevation value [0, 1]
    ramp : list   of (t, R, G, B) tuples, sorted by t

    Returns
    -------
    System.Drawing.Color
    """
    t = max(0.0, min(1.0, t))
    for i in range(len(ramp) - 1):
        t0, r0, g0, b0 = ramp[i]
        t1, r1, g1, b1 = ramp[i + 1]
        if t0 <= t <= t1:
            f = (t - t0) / (t1 - t0) if (t1 - t0) > 0 else 0.0
            return sd.Color.FromArgb(
                int(_lerp(r0, r1, f)),
                int(_lerp(g0, g1, f)),
                int(_lerp(b0, b1, f))
            )
    # fallback to last stop
    return sd.Color.FromArgb(*ramp[-1][1:])


def _print(msg):
    """Print with a consistent prefix so messages are easy to spot."""
    print("[TopoMap] {}".format(msg))


def _progress(label, current, total):
    """Print a simple progress indicator."""
    pct = int(100 * current / total) if total else 0
    bar_len = 30
    filled = int(bar_len * current / total) if total else 0
    bar = "#" * filled + "-" * (bar_len - filled)
    print("[TopoMap] {} |{}| {}%   ({}/{})".format(
        label, bar, pct, current, total))


# ===========================================================================
# 1. POINT CLOUD LOADING
# ===========================================================================

def detect_delimiter(filepath, sample_bytes=4096):
    """
    Sniff the delimiter used in a delimited text file.

    Tries csv.Sniffer first; falls back to testing common delimiters.

    Parameters
    ----------
    filepath     : str   path to the file
    sample_bytes : int   bytes to read for detection

    Returns
    -------
    str  one of ',' '\\t' ' ' ';'
    """
    with open(filepath, "r") as fh:
        sample = fh.read(sample_bytes)
    try:
        dialect = csv.Sniffer().sniff(sample, delimiters=",\t ;")
        return dialect.delimiter
    except csv.Error:
        # Manual fallback: pick delimiter that produces the most columns
        counts = {d: sample.count(d) for d in (",", "\t", " ", ";")}
        return max(counts, key=counts.get)


def has_header(filepath, delimiter):
    """
    Detect whether the first row of a CSV is a text header.

    Returns True if the first non-empty, non-comment row cannot be parsed
    as three floats.

    Parameters
    ----------
    filepath  : str
    delimiter : str

    Returns
    -------
    bool
    """
    with open(filepath, "r") as fh:
        for line in fh:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            parts = line.split(delimiter)
            if len(parts) < 3:
                return False
            try:
                float(parts[0])
                float(parts[1])
                float(parts[2])
                return False
            except ValueError:
                return True
    return False


def _detect_file_format(filepath):
    """
    Determine whether a file is an E57 point cloud or a delimited text file
    based on file extension and, for ambiguous extensions, a magic-byte check.

    E57 files begin with the ASCII signature 'ASTM-E57' at byte offset 0.

    Parameters
    ----------
    filepath : str  absolute path to the file

    Returns
    -------
    str  one of 'e57' or 'csv'
    """
    _, ext = os.path.splitext(filepath)
    ext_lower = ext.lower()

    if ext_lower == ".e57":
        return "e57"

    if ext_lower in (".csv", ".txt", ".xyz", ".asc", ".pts"):
        return "csv"

    # Ambiguous extension: check for E57 magic bytes
    # ISO 14694 specifies the first 4 bytes are "ASTM" when using the
    # binary XML page structure that is the universal E57 encoding.
    try:
        with open(filepath, "rb") as fh:
            magic = fh.read(4)
        if magic == b"ASTM":
            return "e57"
    except (IOError, OSError):
        pass

    # Default: treat as delimited text
    return "csv"


def _load_pointcloud_csv(filepath):
    """
    Parse a delimited text/CSV file and return a list of (x, y, z) tuples.

    Handles:
    - Comma, tab, space, and semicolon delimiters (auto-detected)
    - Optional text header row (auto-detected)
    - Comment lines beginning with '#'
    - Extra columns beyond the first three (silently ignored)
    - Rows with missing or non-numeric values (warned and skipped)

    Parameters
    ----------
    filepath : str  absolute path to the CSV/TXT file

    Returns
    -------
    list of (float, float, float)  raw XYZ points

    Raises
    ------
    IOError   if file cannot be opened
    ValueError if fewer than 3 valid points are found
    """
    if not os.path.isfile(filepath):
        raise IOError("File not found: {}".format(filepath))

    delimiter = detect_delimiter(filepath)
    skip_header = has_header(filepath, delimiter)

    _print("Delimiter detected: {!r}  |  Header row: {}".format(
        delimiter, skip_header))

    points = []
    bad_rows = 0
    row_index = 0

    with open(filepath, "r") as fh:
        for raw_line in fh:
            line = raw_line.strip()

            # Skip blanks and comment lines
            if not line or line.startswith("#"):
                continue

            # Skip header
            if skip_header and row_index == 0:
                row_index += 1
                continue

            row_index += 1
            parts = line.split(delimiter)

            if len(parts) < 3:
                bad_rows += 1
                continue

            try:
                x = float(parts[0])
                y = float(parts[1])
                z = float(parts[2])
                points.append((x, y, z))
            except ValueError:
                bad_rows += 1
                continue

    if bad_rows:
        _print("Warning: {} rows skipped (parse errors or insufficient columns)."
               .format(bad_rows))

    if len(points) < 3:
        raise ValueError(
            "Too few valid points loaded ({}).  "
            "Check file format and delimiter.".format(len(points)))

    _print("Loaded {:,} points from '{}'.".format(
        len(points), os.path.basename(filepath)))
    return points


def _load_pointcloud_e57(filepath):
    """
    Read an E57 file (ISO 14694) and return a list of (x, y, z) tuples.

    Loading strategy (in priority order):
        1. pye57 / pyE57 native Python binding  -- full feature support,
           handles multiple scan positions, intensity, and colour data.
        2. Rhino _Import command bridge         -- imports E57 directly into
           the document, extracts point cloud geometry, then removes the
           temporary objects.  Works without any extra Python libraries but
           is slower and leaves the Undo stack dirty.
        3. Graceful failure with conversion guidance.

    Multiple scan positions (scans) are combined into a single flat list.
    Intensity and colour data, when present, are read but not currently
    forwarded (they are logged for informational purposes only).  Future
    extension can expose them by returning a richer data structure.

    Parameters
    ----------
    filepath : str  absolute path to the .e57 file

    Returns
    -------
    list of (float, float, float)  XYZ points in file coordinate system

    Raises
    ------
    IOError   if the file cannot be opened
    ValueError if the file is not a valid E57 or contains no XYZ data
    RuntimeError if no loading strategy succeeds
    """
    if not os.path.isfile(filepath):
        raise IOError("E57 file not found: {}".format(filepath))

    _print("E57 format detected: '{}'".format(os.path.basename(filepath)))

    # ------------------------------------------------------------------
    # Strategy 1 – pye57 / pyE57 native binding
    # ------------------------------------------------------------------
    if _PYE57_AVAILABLE:
        return _load_e57_via_pye57(filepath)

    # ------------------------------------------------------------------
    # Strategy 2 – Rhino built-in _Import command bridge
    # ------------------------------------------------------------------
    _print("pye57 library not available.  "
           "Attempting Rhino built-in E57 import...")
    points = _load_e57_via_rhino_import(filepath)
    if points is not None:
        return points

    # ------------------------------------------------------------------
    # Strategy 3 – Graceful failure with user guidance
    # ------------------------------------------------------------------
    guidance = (
        "Could not read '{}' as E57.\n\n"
        "To enable native E57 support, install the pye57 library:\n"
        "  1. Open a terminal / command prompt.\n"
        "  2. Run:  pip install pye57\n"
        "  3. Restart Rhino.\n\n"
        "Alternatively, convert the E57 file to CSV using:\n"
        "  - CloudCompare (free, open source): File > Save As > ASCII\n"
        "  - Faro SCENE: Export > XYZ\n"
        "  - Leica Cyclone: Export > CSV\n"
        "  Then re-run this script with the CSV file."
    ).format(os.path.basename(filepath))

    raise RuntimeError(guidance)


def _load_e57_via_pye57(filepath):
    """
    Load an E57 file using the pye57 / pyE57 Python binding.

    Iterates over all scan positions in the file and accumulates XYZ
    coordinates into a single flat list.  Logs per-scan statistics.

    Parameters
    ----------
    filepath : str

    Returns
    -------
    list of (float, float, float)

    Raises
    ------
    ValueError  if no XYZ data is found across all scans
    Exception   propagated from pye57 for file corruption or unsupported
                E57 variants
    """
    _print("Reading E57 with pye57 library...")

    try:
        e57_file = _pye57_module.E57(filepath)
    except Exception as ex:
        raise ValueError(
            "Failed to open E57 file: {}\n"
            "The file may be corrupted or use an unsupported E57 variant."
            .format(ex))

    scan_count = e57_file.scan_count
    _print("E57 file contains {} scan position(s).".format(scan_count))

    if scan_count == 0:
        raise ValueError(
            "E57 file '{}' contains no scan positions."
            .format(os.path.basename(filepath)))

    all_points = []

    for scan_idx in range(scan_count):
        _print("  Reading scan {} / {}...".format(scan_idx + 1, scan_count))

        try:
            # pye57 returns a dict-like object; keys vary by E57 content.
            # Standard cartesian keys are 'cartesianX', 'cartesianY', 'cartesianZ'.
            # Some variants use 'x', 'y', 'z' (older pye57 versions).
            raw_data = e57_file.read_scan(
                scan_idx,
                ignore_missing_fields=True,
                row_column=False
            )
        except Exception as ex:
            _print("  Warning: scan {} read error: {}.  Skipping.".format(
                scan_idx, ex))
            continue

        # Resolve coordinate array keys (handle both naming conventions)
        xs = _resolve_e57_array(raw_data, ("cartesianX", "x", "X"))
        ys = _resolve_e57_array(raw_data, ("cartesianY", "y", "Y"))
        zs = _resolve_e57_array(raw_data, ("cartesianZ", "z", "Z"))

        if xs is None or ys is None or zs is None:
            _print("  Warning: scan {} has no cartesian XYZ data.  "
                   "Skipping.".format(scan_idx))
            continue

        # Validate lengths match
        n = len(xs)
        if len(ys) != n or len(zs) != n:
            _print("  Warning: scan {} coordinate arrays have mismatched "
                   "lengths.  Skipping.".format(scan_idx))
            continue

        # Log optional metadata
        has_intensity = _resolve_e57_array(
            raw_data, ("intensity", "Intensity")) is not None
        has_colour = _resolve_e57_array(
            raw_data, ("colorRed", "red", "r")) is not None

        _print("  Scan {}: {:,} points  |  intensity: {}  |  colour: {}".format(
            scan_idx, n,
            "yes" if has_intensity else "no",
            "yes" if has_colour    else "no"))

        # Collect valid (non-NaN, non-Inf) points
        scan_pts = []
        bad = 0
        for i in range(n):
            try:
                x = float(xs[i])
                y = float(ys[i])
                z = float(zs[i])
                # Guard against NaN / Inf from invalid scan returns
                if (x != x or y != y or z != z or          # NaN check
                        x > 1e15 or y > 1e15 or z > 1e15 or  # Inf-like
                        x < -1e15 or y < -1e15 or z < -1e15):
                    bad += 1
                    continue
                scan_pts.append((x, y, z))
            except (ValueError, TypeError):
                bad += 1

        if bad:
            _print("  Scan {}: {:,} invalid returns discarded.".format(
                scan_idx, bad))

        all_points.extend(scan_pts)
        _print("  Scan {} loaded: {:,} valid points.".format(
            scan_idx, len(scan_pts)))

    if not all_points:
        raise ValueError(
            "E57 file '{}' yielded no valid XYZ points across {} scan(s)."
            .format(os.path.basename(filepath), scan_count))

    _print("E57 total: {:,} points loaded from {} scan(s).".format(
        len(all_points), scan_count))

    # Validate coordinate ranges are physically plausible
    _validate_e57_coordinate_ranges(all_points, filepath)

    return all_points


def _resolve_e57_array(data_dict, candidate_keys):
    """
    Return the first array found in data_dict matching any of the candidate
    keys, or None if none are present.

    Parameters
    ----------
    data_dict      : dict  raw scan data from pye57
    candidate_keys : tuple of str  key names to try in priority order

    Returns
    -------
    array-like or None
    """
    for key in candidate_keys:
        if key in data_dict:
            arr = data_dict[key]
            # Guard against empty arrays
            if arr is not None and len(arr) > 0:
                return arr
    return None


def _validate_e57_coordinate_ranges(points, filepath):
    """
    Validate that E57 XYZ coordinates are within a physically plausible range
    for terrestrial surveying data.

    Logs a warning (not an error) if coordinates exceed typical surveying
    extents (> 1,000,000 units) -- this may indicate a coordinate system
    mismatch (e.g. global UTM coordinates vs. local site coordinates) which
    is normal for raw survey data and handled downstream.

    Parameters
    ----------
    points   : list of (x, y, z)
    filepath : str  used for diagnostic messages only
    """
    xs = [p[0] for p in points]
    ys = [p[1] for p in points]
    zs = [p[2] for p in points]

    x_range = max(xs) - min(xs)
    y_range = max(ys) - min(ys)
    z_range = max(zs) - min(zs)

    _print("E57 coordinate extents:")
    _print("  X: {:.3f}  to  {:.3f}  (span {:.3f})".format(
        min(xs), max(xs), x_range))
    _print("  Y: {:.3f}  to  {:.3f}  (span {:.3f})".format(
        min(ys), max(ys), y_range))
    _print("  Z: {:.3f}  to  {:.3f}  (span {:.3f})".format(
        min(zs), max(zs), z_range))

    # Warn about very large absolute coordinates (UTM / geocentric)
    max_abs = max(abs(min(xs)), abs(max(xs)),
                  abs(min(ys)), abs(max(ys)))
    if max_abs > 500000.0:
        _print(
            "Warning: large absolute coordinates detected ({:.0f} units max).\n"
            "  The E57 data may use a global coordinate system (UTM, ECEF).\n"
            "  Consider transforming to a local site origin before use.\n"
            "  The script will proceed, but Rhino display performance may\n"
            "  be affected by large world coordinates.".format(max_abs))

    # Warn about suspiciously small or degenerate point cloud extents
    if z_range < 1e-6:
        _print(
            "Warning: Z range is essentially zero ({:.6f}).\n"
            "  All points appear to be co-planar.  "
            "Contour generation may produce no results.".format(z_range))


def _load_e57_via_rhino_import(filepath):
    """
    Fallback E57 loader: use Rhino's built-in _Import command to bring the
    E57 file into the document, harvest the resulting point cloud objects,
    then delete them from the document.

    This approach works on Rhino 7+ which ships with built-in E57 import
    support.  It does not require any extra Python libraries.

    Limitations:
    - Rhino must support the specific E57 variant in the file.
    - The undo stack is modified (one undo block wraps the import/delete).
    - For very large files this can be slow due to Rhino's import pipeline.
    - Only cartesian XYZ is extracted; intensity/colour are discarded.

    Parameters
    ----------
    filepath : str

    Returns
    -------
    list of (float, float, float)  or None if import fails
    """
    doc = sc.doc

    # Snapshot of existing object GUIDs before import
    existing_guids = set(
        obj.Id for obj in doc.Objects
        if obj.IsValid and not obj.IsDeleted
    )

    # Run Rhino import via command string
    safe_path = filepath.replace("\\", "/")
    cmd = '_-Import "{}" _Enter'.format(safe_path)

    _print("Running Rhino E57 import command...")
    result = rs.Command(cmd, False)

    if not result:
        _print("Rhino _Import command returned failure.")
        return None

    # Identify newly added objects
    all_guids_after = set(
        obj.Id for obj in doc.Objects
        if obj.IsValid and not obj.IsDeleted
    )
    new_guids = all_guids_after - existing_guids

    if not new_guids:
        _print("Rhino _Import succeeded but added no new objects.")
        return None

    _print("Rhino import created {} new object(s).".format(len(new_guids)))

    points = []
    guids_to_delete = list(new_guids)

    for guid in new_guids:
        obj = doc.Objects.FindId(guid)
        if obj is None:
            continue

        geom = obj.Geometry

        # Handle PointCloud geometry type (Rhino 7 E57 import result)
        if isinstance(geom, rg.PointCloud):
            cloud_pts = geom.GetPoints()
            if cloud_pts:
                for pt in cloud_pts:
                    points.append((pt.X, pt.Y, pt.Z))
            _print("  Extracted {:,} points from PointCloud object.".format(
                len(cloud_pts) if cloud_pts else 0))

        # Handle individual Point objects (less common but possible)
        elif isinstance(geom, rg.Point):
            pt = geom.Location
            points.append((pt.X, pt.Y, pt.Z))

    # Remove imported objects from the document
    for guid in guids_to_delete:
        doc.Objects.Delete(guid, True)

    doc.Views.Redraw()

    if not points:
        _print("No point data could be extracted from Rhino's E57 import.")
        return None

    _print("Rhino E57 bridge: extracted {:,} points.".format(len(points)))
    _validate_e57_coordinate_ranges(points, filepath)
    return points


def load_point_cloud(filepath):
    """
    Format-aware point cloud dispatcher.

    Detects whether `filepath` is an E57 binary file or a delimited text
    file (CSV/TXT/XYZ) and calls the appropriate loader.

    Both loaders return the same data structure so all downstream processing
    (statistics, filtering, surface generation, contouring) is unchanged.

    Parameters
    ----------
    filepath : str  absolute path to the point cloud file

    Returns
    -------
    list of (float, float, float)  XYZ points

    Raises
    ------
    IOError      if the file cannot be found or opened
    ValueError   if the file contains no valid XYZ data
    RuntimeError if E57 loading fails and no fallback succeeds
    """
    fmt = _detect_file_format(filepath)

    if fmt == "e57":
        _print("Format detected: E57 (ISO 14694 3D imaging)")
        return _load_pointcloud_e57(filepath)
    else:
        _print("Format detected: delimited text (CSV/TXT/XYZ)")
        return _load_pointcloud_csv(filepath)


# ===========================================================================
# 2. POINT CLOUD VALIDATION & STATISTICS
# ===========================================================================

def compute_statistics(points):
    """
    Compute bounding box, mean, and standard deviation for a point list.

    Parameters
    ----------
    points : list of (x, y, z)

    Returns
    -------
    dict with keys:
        x_min, x_max, y_min, y_max, z_min, z_max,
        z_mean, z_std, count, x_range, y_range, z_range
    """
    xs = [p[0] for p in points]
    ys = [p[1] for p in points]
    zs = [p[2] for p in points]

    n = len(points)
    z_mean = sum(zs) / n
    z_var  = sum((z - z_mean) ** 2 for z in zs) / n
    z_std  = math.sqrt(z_var)

    return {
        "count":   n,
        "x_min":   min(xs),  "x_max": max(xs),
        "y_min":   min(ys),  "y_max": max(ys),
        "z_min":   min(zs),  "z_max": max(zs),
        "z_mean":  z_mean,
        "z_std":   z_std,
        "x_range": max(xs) - min(xs),
        "y_range": max(ys) - min(ys),
        "z_range": max(zs) - min(zs),
    }


def normalize_coordinates(points, stats):
    """
    Translate point coordinates to a local origin for better numerical precision
    during surface fitting. Large absolute coordinates (e.g. UTM > 300,000)
    cause floating-point precision loss in RhinoCommon algorithms.

    Parameters
    ----------
    points : list of (x, y, z)
    stats  : dict  from compute_statistics()

    Returns
    -------
    tuple (normalized_points, origin)
        normalized_points : list of (x, y, z) with origin at (0, 0, z_min)
        origin : tuple (orig_x_min, orig_y_min, orig_z_min) for denormalization
    """
    origin = (stats["x_min"], stats["y_min"], stats["z_min"])
    normalized = [
        (p[0] - origin[0], p[1] - origin[1], p[2] - origin[2])
        for p in points
    ]
    _print("Coordinate normalization: shifting origin by ({:.1f}, {:.1f}, {:.1f})".format(
        origin[0], origin[1], origin[2]))
    return normalized, origin


def denormalize_coordinates(points, origin):
    """
    Reverse the coordinate normalization to restore original UTM/global coords.

    Parameters
    ----------
    points : list of (x, y, z)  in normalized space
    origin : tuple (orig_x, orig_y, orig_z)

    Returns
    -------
    list of (x, y, z)  back in original coordinate system
    """
    return [
        (p[0] + origin[0], p[1] + origin[1], p[2] + origin[2])
        for p in points
    ]


def filter_outliers(points, sigma=OUTLIER_SIGMA):
    """
    Remove elevation outliers beyond `sigma` standard deviations from the mean.

    Parameters
    ----------
    points : list of (x, y, z)
    sigma  : float  standard deviation multiplier

    Returns
    -------
    list of (x, y, z)  cleaned point list
    """
    stats = compute_statistics(points)
    z_lo = stats["z_mean"] - sigma * stats["z_std"]
    z_hi = stats["z_mean"] + sigma * stats["z_std"]

    filtered = [p for p in points if z_lo <= p[2] <= z_hi]
    removed = len(points) - len(filtered)

    if removed:
        _print("Outlier filter ({}σ): removed {:,} points  "
               "(z outside [{:.2f}, {:.2f}]).".format(
                   sigma, removed, z_lo, z_hi))
    return filtered


def thin_points(points, target_count=MAX_SURFACE_POINTS):
    """
    Uniformly subsample a point list to at most `target_count` points.

    Uses a deterministic stride so the spatial distribution is even.

    Parameters
    ----------
    points       : list of (x, y, z)
    target_count : int

    Returns
    -------
    list of (x, y, z)
    """
    n = len(points)
    if n <= target_count:
        return points

    stride = n // target_count
    thinned = points[::stride][:target_count]
    _print("Thinned {:,} → {:,} points for surface fitting.".format(n, len(thinned)))
    return thinned


# ===========================================================================
# 3. LAYER MANAGEMENT
# ===========================================================================

class LayerManager:
    """
    Creates and caches Rhino layers for the topographic map output.

    Layer hierarchy:
        Topo_PointCloud
        Topo_Surface
        Contours_<band_lo>-<band_hi>m
            Contours_<band_lo>-<band_hi>m::Regular
            Contours_<band_lo>-<band_hi>m::Index

    The band parent layer colour matches the mid-elevation colour on the ramp.
    """

    def __init__(self, z_min, z_max, band_size=DEFAULT_BAND_SIZE):
        """
        Parameters
        ----------
        z_min     : float  minimum elevation in dataset
        z_max     : float  maximum elevation in dataset
        band_size : float  elevation span per layer group
        """
        self.z_min    = z_min
        self.z_max    = z_max
        self.band_size = band_size
        self._cache   = {}  # name → layer index

    # ------------------------------------------------------------------
    def _get_or_create(self, name, parent_name=None, colour=None,
                       plot_weight=None):
        """
        Return the Rhino layer index for `name`, creating it if absent.

        Parameters
        ----------
        name        : str   full layer name (Rhino uses '::' as separator)
        parent_name : str   parent layer name (created first if needed)
        colour      : System.Drawing.Color or None
        plot_weight : float  plot weight in mm, or None to leave default

        Returns
        -------
        int  Rhino layer table index
        """
        if name in self._cache:
            return self._cache[name]

        doc = sc.doc
        lt  = doc.Layers

        idx = lt.FindByFullPath(name, Rhino.RhinoMath.UnsetIntIndex)
        if idx >= 0:
            self._cache[name] = idx
            return idx

        layer = Rhino.DocObjects.Layer()
        # Rhino layer name is the leaf; parent is set separately
        parts = name.split("::")
        layer.Name = parts[-1]

        if colour is not None:
            layer.Color = colour
        if plot_weight is not None:
            layer.PlotWeight = plot_weight

        if parent_name is not None:
            parent_idx = self._cache.get(parent_name)
            if parent_idx is None:
                parent_idx = lt.FindByFullPath(
                    parent_name, Rhino.RhinoMath.UnsetIntIndex)
            if parent_idx >= 0:
                layer.ParentLayerId = lt[parent_idx].Id

        idx = lt.Add(layer)
        self._cache[name] = idx
        return idx

    # ------------------------------------------------------------------
    def create_base_layers(self):
        """Create the top-level organisational layers."""
        self._get_or_create(
            "Topo_PointCloud",
            colour=sd.Color.FromArgb(180, 180, 180),
            plot_weight=0.09)

        self._get_or_create(
            "Topo_Surface",
            colour=sd.Color.FromArgb(200, 220, 240),
            plot_weight=LW_SURFACE)

    # ------------------------------------------------------------------
    def _band_label(self, band_lo, band_hi):
        """Return a short string like 'Contours_0-50m'."""
        return "Contours_{}-{}m".format(int(band_lo), int(band_hi))

    # ------------------------------------------------------------------
    def _band_colour(self, band_lo, band_hi):
        """Colour for the band parent layer based on its mid elevation."""
        mid_z = (band_lo + band_hi) / 2.0
        t = (mid_z - self.z_min) / (self.z_max - self.z_min) \
            if (self.z_max - self.z_min) > 0 else 0.5
        return _colour_from_ramp(t)

    # ------------------------------------------------------------------
    def get_regular_layer(self, elevation):
        """
        Return the layer index for a regular contour at `elevation`.

        Creates the band and sub-layers on first access.

        Parameters
        ----------
        elevation : float

        Returns
        -------
        int  Rhino layer table index
        """
        band_lo = math.floor(elevation / self.band_size) * self.band_size
        band_hi = band_lo + self.band_size
        parent  = self._band_label(band_lo, band_hi)
        child   = "{}::Regular".format(parent)

        if parent not in self._cache:
            band_col = self._band_colour(band_lo, band_hi)
            self._get_or_create(parent, colour=band_col)

        if child not in self._cache:
            self._get_or_create(
                child,
                parent_name=parent,
                colour=sd.Color.FromArgb(100, 100, 100),
                plot_weight=LW_REGULAR)

        return self._cache[child]

    # ------------------------------------------------------------------
    def get_index_layer(self, elevation):
        """
        Return the layer index for an index contour at `elevation`.

        Parameters
        ----------
        elevation : float

        Returns
        -------
        int  Rhino layer table index
        """
        band_lo = math.floor(elevation / self.band_size) * self.band_size
        band_hi = band_lo + self.band_size
        parent  = self._band_label(band_lo, band_hi)
        child   = "{}::Index".format(parent)

        if parent not in self._cache:
            band_col = self._band_colour(band_lo, band_hi)
            self._get_or_create(parent, colour=band_col)

        if child not in self._cache:
            # Index layer colour comes from the elevation ramp
            t = (elevation - self.z_min) / (self.z_max - self.z_min) \
                if (self.z_max - self.z_min) > 0 else 0.5
            idx_col = _colour_from_ramp(t)
            self._get_or_create(
                child,
                parent_name=parent,
                colour=idx_col,
                plot_weight=LW_INDEX)

        return self._cache[child]


# ===========================================================================
# 4. SURFACE GENERATION
# ===========================================================================

def build_surface_from_points(points, stats):
    """
    Fit a NURBS surface through the point cloud using RhinoCommon's
    NurbsSurface.CreateThroughPoints for structured grids, or
    Brep.CreateFromMesh for unstructured clouds (via Delaunay mesh).

    Strategy:
        - If the point cloud is on a regular grid (detected by aspect ratio
          and count matching a reasonable U x V grid), use
          NurbsSurface.CreateThroughPoints.
        - Otherwise, triangulate via Rhino's Mesh.CreateFromPointCloud and
          fit a surface patch (or keep the mesh for contouring).

    Parameters
    ----------
    points : list of (x, y, z)  thinned point cloud
    stats  : dict               from compute_statistics()

    Returns
    -------
    tuple (geometry, is_mesh)
        geometry : Rhino.Geometry.NurbsSurface or Rhino.Geometry.Mesh
        is_mesh  : bool  True when a mesh was returned instead of a surface
    """
    _print("Building terrain surface from {:,} points...".format(len(points)))

    # Convert to Point3d list (RhinoCommon accepts Python lists directly)
    rhino_pts = [rg.Point3d(p[0], p[1], p[2]) for p in points]

    # ---- Attempt structured NURBS fit --------------------------------
    # Estimate grid dimensions from point count and XY aspect ratio
    count = len(points)
    aspect = (stats["x_range"] / stats["y_range"]
              if stats["y_range"] > 0 else 1.0)

    # candidate U count such that V = count/U and aspect ≈ U/V
    u_candidate = int(math.sqrt(count * aspect))
    v_candidate = count // max(u_candidate, 1)

    use_nurbs = (
        u_candidate >= 2
        and v_candidate >= 2
        and abs(u_candidate * v_candidate - count) < count * 0.05
    )

    if use_nurbs:
        _print("Detected structured grid  (~{}×{}).  "
               "Using NurbsSurface.CreateThroughPoints.".format(
                   u_candidate, v_candidate))
        try:
            surf = rg.NurbsSurface.CreateThroughPoints(
                rhino_pts,
                u_candidate,
                v_candidate,
                SURFACE_U_DEGREE,
                SURFACE_V_DEGREE,
                False,   # closedU
                False    # closedV
            )
            if surf is not None and surf.IsValid:
                bbox = surf.GetBoundingBox(rg.Plane.WorldXY)
                _print("NURBS surface created successfully.")
                _print("  Surface bbox: X={:.2f}..{:.2f}, Y={:.2f}..{:.2f}, "
                       "Z={:.2f}..{:.2f}".format(
                           bbox.Min.X, bbox.Max.X, bbox.Min.Y, bbox.Max.Y,
                           bbox.Min.Z, bbox.Max.Z))
                return surf, False
            else:
                _print("NurbsSurface.CreateThroughPoints returned invalid "
                       "result.  Falling back to mesh.")
        except Exception as ex:
            _print("NURBS fit failed: {}.  Falling back to mesh.".format(ex))

    # ---- Fallback: Delaunay mesh → surface ---------------------------
    _print("Using Delaunay mesh triangulation for unstructured cloud.")

    mesh = _build_delaunay_mesh(points, stats)
    if mesh is None:
        raise RuntimeError(
            "Surface generation failed.  Check point cloud quality.")

    bbox = mesh.GetBoundingBox(rg.Plane.WorldXY)
    _print("Mesh surface created: {} faces, {} vertices".format(
        mesh.Faces.Count, mesh.Vertices.Count))
    _print("  Mesh bbox: X={:.2f}..{:.2f}, Y={:.2f}..{:.2f}, "
           "Z={:.2f}..{:.2f}".format(
               bbox.Min.X, bbox.Max.X, bbox.Min.Y, bbox.Max.Y,
               bbox.Min.Z, bbox.Max.Z))
    return mesh, True


def _build_delaunay_mesh(points, stats):
    """
    Create a Rhino Mesh from an unstructured XYZ point cloud using
    RhinoCommon's Mesh.CreateFromTessellation (Rhino 7+) if available,
    or via a height-field approach as a reliable fallback.

    Parameters
    ----------
    points : list of (x, y, z)
    stats  : dict  from compute_statistics()

    Returns
    -------
    Rhino.Geometry.Mesh or None
    """
    rhino_pts = [rg.Point3d(p[0], p[1], p[2]) for p in points]

    # --- Attempt RhinoCommon tessellation (Rhino 7+ only) -------------
    try:
        cloud = rg.PointCloud(rhino_pts)
        mesh  = rg.Mesh.CreateFromTessellation(
            cloud.GetPoints(), rg.MeshingParameters.Default, True)
        if mesh is not None and mesh.IsValid and mesh.Faces.Count > 0:
            return mesh
    except Exception:
        pass  # API not available or failed

    # --- Height-field grid fallback -----------------------------------
    # Project points onto a regular grid via nearest-neighbour assignment,
    # then create a height-field mesh.
    _print("Tessellation API unavailable; building height-field mesh.")

    grid_res = max(20, min(200, int(math.sqrt(len(points)))))
    x_step   = stats["x_range"] / grid_res
    y_step   = stats["y_range"] / grid_res

    if x_step < 1e-10 or y_step < 1e-10:
        _print("Error: degenerate point cloud extent.")
        return None

    # Accumulate z values per grid cell
    grid_z   = {}
    grid_cnt = {}

    for (x, y, z) in points:
        xi = int((x - stats["x_min"]) / x_step)
        yi = int((y - stats["y_min"]) / y_step)
        xi = max(0, min(xi, grid_res - 1))
        yi = max(0, min(yi, grid_res - 1))
        key = (xi, yi)
        grid_z[key]   = grid_z.get(key, 0.0)   + z
        grid_cnt[key] = grid_cnt.get(key, 0)   + 1

    # Average z per cell; interpolate missing cells from neighbours
    z_grid = [[None] * grid_res for _ in range(grid_res)]
    for (xi, yi), total_z in grid_z.items():
        z_grid[yi][xi] = total_z / grid_cnt[(xi, yi)]

    _fill_grid_gaps(z_grid, grid_res, stats["z_mean"])

    # Build Rhino mesh from height field
    mesh = rg.Mesh()

    for yi in range(grid_res):
        for xi in range(grid_res):
            world_x = stats["x_min"] + xi * x_step
            world_y = stats["y_min"] + yi * y_step
            world_z = z_grid[yi][xi] if z_grid[yi][xi] is not None \
                      else stats["z_mean"]
            mesh.Vertices.Add(world_x, world_y, world_z)

    # Faces: two triangles per quad
    for yi in range(grid_res - 1):
        for xi in range(grid_res - 1):
            v00 = yi * grid_res + xi
            v10 = yi * grid_res + xi + 1
            v01 = (yi + 1) * grid_res + xi
            v11 = (yi + 1) * grid_res + xi + 1
            mesh.Faces.AddFace(v00, v10, v11, v01)

    mesh.Normals.ComputeNormals()
    mesh.Compact()

    return mesh if mesh.IsValid else None


def _fill_grid_gaps(z_grid, grid_res, default_z):
    """
    Fill None cells in a 2D grid using a simple nearest-assigned-neighbour
    propagation (not a full IDW, but adequate for gap-filling).

    Modifies z_grid in place.
    """
    max_passes = 4
    for _ in range(max_passes):
        changed = False
        for yi in range(grid_res):
            for xi in range(grid_res):
                if z_grid[yi][xi] is not None:
                    continue
                neighbours = []
                for dy, dx in ((-1, 0), (1, 0), (0, -1), (0, 1)):
                    ny, nx = yi + dy, xi + dx
                    if 0 <= ny < grid_res and 0 <= nx < grid_res:
                        if z_grid[ny][nx] is not None:
                            neighbours.append(z_grid[ny][nx])
                if neighbours:
                    z_grid[yi][xi] = sum(neighbours) / len(neighbours)
                    changed = True
        if not changed:
            break

    # Any remaining None → default
    for yi in range(grid_res):
        for xi in range(grid_res):
            if z_grid[yi][xi] is None:
                z_grid[yi][xi] = default_z


# ===========================================================================
# 5. CONTOUR EXTRACTION
# ===========================================================================

def extract_contours(geometry, is_mesh, stats,
                     interval=DEFAULT_CONTOUR_INTERVAL,
                     index_every=DEFAULT_INDEX_EVERY):
    """
    Extract contour curves from a surface or mesh at every `interval` units.

    Uses Rhino.Geometry.Brep.CreateContourCurves (for surfaces converted to
    Brep) or Rhino.Geometry.Mesh.CreateContourCurves (for meshes).

    Parameters
    ----------
    geometry    : NurbsSurface or Mesh
    is_mesh     : bool
    stats       : dict  from compute_statistics()
    interval    : float  vertical spacing between contour planes
    index_every : int    every N-th contour is an index contour

    Returns
    -------
    list of dict, each containing:
        'elevation' : float
        'curves'    : list of Rhino.Geometry.Curve
        'is_index'  : bool
    """
    z_min = stats["z_min"]
    z_max = stats["z_max"]

    # Snap the start elevation to the nearest multiple of `interval`
    start_z = math.ceil(z_min / interval) * interval
    elevations = []
    z = start_z
    while z <= z_max + 1e-6:
        elevations.append(z)
        z += interval

    _print("Extracting {:d} contour levels  "
           "(z={:.2f} to {:.2f}, interval={:.2f}).".format(
               len(elevations), start_z,
               elevations[-1] if elevations else z_min,
               interval))

    # Determine which elevation indices are index contours
    # Index contours occur every `index_every` steps counted from the
    # lowest contour.  The first contour is #1 (not index), so index
    # contours are at positions index_every, 2*index_every, etc.
    contour_results = []

    if is_mesh:
        brep_or_mesh = geometry
    else:
        # Convert NurbsSurface → Brep for contour extraction
        brep_or_mesh = geometry.ToBrep()
        if brep_or_mesh is None:
            raise RuntimeError("Failed to convert surface to Brep "
                               "for contour extraction.")

    # Base point for contour planes (XY centroid, varying Z)
    base_pt = rg.Point3d(
        (stats["x_min"] + stats["x_max"]) / 2.0,
        (stats["y_min"] + stats["y_max"]) / 2.0,
        0.0
    )
    normal = rg.Vector3d.ZAxis

    total = len(elevations)
    curves_generated = 0
    curves_filtered = 0

    for i, elev in enumerate(elevations):
        if (i + 1) % max(1, total // 10) == 0 or i == total - 1:
            _progress("Contouring", i + 1, total)

        plane_pt = rg.Point3d(base_pt.X, base_pt.Y, elev)

        try:
            if is_mesh:
                curves = rg.Mesh.CreateContourCurves(
                    brep_or_mesh,
                    plane_pt,
                    normal)
            else:
                curves = rg.Brep.CreateContourCurves(
                    brep_or_mesh,
                    plane_pt,
                    normal,
                    sc.doc.ModelAbsoluteTolerance)

            if curves is None:
                curves = []

            curves_generated += len(curves)

            # Filter out degenerate or duplicate tiny curves
            valid_curves = [
                c for c in curves
                if c is not None and c.IsValid
                and c.GetLength() > sc.doc.ModelAbsoluteTolerance * 10
            ]

            curves_filtered += len(curves) - len(valid_curves)

        except Exception as ex:
            _print("Warning: contour at z={:.2f} failed: {}".format(elev, ex))
            valid_curves = []

        # Determine index status
        # Count from start_z up; every `index_every`-th level is index
        step_number = int(round((elev - start_z) / interval))
        is_index = (step_number % index_every == 0) and (step_number != 0 or
                   abs(elev / interval - round(elev / interval)) < 1e-6)

        # Simpler: every `index_every` multiples of interval
        is_index = (abs(elev % (interval * index_every)) <
                    interval * 0.01)

        contour_results.append({
            "elevation": elev,
            "curves":    valid_curves,
            "is_index":  is_index,
        })

    total_curves = sum(len(c["curves"]) for c in contour_results)
    _print("Extracted {:,} contour curve segments across {:d} levels.".format(
        total_curves, len(contour_results)))

    # Diagnostic info
    _print("  Total curves generated: {:,}".format(curves_generated))
    _print("  Curves filtered as degenerate: {:,}".format(curves_filtered))
    _print("  Geometry type: {}".format("Mesh" if is_mesh else "Brep (NurbsSurface)"))
    _print("  Surface Z extent: {:.3f} to {:.3f}".format(
        stats["z_min"], stats["z_max"]))
    _print("  Contour Z range tested: {:.3f} to {:.3f}".format(
        start_z, elevations[-1] if elevations else start_z))

    if curves_generated == 0:
        _print("\nDEBUG: No curves generated. Possible causes:")
        _print("  1. Surface Z extent too small (very flat terrain)")
        _print("  2. Contour interval larger than Z range")
        _print("  3. Surface geometry invalid or incorrectly projected")
        _print("  4. Tolerance settings preventing curve creation")

    return contour_results


# ===========================================================================
# 6. RHINO DOCUMENT POPULATION
# ===========================================================================

def add_points_to_document(points, layer_idx):
    """
    Add raw XYZ points as Rhino point objects on the specified layer.

    Parameters
    ----------
    points    : list of (x, y, z)
    layer_idx : int  Rhino layer table index

    Returns
    -------
    list of Guid  added object GUIDs
    """
    guids = []
    doc = sc.doc
    attrs = Rhino.DocObjects.ObjectAttributes()
    attrs.LayerIndex = layer_idx

    # Only add a thinned representative cloud to avoid document bloat
    display_pts = thin_points(points, target_count=5000)

    for (x, y, z) in display_pts:
        pt   = rg.Point3d(x, y, z)
        guid = doc.Objects.AddPoint(pt, attrs)
        if guid != System.Guid.Empty:
            guids.append(guid)

    _print("Added {:,} display points to document.".format(len(guids)))
    return guids


def add_surface_to_document(geometry, is_mesh, layer_idx):
    """
    Add the terrain surface or mesh to the Rhino document.

    Parameters
    ----------
    geometry  : NurbsSurface or Mesh
    is_mesh   : bool
    layer_idx : int

    Returns
    -------
    Guid
    """
    doc   = sc.doc
    attrs = Rhino.DocObjects.ObjectAttributes()
    attrs.LayerIndex = layer_idx

    if is_mesh:
        guid = doc.Objects.AddMesh(geometry, attrs)
    else:
        brep = geometry.ToBrep()
        guid = doc.Objects.AddBrep(brep, attrs) if brep else \
               doc.Objects.AddSurface(geometry, attrs)

    _print("Added terrain surface to document.")
    return guid


def add_contours_to_document(contour_results, layer_manager, stats,
                              colour_by_elevation=True):
    """
    Add all contour curves to the Rhino document with correct layer
    and object-level plot weight attributes.

    Parameters
    ----------
    contour_results     : list of dict  from extract_contours()
    layer_manager       : LayerManager
    stats               : dict
    colour_by_elevation : bool  apply per-object colour ramp to index contours

    Returns
    -------
    dict with keys 'regular' and 'index', each a list of added Guids
    """
    doc    = sc.doc
    added  = {"regular": [], "index": []}
    z_min  = stats["z_min"]
    z_max  = stats["z_max"]
    z_span = z_max - z_min if (z_max - z_min) > 0 else 1.0

    total  = sum(len(r["curves"]) for r in contour_results)
    done   = 0

    for entry in contour_results:
        elev     = entry["elevation"]
        is_index = entry["is_index"]
        curves   = entry["curves"]

        if not curves:
            continue

        if is_index:
            layer_idx  = layer_manager.get_index_layer(elev)
            plot_wt    = LW_INDEX
        else:
            layer_idx  = layer_manager.get_regular_layer(elev)
            plot_wt    = LW_REGULAR

        # Build object attributes
        attrs              = Rhino.DocObjects.ObjectAttributes()
        attrs.LayerIndex   = layer_idx
        attrs.PlotWeight   = plot_wt

        if colour_by_elevation and is_index:
            t          = (elev - z_min) / z_span
            obj_colour = _colour_from_ramp(t)
            attrs.ObjectColor      = obj_colour
            attrs.ColorSource      = \
                Rhino.DocObjects.ObjectColorSource.ColorFromObject
            attrs.PlotColorSource  = \
                Rhino.DocObjects.ObjectPlotColorSource.PlotColorFromObject

        for curve in curves:
            guid = doc.Objects.AddCurve(curve, attrs)
            if guid != System.Guid.Empty:
                if is_index:
                    added["index"].append(guid)
                else:
                    added["regular"].append(guid)
            done += 1

        if done % max(1, total // 20) == 0:
            _progress("Adding to document", done, total)

    _print("Added {:,} regular + {:,} index contour curves.".format(
        len(added["regular"]), len(added["index"])))

    return added


# ===========================================================================
# 7. DXF EXPORT
# ===========================================================================

def export_dxf(output_path):
    """
    Export the entire Rhino model to a DXF file using Rhino's built-in
    export command.

    Parameters
    ----------
    output_path : str  full path including '.dxf' extension

    Returns
    -------
    bool  True on apparent success
    """
    # Rhino's _-Export command preserves layers and plot weights
    safe_path = output_path.replace("\\", "/")
    cmd = '_-Export "{}" _Enter'.format(safe_path)
    result = rs.Command(cmd, False)
    if result and os.path.isfile(output_path):
        _print("DXF exported to: {}".format(output_path))
        return True
    else:
        _print("DXF export may have failed.  Check: {}".format(output_path))
        return False


# ===========================================================================
# 8. USER INTERFACE  –  main interaction flow
# ===========================================================================

def get_user_parameters():
    """
    Collect all user-configurable parameters through Rhino dialogs.

    Returns
    -------
    dict or None  (None means the user cancelled)
    Keys:
        filepath           : str
        contour_interval   : float
        index_every        : int
        band_size          : float
        add_points         : bool
        add_surface        : bool
        colour_by_elev     : bool
        filter_outliers    : bool
        export_dxf         : bool
    """
    # ---- File selection -----------------------------------------------
    # Filter shows CSV/text formats first, then E57, then a combined group.
    # The combined group at the top makes it easy to browse for either type.
    filepath = rs.OpenFileName(
        "Select Point Cloud File  (CSV, TXT, XYZ  or  E57)",
        "All Point Cloud Files (*.csv;*.txt;*.xyz;*.asc;*.pts;*.e57)"
        "|*.csv;*.txt;*.xyz;*.asc;*.pts;*.e57"
        "|E57 3D Imaging Files (*.e57)|*.e57"
        "|CSV / Text Files (*.csv;*.txt;*.xyz;*.asc;*.pts)"
        "|*.csv;*.txt;*.xyz;*.asc;*.pts"
        "|All Files (*.*)|*.*||"
    )
    if not filepath:
        _print("Operation cancelled by user.")
        return None

    # ---- Contour parameters ------------------------------------------
    contour_interval = rs.GetReal(
        "Contour interval (model units)",
        DEFAULT_CONTOUR_INTERVAL, 0.01, 1e6)
    if contour_interval is None:
        return None

    index_every = rs.GetInteger(
        "Mark every N-th contour as INDEX (thicker/coloured)",
        DEFAULT_INDEX_EVERY, 2, 100)
    if index_every is None:
        return None

    band_size = rs.GetReal(
        "Elevation band size for layer grouping (model units)",
        DEFAULT_BAND_SIZE, contour_interval, 1e6)
    if band_size is None:
        return None

    # ---- Options via checkbox list -----------------------------------
    option_labels = [
        "Add raw point cloud to document",
        "Add terrain surface to document",
        "Colour index contours by elevation",
        "Filter elevation outliers ({}σ)".format(OUTLIER_SIGMA),
        "Export DXF after generation",
    ]
    defaults = [False, True, True, True, False]

    # Create (label, default_state) pairs for CheckListBox
    item_pairs = [(option_labels[i], defaults[i]) for i in range(len(option_labels))]

    choices = rs.CheckListBox(
        item_pairs,
        "Topographic Map Options",
        "Topo Map Generator"
    )

    if choices is None:
        return None

    # CheckListBox returns a tuple of (label, checked) pairs
    chosen = {label: state for label, state in choices}

    return {
        "filepath":         filepath,
        "contour_interval": contour_interval,
        "index_every":      index_every,
        "band_size":        band_size,
        "add_points":       chosen.get(option_labels[0], defaults[0]),
        "add_surface":      chosen.get(option_labels[1], defaults[1]),
        "colour_by_elev":   chosen.get(option_labels[2], defaults[2]),
        "filter_outliers":  chosen.get(option_labels[3], defaults[3]),
        "export_dxf":       chosen.get(option_labels[4], defaults[4]),
    }


def print_statistics(stats):
    """Print a formatted statistics block to the Rhino command line."""
    _print("=" * 60)
    _print("Point Cloud Statistics")
    _print("  Count  : {:,}".format(stats["count"]))
    _print("  X      : {:.3f}  –  {:.3f}  (range {:.3f})".format(
        stats["x_min"], stats["x_max"], stats["x_range"]))
    _print("  Y      : {:.3f}  –  {:.3f}  (range {:.3f})".format(
        stats["y_min"], stats["y_max"], stats["y_range"]))
    _print("  Z      : {:.3f}  –  {:.3f}  (range {:.3f})".format(
        stats["z_min"], stats["z_max"], stats["z_range"]))
    _print("  Z mean : {:.3f}   Z std: {:.3f}".format(
        stats["z_mean"], stats["z_std"]))
    _print("=" * 60)


# ===========================================================================
# 9. MAIN ENTRY POINT
# ===========================================================================

def main():
    """
    Main execution function.

    Orchestrates:
        1. User parameter collection
        2. Point cloud loading and validation
        3. Surface generation
        4. Contour extraction
        5. Layer creation and document population
        6. Optional DXF export
        7. Viewport refresh
    """
    t_start = time.time()
    _print("Architectural Topographic Map Generator  –  Starting")
    _print("-" * 60)

    # -- 1. User input -------------------------------------------------
    params = get_user_parameters()
    if params is None:
        return

    # -- 2. Load & validate point cloud --------------------------------
    # Detect format early so the status message precedes any long I/O.
    input_fmt = _detect_file_format(params["filepath"])
    if input_fmt == "e57":
        _print("Input format: E57  --  "
               "pye57 available: {}".format(_PYE57_AVAILABLE))
        if not _PYE57_AVAILABLE:
            _print(
                "Note: pye57 not installed.  "
                "Will attempt Rhino built-in E57 import as fallback.")

    try:
        points = load_point_cloud(params["filepath"])
    except (IOError, ValueError) as ex:
        rs.MessageBox(
            "Failed to load point cloud:\n\n{}".format(ex),
            48,   # MB_ICONEXCLAMATION
            "Topo Map Generator – Error"
        )
        return
    except RuntimeError as ex:
        # RuntimeError is raised when E57 fallback chain is exhausted and
        # contains actionable guidance for the user.
        rs.MessageBox(
            "E57 Loading Failed\n\n{}".format(ex),
            48,   # MB_ICONEXCLAMATION
            "Topo Map Generator – E57 Error"
        )
        return

    stats_raw = compute_statistics(points)
    print_statistics(stats_raw)

    # Outlier filtering
    if params["filter_outliers"]:
        points = filter_outliers(points)
        stats = compute_statistics(points)
    else:
        stats = stats_raw

    if len(points) < 4:
        rs.MessageBox(
            "After filtering, only {} points remain.\n"
            "Cannot generate surface.".format(len(points)),
            48, "Topo Map Generator – Error")
        return

    # -- 3. Surface generation -----------------------------------------
    surface_pts = thin_points(points, MAX_SURFACE_POINTS)
    surface_stats = compute_statistics(surface_pts)

    # Check if coordinates are very large (e.g., UTM) and normalize for precision
    max_abs_coord = max(
        abs(surface_stats["x_min"]), abs(surface_stats["x_max"]),
        abs(surface_stats["y_min"]), abs(surface_stats["y_max"])
    )

    normalized_pts = surface_pts
    origin_shift = None

    if max_abs_coord > 10000:
        _print("Large absolute coordinates detected ({:.0f}).".format(max_abs_coord))
        _print("Normalizing for numerical precision during surface fitting...")
        normalized_pts, origin_shift = normalize_coordinates(surface_pts, surface_stats)
        surface_stats = compute_statistics(normalized_pts)

    try:
        geometry, is_mesh = build_surface_from_points(normalized_pts, surface_stats)
    except Exception as ex:
        rs.MessageBox(
            "Surface generation failed:\n\n{}".format(ex),
            48, "Topo Map Generator – Error")
        return

    # Denormalize surface immediately after creation
    if origin_shift is not None:
        _print("Denormalizing surface back to original coordinates...")
        dx, dy, dz = origin_shift
        transform = rg.Transform.Translation(dx, dy, dz)
        try:
            if is_mesh:
                geometry.Transform(transform)
            else:
                # NurbsSurface.Transform returns a new surface
                geometry = geometry.Transform(transform)
        except Exception as e:
            _print("Warning: surface denormalization failed: {}".format(e))

    # -- 4. Contour extraction -----------------------------------------
    # Now use original stats since geometry is back in original coordinates
    try:
        contour_results = extract_contours(
            geometry, is_mesh, stats,
            interval    = params["contour_interval"],
            index_every = params["index_every"]
        )
    except Exception as ex:
        rs.MessageBox(
            "Contour extraction failed:\n\n{}".format(ex),
            48, "Topo Map Generator – Error")
        return

    non_empty = [r for r in contour_results if r["curves"]]
    if not non_empty:
        rs.MessageBox(
            "No contour curves were generated.\n"
            "Check point cloud coverage and contour interval.",
            48, "Topo Map Generator – Error")
        return

    # -- 5. Layer structure & document population ----------------------
    sc.doc.Views.RedrawEnabled = False   # suppress redraws during bulk add
    try:
        layer_mgr = LayerManager(
            stats["z_min"], stats["z_max"], params["band_size"])
        layer_mgr.create_base_layers()

        if params["add_points"]:
            pt_layer = layer_mgr._cache.get("Topo_PointCloud", 0)
            add_points_to_document(points, pt_layer)

        if params["add_surface"]:
            surf_layer = layer_mgr._cache.get("Topo_Surface", 0)
            add_surface_to_document(geometry, is_mesh, surf_layer)

        added_guids = add_contours_to_document(
            contour_results,
            layer_mgr,
            stats,
            colour_by_elevation=params["colour_by_elev"]
        )
    finally:
        sc.doc.Views.RedrawEnabled = True

    # -- 6. Optional DXF export ----------------------------------------
    if params["export_dxf"]:
        base_dir  = os.path.dirname(params["filepath"])
        base_name = os.path.splitext(
                        os.path.basename(params["filepath"]))[0]
        dxf_path  = os.path.join(base_dir, base_name + "_topo.dxf")
        export_dxf(dxf_path)

    # -- 7. Refresh & summary ------------------------------------------
    sc.doc.Views.Redraw()
    rs.ZoomExtents()

    elapsed = time.time() - t_start
    summary = (
        "Topographic Map Generated\n\n"
        "  Regular contour curves : {:,}\n"
        "  Index contour curves   : {:,}\n"
        "  Contour interval       : {:.2f} units\n"
        "  Index every            : {:d} contours\n"
        "  Elevation range        : {:.2f}  –  {:.2f}\n"
        "  Processing time        : {:.1f} s\n"
    ).format(
        len(added_guids["regular"]),
        len(added_guids["index"]),
        params["contour_interval"],
        params["index_every"],
        stats["z_min"], stats["z_max"],
        elapsed
    )

    _print(summary)
    rs.MessageBox(summary, 64, "Topo Map Generator – Complete")   # MB_ICONINFORMATION


# ===========================================================================
# SCRIPT ENTRY
# ===========================================================================

if __name__ == "__main__":
    main()
