"""License-string classification: the core of every verdict."""

from __future__ import annotations

import pytest

from foss_audit.licenses import classify_spdx, classify_text, tokens


@pytest.mark.parametrize(
    ("name", "expr", "verdict"),
    [
        ("zlib", "Zlib", "foss"),
        ("glibc", "GPL-2.0-or-later AND LGPL-2.1-or-later", "foss"),
        ("qt6-base", "GPL-3.0-only OR LicenseRef-Qt-Commercial", "foss"),
        ("autoconf", "GPL2 GPL3 custom", "foss"),
        ("wqy-zenhei", 'GPL2 custom:"font embedding exception"', "foss"),
        ("ffmpeg-audio-thumbnailer", "GPL3 or any later version", "foss"),
        ("clinfo", "custom:Public Domain", "foss"),
        ("google-chrome", "custom:chrome", "nonfree"),
        ("steam", "LicenseRef-steam-subscriber-agreement", "nonfree"),
        ("nvidia-utils", "LicenseRef-NVIDIA-Driver-License-Agreement", "nonfree"),
        ("linux-firmware-amd", "LicenseRef-WHENCE LicenseRef-amd", "nonfree"),
        ("intel-oneapi-mkl", "LicenseRef-Intel-Simplified", "nonfree"),
        ("pop-icon-theme", "CCPL", "foss"),
        ("dual", "GPL-3.0-only OR LicenseRef-commercial", "foss"),
        ("blender-bin", "MIT LicenseRef-Arev-Fonts LicenseRef-ICS LicenseRef-TOST-1.0", "foss"),
        ("sudo", "custom", "nonfree"),
        ("libklvanc", "", "nonfree"),
        ("odd", "LicenseRef-Mystery", "nonfree"),
        ("php", "PHP-3.01", "foss"),
        ("php-legacy", "PHP-3.0", "foss"),
    ],
)
def test_classify_spdx(name: str, expr: str, verdict: str) -> None:
    assert classify_spdx(name, expr)[0] == verdict


def test_dual_license_with_unknown_part_is_not_free() -> None:
    # A free OR-branch only rescues the package when nothing else is unexplained.
    verdict, reason = classify_spdx("x", "GPL-2.0 OR LicenseRef-EULA OR LicenseRef-Mystery")
    assert verdict == "nonfree"
    assert "EULA" in reason


def test_unknown_reason_names_the_token() -> None:
    assert classify_spdx("x", "MIT LicenseRef-Mystery")[1] == "unrecognised license: LicenseRef-Mystery"


def test_tokens_drop_operators_and_filler() -> None:
    assert tokens("(MIT OR Apache-2.0) WITH LLVM-exception") == ["MIT", "Apache-2.0", "LLVM-exception"]


@pytest.mark.parametrize(
    ("text", "verdict"),
    [
        ("MIT License", "foss"),
        ("BSD 3-Clause", "foss"),
        ("GNU General Public License v3 or later (GPLv3+)", "foss"),
        ("Python-2.0", "foss"),
        ("Proprietary", "nonfree"),
        ("Copyright 2013 Someone. All rights reserved.", "nonfree"),
        ("Dual: MIT or commercial", "foss"),
        ("", "nonfree"),
        ("UNKNOWN", "nonfree"),
        ("None", "nonfree"),
        ("Some bespoke text", "nonfree"),
        ("SIL Open Font License, Version 1.1", "foss"),
        ("icons licensed under CC BY 4.0", "foss"),
        ("art licensed under CC BY-NC 4.0, all rights reserved", "nonfree"),
    ],
)
def test_classify_text(text: str, verdict: str) -> None:
    assert classify_text(text)[0] == verdict


def test_blob_and_missing_reasons() -> None:
    assert classify_spdx("linux-firmware-amd", "LicenseRef-amd")[1] == "firmware blob: LicenseRef-amd"
    assert classify_text("")[1] == "no license (all rights reserved)"


@pytest.mark.parametrize(
    "text",
    [
        "Android Software Development Kit License",
        "ML Kit Terms of Service",
        "The JSON License",
        "Syncfusion<sup>&reg;</sup> License",
        "NEBULINO PUBLIC LICENSE",
        "UNLICENSED",
        "LicenseRef-NVIDIA-SOFTWARE-LICENSE",
    ],
)
def test_maven_nonfree_license_names(text: str) -> None:
    verdict, reason = classify_text(text)
    assert verdict == "nonfree"
    assert not reason.startswith("unrecognised")


@pytest.mark.parametrize(
    "text",
    [
        "Unicode-3.0",
        "CDLA-Permissive-2.0",
        "bzip2-1.0.6",
        "Apache2",
        "MPL2",
        "GPLv2",
        "wxWindows Library Licence, Version 3.1",
        "ODC-By-1.0",
        "Bouncy Castle Licence",
        "ASLv2",
        "Zope Public License",
        "ZPL 2.1",
        "PSFL",
        "Expat License",
        "Inno Setup License",
        "Historical Permission Notice and Disclaimer (HPND)",
    ],
)
def test_crate_free_license_ids(text: str) -> None:
    assert classify_text(text) == ("foss", "")
