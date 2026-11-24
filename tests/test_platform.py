import sys

import pytest

from djsync import config
from djsync.filenames import normalize_folder

# ---- Ordnerpfade ------------------------------------------------------------


posix_only = pytest.mark.skipif(sys.platform == "win32", reason="Linux/WSL-Pfade")


@posix_only
def test_wsl_translates_windows_paths():
    assert normalize_folder(r"D:\Rekordbox Library\2026", wsl=True) == "/mnt/d/Rekordbox Library/2026"


def test_windows_uses_forward_slashes():
    assert normalize_folder(r"D:\Musik\2026\\", wsl=False, sep="\\") == "D:/Musik/2026"


def test_windows_drive_root_keeps_slash():
    assert normalize_folder("D:\\", wsl=False, sep="\\") == "D:/"


def test_quotes_from_drag_and_drop_are_removed():
    assert normalize_folder('"D:\\Musik\\House" ', wsl=False, sep="\\") == "D:/Musik/House"


@posix_only
def test_posix_path_unchanged():
    assert normalize_folder("/mnt/d/Musik/", wsl=False) == "/mnt/d/Musik"


# ---- Client-ID ----------------------------------------------------------------


def test_client_id_validation():
    assert config.is_valid_client_id("cf6b0db90df8468dbda78ae3f260c0c0")
    assert not config.is_valid_client_id("abc")
    assert not config.is_valid_client_id("https://developer.spotify.com/dashboard")


def test_save_client_id_keeps_other_settings(tmp_path):
    path = tmp_path / "config.toml"
    path.write_text("min_score = 0.8\n", encoding="utf-8")
    config.save_client_id("a" * 32, path)
    config.save_client_id("b" * 32, path)
    text = path.read_text(encoding="utf-8")
    assert text.count("client_id") == 1
    assert f'client_id = "{"b" * 32}"' in text and "min_score = 0.8" in text


@pytest.fixture
def isolated_config(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "CONFIG_FILE", tmp_path / "config.toml")
    monkeypatch.setattr(config, "PROJECT_ENV_FILE", tmp_path / ".env")
    monkeypatch.delenv("SPOTIFY_CLIENT_ID", raising=False)
    return tmp_path


def test_client_id_from_config_toml(isolated_config):
    config.save_client_id("c" * 32, isolated_config / "config.toml")
    cfg = config.load_config()
    assert cfg.client_id == "c" * 32
    assert "client_id" not in cfg.extra


def test_missing_client_id_points_to_setup(isolated_config):
    with pytest.raises(config.ConfigError, match="djsync setup"):
        config.load_config()
    assert not config.has_client_id()


def test_env_var_overrides_config(isolated_config, monkeypatch):
    config.save_client_id("c" * 32, isolated_config / "config.toml")
    monkeypatch.setenv("SPOTIFY_CLIENT_ID", "d" * 32)
    assert config.load_config().client_id == "d" * 32
