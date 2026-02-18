# -*- coding: utf-8 -*-
"""
minimal_diagnostic.py - ULTRA MINIMAL (fastest)

Just counts and lists objects by name. No geometry analysis.
"""

import scriptcontext as sc

print("\n" + "=" * 70)
print("MINIMAL DIAGNOSTIC")
print("=" * 70)

try:
    doc = sc.doc
    obj_count = len(doc.Objects)
    print("\nTotal objects in document: {}".format(obj_count))

    if obj_count == 0:
        print("(No objects found)")
    elif obj_count > 500:
        print("\n⚠ WARNING: {} objects is very high!".format(obj_count))
        print("This may be causing the freeze.")
        print("\nFirst 20 objects:")
        for i, obj in enumerate(doc.Objects):
            if i >= 20:
                break
            print("  {}. {}".format(i+1, obj.Name if obj.Name else "<unnamed>"))
    else:
        print("\nObjects:")
        for i, obj in enumerate(doc.Objects):
            print("  {}. {}".format(i+1, obj.Name if obj.Name else "<unnamed>"))

    print("\n" + "=" * 70)

except Exception as e:
    print("\n❌ ERROR: {}".format(e))
