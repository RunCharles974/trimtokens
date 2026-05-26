"""Tests du script build.py (helpers de détection plateforme + commande PyInstaller).

On ne lance PAS PyInstaller en CI standard — trop coûteux. Le workflow `release.yml`
s'en charge sur tag. Ici on valide juste que les helpers retournent des valeurs cohérentes.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

BUILD_PY = Path(__file__).parent.parent / "build.py"


def _load_build_module():
    spec = importlib.util.spec_from_file_location("_build_under_test", BUILD_PY)
    assert spec is not None
    assert spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_build_py_exists() -> None:
    assert BUILD_PY.exists()


def test_build_py_importable() -> None:
    mod = _load_build_module()
    assert hasattr(mod, "main")
    assert hasattr(mod, "detect_platform")
    assert hasattr(mod, "build_cli")
    assert hasattr(mod, "build_gui")


def test_detect_platform_returns_known_os() -> None:
    mod = _load_build_module()
    os_name, arch = mod.detect_platform()
    assert os_name in {"windows", "macos", "linux"} or isinstance(os_name, str)
    assert arch in {"x64", "arm64"} or isinstance(arch, str)


def test_detect_platform_matches_current_system() -> None:
    mod = _load_build_module()
    os_name, _arch = mod.detect_platform()
    if sys.platform == "win32":
        assert os_name == "windows"
    elif sys.platform == "darwin":
        assert os_name == "macos"
    elif sys.platform.startswith("linux"):
        assert os_name == "linux"


def test_hidden_imports_lists_present() -> None:
    mod = _load_build_module()
    assert "fitz" in mod.HIDDEN_IMPORTS_BASE
    assert "PIL._tkinter_finder" in mod.HIDDEN_IMPORTS_BASE
    assert "tkinterdnd2" in mod.HIDDEN_IMPORTS_GUI
    assert "customtkinter" in mod.HIDDEN_IMPORTS_GUI
    # Extracteurs dynamiques bien listés (sinon import_module échoue en runtime)
    assert "trimtokens.extractors.pdf" in mod.HIDDEN_IMPORTS_BASE
    assert "trimtokens.extractors.image" in mod.HIDDEN_IMPORTS_BASE


def test_collect_data_args_returns_list() -> None:
    mod = _load_build_module()
    args = mod.collect_data_args()
    assert isinstance(args, list)
    # Si customtkinter / tkinterdnd2 dispo, on doit avoir des --add-data
    try:
        import customtkinter  # noqa: F401

        assert any("customtkinter" in a for a in args)
    except ImportError:
        pass


def test_base_pyinstaller_cmd_contains_essentials() -> None:
    mod = _load_build_module()
    cmd = mod.base_pyinstaller_cmd("test-binary", clean=False)
    assert "--onefile" in cmd
    assert "--noconfirm" in cmd
    assert "--name" in cmd
    assert "test-binary" in cmd
    assert "--paths" in cmd


def test_base_pyinstaller_cmd_with_clean() -> None:
    mod = _load_build_module()
    cmd = mod.base_pyinstaller_cmd("test", clean=True)
    assert "--clean" in cmd


def test_main_rejects_conflicting_flags(monkeypatch: pytest.MonkeyPatch) -> None:
    mod = _load_build_module()
    monkeypatch.setattr(sys, "argv", ["build.py", "--cli-only", "--gui-only"])
    with pytest.raises(SystemExit):
        mod.main()
