#!/usr/bin/env python3
"""Downgrade android.jar's nullability annotations to Google's "Recently" ones.

Google's android.jar is a metalava stub that leaves out many of the
framework's @Nullable/@NonNull (Context.getSystemService(Class) has none);
Robolectric's android-all is the real framework and keeps them all, and
kotlinc treats android.annotation.Nullable as a hard error. Third-party
plugins written against Google's jar (workmanager_android) then fail to
compile. androidx.annotation.RecentlyNullable/RecentlyNonNull are the names
metalava itself uses for "nullability kotlinc reports as a warning", so the
jar keeps its information and every build that passes on Google's jar passes.

Usage: foss_android_jar_nullability.py <android.jar>   (rewritten in place)
"""

from __future__ import annotations

import os
import struct
import sys
import zipfile

RENAMES = {
    b"Landroid/annotation/Nullable;": b"Landroidx/annotation/RecentlyNullable;",
    b"Landroid/annotation/NonNull;": b"Landroidx/annotation/RecentlyNonNull;",
}
# Constant-pool entry sizes after the tag byte (JVMS 4.4); Utf8 (1) is
# length-prefixed and Long/Double (5, 6) take two pool slots.
FIXED = {
    3: 4,
    4: 4,
    5: 8,
    6: 8,
    7: 2,
    8: 2,
    9: 4,
    10: 4,
    11: 4,
    12: 4,
    15: 3,
    16: 2,
    17: 4,
    18: 4,
    19: 2,
    20: 2,
}


def rewrite_class(data: bytes) -> bytes:
    """The class file with every renamed Utf8 constant replaced."""
    if not any(old in data for old in RENAMES):
        return data
    (count,) = struct.unpack_from(">H", data, 8)
    out, pos, index = [data[:10]], 10, 1
    while index < count:
        tag = data[pos]
        if tag == 1:
            (length,) = struct.unpack_from(">H", data, pos + 1)
            text = data[pos + 3 : pos + 3 + length]
            text = RENAMES.get(text, text)
            out.append(b"\x01" + struct.pack(">H", len(text)) + text)
            pos += 3 + length
        else:
            size = FIXED[tag]
            out.append(data[pos : pos + 1 + size])
            pos += 1 + size
        index += 2 if tag in (5, 6) else 1
    out.append(data[pos:])
    return b"".join(out)


def main(jar: str) -> int:
    """Rewrite every class of `jar`; prints how many changed."""
    tmp, changed = f"{jar}.tmp", 0
    with zipfile.ZipFile(jar) as src, zipfile.ZipFile(tmp, "w", zipfile.ZIP_DEFLATED) as dst:
        for info in src.infolist():
            data = src.read(info)
            if info.filename.endswith(".class"):
                new = rewrite_class(data)
                changed += new is not data
                data = new
            dst.writestr(info, data)
    os.replace(tmp, jar)
    sys.stdout.write(f"{jar}: nullability downgraded in {changed} classes\n")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1]))
