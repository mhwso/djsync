import sys

import pytest

from djsync import cli, config, wizard


class FakeStdin:
    def isatty(self):
        return True


@pytest.fixture
def env(tmp_path, monkeypatch):
    """Isolierte Konfiguration, kein Browser, kein echter Login."""
    cfg_file = tmp_path / "config.toml"
    monkeypatch.setattr(config, "CONFIG_FILE", cfg_file)
    monkeypatch.setattr(config, "PROJECT_ENV_FILE", tmp_path / ".env")
    monkeypatch.setattr(wizard, "CONFIG_FILE", cfg_file)
    monkeypatch.setattr(wizard, "TOKEN_FILE", tmp_path / "token.json")
    monkeypatch.setattr(wizard, "save_client_id", lambda v: config.save_client_id(v, cfg_file))
    monkeypatch.setattr(wizard, "open_browser", lambda url: None)
    monkeypatch.setattr(wizard, "IS_WINDOWS", False)
    monkeypatch.setattr(sys, "stdin", FakeStdin())
    monkeypatch.delenv("SPOTIFY_CLIENT_ID", raising=False)
    calls = {"login": 0, "sync": []}
    monkeypatch.setattr(cli, "cmd_login", lambda args: calls.__setitem__("login", calls["login"] + 1))
    monkeypatch.setattr(cli, "cmd_sync", lambda args: calls["sync"].append(args.folder))
    return tmp_path, calls


def feed(monkeypatch, *answers):
    it = iter(answers)

    def fake_input(_prompt=""):
        try:
            return next(it)
        except StopIteration:
            raise EOFError from None

    monkeypatch.setattr("builtins.input", fake_input)


def test_first_start_runs_setup_then_asks_for_folder(env, monkeypatch):
    tmp_path, calls = env
    feed(monkeypatch, "", "keine-id", "c" * 32, '"D:\\Musik\\2026"', "")
    assert wizard.run_interactive(None) == 0
    assert config.load_config().client_id == "c" * 32
    assert calls["login"] == 1
    assert calls["sync"] == ['"D:\\Musik\\2026"']


def test_dropped_folder_is_synced_directly(env, monkeypatch):
    tmp_path, calls = env
    config.save_client_id("c" * 32, tmp_path / "config.toml")
    (tmp_path / "token.json").write_text("{}")
    feed(monkeypatch, "")
    assert wizard.run_interactive("D:\\Musik") == 0
    assert calls == {"login": 0, "sync": ["D:\\Musik"]}


def test_missing_token_triggers_login(env, monkeypatch):
    tmp_path, calls = env
    config.save_client_id("c" * 32, tmp_path / "config.toml")
    feed(monkeypatch, "")
    wizard.run_interactive(None)
    assert calls["login"] == 1


def test_eof_during_setup_cancels(env, monkeypatch):
    feed(monkeypatch)
    assert wizard.run_interactive(None) == 130


def test_main_dispatches_dropped_folder(env, monkeypatch, tmp_path):
    seen = []
    monkeypatch.setattr(cli, "run_interactive", lambda folder: seen.append(folder) or 0)
    assert cli.main([str(tmp_path)]) == 0
    assert cli.main([]) == 0
    assert seen == [str(tmp_path), None]
