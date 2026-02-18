# -*- coding: utf-8 -*-
"""
quick_diagnostic.py - FAST scene checker (no freezing)

Much simpler - just lists objects without trying to compute bounding boxes.
"""

import scriptcontext as sc
import rhinoscriptsyntax as rs

print("\n" + "=" * 70)
print("QUICK DIAGNOSTIC - SIMPLE OBJECT LIST")
print("=" * 70)

try:
    doc = sc.doc
    print("\nDocument objects: {}".format(len(doc.Objects)))

    count = 0
    for obj in doc.Objects:
        try:
            if count > 100:
                print("\n⚠ Too many objects ({}) - stopping list".format(len(doc.Objects)))
                break

            name = obj.Name if obj.Name else "<unnamed>"
            geom_type = obj.Geometry.GetType().Name

            print("  {} - {}".format(name, geom_type))
            count += 1
        except Exception as e:
            print("  ERROR reading object: {}".format(str(e)[:50]))

    print("\n" + "=" * 70)
    print("Done!")
    print("=" * 70 + "\n")

except Exception as e:
    print("\n❌ ERROR: {}".format(e))
    import traceback
    traceback.print_exc()
