"""Turn a raw license string into a verdict.

Conservative on purpose: anything not clearly free is "nonfree" with the
reason saying why (no license, unrecognised text), and data/curated.json
settles the false alarms by hand.
"""

from __future__ import annotations

import re

from foss_audit.model import NO_LICENSE, Verdict

# Tokens that make a package non-free unless they are just one OR-alternative.
NONFREE_PAT = re.compile(
    r"EULA|NVIDIA|nvidia|cuDNN|CUDA|Steam|steam|Microsoft|UnRAR|Reshade|claude-code"
    r"|GeoLite2|CC-BY-NC|Aseprite|[Pp]roprietary|commercial|chrome|Intel-EULA"
    r"|amd-ucode|amdgpu|radeon|realtek|broadcom|atheros|mediatek|cirrus|qlogic"
    r"|netronome|liquidio|WHENCE|LicenseRef-ti$|LicenseRef-intel$|LicenseRef-amd$"
    r"|Nmap-Public-Source|Java|Unsplash|Intel-Simplified",
)
# Firmware / microcode / driver blobs: non-free, flagged as such in the reason.
BLOB_NAME = re.compile(r"^(linux-firmware|amd-ucode|intel-ucode|sof-firmware|nvidia-utils)")

FREE_PAT = re.compile(
    r"^(MIT|BSD|GPL|LGPL|AGPL|Apache|APACHE|apache|MPL|ISC|Zlib|zlib|ZLIB|CC0|Unlicense|WTFPL"
    r"|PSF|Python|python|Artistic|PerlArtistic|FSFAP|FSFULLR|X11|HPND|ICU|OFL|BSL-1\.0"
    r"|0BSD|NCSA|NTP|CC-BY-(SA-)?[0-9]|CC-BY-SA|CC-PDM|CC-PDDC|EPL|CPL|CECILL|curl|libpng"
    r"|libtiff|IJG|FTL|bzip2|PostgreSQL|Ruby|OpenSSL|TCL|Sleepycat|ZPL|AFL|Unicode"
    r"|GFDL|FDL|SGI-B|SMLNJ|Linux-|LLVM-exception|GCC-exception|Qt-GPL|Bison|PCRE2"
    r"|Autoconf|Libtool|Font|Bitstream|Beerware|MIT-|libselinux|ImageMagick|QPL|CDDL"
    r"|SISSL|TCP-wrappers|SunPro|NAIST|MPICH|BSD2|GPL2|GPL3|LGPL2|LGPL3|custom:(BSD|ZLIB|zlib"
    r"|wxWindows|vim|Public|PublicDomain|Public_Domain|OpenLDAP|LGPL|ISC|Expat|SIL|OFL|WTFPL"
    r"|flex|CC$)|LicenseRef-(Public-Domain|PublicDomain|public-domain|scancode-public-domain"
    r"|Qt-Commercial|xorg|xkb|libx|libpci|tz|Sqlite|OpenLDAP|OpenIB|BSD|Intel-BSD"
    r"|Unicode|icu|glew|lib32-glew|GC|docbook|Ispell|SCOWL|soxr|qhull|pooch|libmng|libavif"
    r"|libcdr|JasPer|Info-ZIP|leancrypto|Less|LGPL-exception|GPL-|zlib|OFL|AOMPL|Google-Patent"
    r"|PathScale|cfitsio|XSD2|RNG2|Batch|OCB1|MPICH|Adobe-Display-PostScript|DEC-3-Clause"
    r"|HPND|xkeyboard-config|Arev-Fonts|ICS|LLVM-exception|TOST-1\.0))",
)
OPERATORS = frozenset({"OR", "AND", "WITH"})
# Free-form words packagers put in the field ("GPL3 or any later version",
# "custom:SIL Open Font License v1.1"); they carry no verdict on their own.
FILLER = re.compile(
    r"(?i)^(or|any|later|version|with|linking|exception|Domain|Public|License|Open|Font|v?\d[\d.]*"
    r"|embedding|SIL|CC|by-sa|CCPL.*|custom:CC0|PS-or-PDF-font-exception.*|Python-2\.0)$",
)
# Arch's bare "custom" means "see the extra license file". Next to a free
# license it is that license's notice; on its own it needs a curated verdict.
CUSTOM = re.compile(r"^custom:?$")

# Free-text licenses from PyPI/npm/conda metadata ("MIT License", "BSD 3-Clause").
FREE_TEXT = re.compile(
    r"\b(MIT|BSD|Apache|GPL|LGPL|AGPL|MPL|Mozilla|ISC|PSF|Python Software|Unlicense"
    r"|Zlib|Artistic|EPL|Eclipse|CC0|Public Domain|0BSD|BlueOak|WTFPL|GNU|General Public"
    r"|Python-2\.0|TCL|OFL|Open Font License|CC[ -]BY(?![ -]NC))\b"
    r"|License agreement for matplotlib|SciPy Develope",
    re.IGNORECASE,
)
NONFREE_TEXT = re.compile(r"proprietary|all rights reserved|commercial|EULA", re.IGNORECASE)


def tokens(expr: str) -> list[str]:
    """Split a pacman license field into bare identifiers."""
    raw = re.split(r"[\s()\"]+", expr)
    return [t for t in raw if t and t not in OPERATORS and not FILLER.match(t)]


def classify_spdx(name: str, expr: str) -> tuple[Verdict, str]:
    """Classify a pacman (SPDX-ish) license field; returns (verdict, reason)."""
    toks = tokens(expr)
    if not toks:
        if expr.strip():
            return "foss", "free-form CC/public-domain wording"
        return "nonfree", NO_LICENSE
    nonfree = [t for t in toks if NONFREE_PAT.search(t)]
    free = [t for t in toks if FREE_PAT.match(t) and t not in nonfree]
    other = [t for t in toks if t not in nonfree and t not in free]
    if free and other and all(CUSTOM.match(t) for t in other):
        other = []
    if nonfree:
        # "GPL OR Commercial"-style dual licensing still leaves a free option.
        if " OR " in expr and free and not other:
            return "foss", "dual-licensed, free option taken"
        blob = "firmware blob: " if BLOB_NAME.match(name) else ""
        return "nonfree", blob + " ".join(nonfree)
    if other:
        return "nonfree", "unrecognised license: " + " ".join(other)
    return "foss", ""


def classify_text(text: str) -> tuple[Verdict, str]:
    """Classify a free-text license (PyPI/npm/conda); returns (verdict, reason)."""
    if not text or text.strip() in {"?", "UNKNOWN", "None"}:
        return "nonfree", NO_LICENSE
    if NONFREE_TEXT.search(text) and not FREE_TEXT.search(text):
        return "nonfree", text[:80]
    if FREE_TEXT.search(text):
        return "foss", ""
    # Copyright-only lines (mitmproxy's BSD header) grant nothing by themselves.
    return "nonfree", "unrecognised license: " + text[:80]
