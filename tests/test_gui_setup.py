"""Einrichtung über die API-Schicht der GUI: Status, Client-ID, Anmeldung im System-Browser."""

import json
import socket
import time
from urllib.parse import parse_qs, urlparse

import httpx
import pytest
from conftest import CLIENT_ID

from djsync.gui.api import ApiError
from djsync.gui.api import setup as setup_api


def test_existing_setup_is_recognised(api):
    status = api.setup.status()
    assert status["client_id"] is True
    assert status["logged_in"] is True
    assert status["needed"] is False


def test_setup_needed_without_client_id(api, paths):
    paths.config_file.unlink()
    paths.token_file.unlink()

    status = api.setup.status()
    assert (status["client_id"], status["logged_in"], status["needed"]) == (False, False, True)
    # Für die Schritte im Spotify-Dashboard
    assert status["redirect_uri"] == "http://127.0.0.1:8888/callback"
    assert status["dashboard_url"] == "https://developer.spotify.com/dashboard"


def test_setup_needed_without_login(api, paths):
    paths.token_file.unlink()

    status = api.setup.status()
    assert (status["client_id"], status["logged_in"], status["needed"]) == (True, False, True)


def test_login_without_all_permissions_counts_as_missing(api, paths):
    token = json.loads(paths.token_file.read_text())
    token["scope"] = "playlist-read-private"
    paths.token_file.write_text(json.dumps(token))

    assert api.setup.status()["logged_in"] is False


def test_redirect_uri_from_config_is_shown(api, paths):
    paths.config_file.write_text(
        paths.config_file.read_text() + 'redirect_uri = "http://127.0.0.1:9999/cb"\n', encoding="utf-8"
    )
    assert api.setup.status()["redirect_uri"] == "http://127.0.0.1:9999/cb"


VALID_ID = "0123456789abcdef0123456789abcdef"


def test_valid_client_id_is_saved(api, paths, ctx):
    paths.config_file.unlink()
    paths.token_file.unlink()

    status = api.setup.save_client_id(f"  {VALID_ID.upper()}\n")

    assert status["client_id"] is True
    assert status["needed"] is True  # Anmeldung fehlt noch
    assert ctx.load_config().client_id == VALID_ID


@pytest.mark.parametrize("value", ["", "abc", "g" * 32, VALID_ID + "0"])
def test_invalid_client_id_is_rejected(api, paths, ctx, value):
    with pytest.raises(ApiError, match="32 Zeichen"):
        api.setup.save_client_id(value)
    assert ctx.load_config().client_id == CLIENT_ID  # unverändert


def test_saving_keeps_other_settings(api, paths, ctx):
    paths.config_file.write_text(f'client_id = "{CLIENT_ID}"\nmin_score = 0.9\n', encoding="utf-8")

    api.setup.save_client_id(VALID_ID)

    cfg = ctx.load_config()
    assert (cfg.client_id, cfg.min_score) == (VALID_ID, 0.9)


def test_new_client_id_requires_new_login(api):
    # Das Token gehört zur bisherigen App im Spotify-Dashboard
    status = api.setup.save_client_id(VALID_ID)
    assert (status["logged_in"], status["needed"]) == (False, True)


def test_same_client_id_keeps_login(api):
    status = api.setup.save_client_id(CLIENT_ID)
    assert (status["logged_in"], status["needed"]) == (True, False)


# ---- Anmeldung im System-Browser ---------------------------------------------


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@pytest.fixture
def browser(paths, monkeypatch):
    """Statt des System-Browsers: merkt sich die geöffnete Adresse. Redirect-URI auf freiem Port."""
    redirect = f"http://127.0.0.1:{_free_port()}/callback"
    paths.config_file.write_text(
        paths.config_file.read_text() + f'redirect_uri = "{redirect}"\n', encoding="utf-8"
    )
    paths.token_file.unlink()
    opened = []
    monkeypatch.setattr(setup_api, "open_browser", opened.append)

    class Browser:
        redirect_uri = redirect

        @property
        def url(self):
            return opened[-1]

        def confirm(self, **params):
            """Spotify leitet nach der Bestätigung auf die Redirect-URI weiter."""
            state = parse_qs(urlparse(self.url).query)["state"][0]
            r = httpx.get(self.redirect_uri, params={"state": state, **params}, timeout=5)
            assert r.status_code == 200

    return Browser()


def _wait_for_login(events) -> dict:
    deadline = time.time() + 5
    while not events.named("setup.login"):
        assert time.time() < deadline, "Anmeldung nicht abgeschlossen"
        time.sleep(0.01)
    [result] = events.named("setup.login")
    return result


def test_login_in_system_browser(api, browser, spotify, events):
    started = api.setup.start_login()

    assert started["url"] == browser.url
    assert browser.url.startswith("https://accounts.spotify.com/authorize?")
    assert api.setup.status()["login"] == {"state": "waiting", "message": None}

    browser.confirm(code="auth-code")

    assert _wait_for_login(events) == {"state": "success", "message": None}
    status = api.setup.status()
    assert (status["logged_in"], status["needed"]) == (True, False)
    assert status["login"]["state"] == "success"
    assert spotify.token_requests[-1]["code"] == ["auth-code"]


def test_login_refused_in_browser(api, browser, events):
    api.setup.start_login()
    browser.confirm(error="access_denied")

    result = _wait_for_login(events)
    assert result["state"] == "error"
    assert "abgelehnt" in result["message"]
    assert api.setup.status()["logged_in"] is False


def test_login_token_exchange_fails(api, browser, spotify, events):
    spotify.token_status = 400
    api.setup.start_login()
    browser.confirm(code="auth-code")

    result = _wait_for_login(events)
    assert result["state"] == "error"
    assert "Token-Abruf fehlgeschlagen" in result["message"]


def test_login_can_be_cancelled(api, browser, events):
    api.setup.start_login()
    api.setup.cancel_login()

    assert _wait_for_login(events)["state"] == "cancelled"
    assert api.setup.status()["login"]["state"] == "cancelled"


def test_login_restart_replaces_waiting_login(api, browser):
    api.setup.start_login()
    api.setup.start_login()  # z. B. Browser-Fenster versehentlich geschlossen
    browser.confirm(code="auth-code")

    deadline = time.time() + 5
    while api.setup.status()["login"]["state"] != "success":
        assert time.time() < deadline
        time.sleep(0.01)
    assert api.setup.status()["logged_in"] is True


def test_login_needs_client_id(api, paths):
    paths.config_file.unlink()
    with pytest.raises(ApiError, match="Client-ID"):
        api.setup.start_login()


def test_login_port_in_use_is_reported(api, browser):
    port = urlparse(browser.redirect_uri).port
    with socket.socket() as blocker:
        blocker.bind(("127.0.0.1", port))
        blocker.listen()
        with pytest.raises(ApiError, match=str(port)):
            api.setup.start_login()
