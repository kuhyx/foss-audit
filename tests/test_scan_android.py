"""Tests for the Android SDK scanners: Google's SDK and the FOSS rebuild."""

from __future__ import annotations

from pathlib import Path

import pytest
from userapp_helpers import write

from foss_audit import scan_android, scan_userapp
from foss_audit.curated import Curated, apply


@pytest.fixture
def home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setattr(scan_android, "HOME", tmp_path)
    monkeypatch.setattr(scan_userapp, "HOME", tmp_path)
    return tmp_path


def test_android_sdk(home: Path) -> None:
    sdk = home / "sdk/Android/Sdk"
    assert scan_android.scan_android_sdk() == []
    sdk.mkdir(parents=True)
    (item,) = scan_android.scan_android_sdk()
    assert (item.verdict, item.license, item.reason) == (
        "nonfree",
        "",
        "~/sdk/Android/Sdk; no SDK license accepted",
    )
    write(sdk / "licenses/android-sdk-license", "abc\n", 0o644)
    write(sdk / "licenses/google-gdk-license", "def\n", 0o644)
    (item,) = scan_android.scan_android_sdk()
    assert (item.verdict, item.license) == ("nonfree", "LicenseRef-Android-SDK-License")
    assert "Android SDK License accepted (android-sdk-license, google-gdk-license)" in item.reason


def test_foss_android_sdk(home: Path) -> None:
    sdk = home / "sdk/foss-android-sdk"
    assert scan_android.scan_foss_android_sdk() == []
    sdk.mkdir(parents=True)
    (item,) = scan_android.scan_foss_android_sdk()
    assert (item.name, item.source, item.verdict) == ("foss-android-sdk", "user-app", "foss")
    assert "Apache-2.0 WITH LLVM-exception" in item.license
    assert item.reason.startswith("~/sdk/foss-android-sdk; ")
    assert item.removeCommand == f"rm -rf {sdk}"


def test_foss_sdk_is_the_installed_alternative(home: Path) -> None:
    (home / "sdk/Android/Sdk/licenses").mkdir(parents=True)
    write(home / "sdk/Android/Sdk/licenses/android-sdk-license", "abc\n", 0o644)
    (home / "sdk/foss-android-sdk").mkdir(parents=True)
    items = apply(scan_userapp.scan_user_apps(), Curated.load())
    (google,) = [i for i in items if i.name == "android-sdk"]
    assert google.alternative is not None
    assert "foss-android-sdk" in google.alternative.installed
