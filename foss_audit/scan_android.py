"""Android SDKs under ~/sdk: Google's, and the FOSS rebuild that replaces it.

Google's SDK is one item for the whole tree: its license is accepted once,
via the hash files in licenses/. The FOSS rebuild is what
scripts/foss_android_sdk.sh and scripts/foss_android_ndk.sh assemble from
AOSP, OpenJDK and LLVM sources; curated.json lists it as the alternative.
"""

from __future__ import annotations

import shlex
from pathlib import Path
from typing import Final

from foss_audit.model import Item
from foss_audit.scan_misc import unknown

SOURCE: Final = "user-app"
HOME = Path.home()
# android-all + build-tools (Apache-2.0), OpenJDK's java.* (GPL-2.0 WITH
# Classpath-exception-2.0), libc++/compiler-rt/libunwind (LLVM-exception),
# bionic's headers and crt objects (mostly BSD-3-Clause).
FOSS_SDK_LICENSE: Final = (
    "Apache-2.0 AND Apache-2.0 WITH LLVM-exception AND GPL-2.0 WITH Classpath-exception-2.0 AND BSD-3-Clause"
)


def shown(path: Path) -> str:
    """`path` the way a person would type it: ~/..."""
    return f"~/{path.relative_to(HOME)}"


def scan_android_sdk() -> list[Item]:
    """~/sdk/Android/Sdk: Google's SDK License is accepted via licenses/* hash files."""
    sdk = HOME / "sdk/Android/Sdk"
    if not sdk.is_dir():
        return []
    accepted = sorted(p.name for p in (sdk / "licenses").glob("*") if p.is_file())
    if "android-sdk-license" not in accepted:
        return [unknown("android-sdk", SOURCE, reason=f"{shown(sdk)}; no SDK license accepted")]
    reason = f"{shown(sdk)}; Android SDK License accepted ({', '.join(accepted)})"
    return [
        Item(
            name="android-sdk",
            source=SOURCE,
            verdict="nonfree",
            license="LicenseRef-Android-SDK-License",
            reason=reason,
        )
    ]


def scan_foss_android_sdk() -> list[Item]:
    """~/sdk/foss-android-sdk, assembled by scripts/foss_android_{sdk,ndk}.sh."""
    sdk = HOME / "sdk/foss-android-sdk"
    if not sdk.is_dir():
        return []
    reason = f"{shown(sdk)}; built from AOSP, OpenJDK and LLVM sources by foss-audit's scripts"
    return [
        Item(
            name="foss-android-sdk",
            source=SOURCE,
            verdict="foss",
            license=FOSS_SDK_LICENSE,
            reason=reason,
            removeCommand=f"rm -rf {shlex.quote(str(sdk))}",
        )
    ]
