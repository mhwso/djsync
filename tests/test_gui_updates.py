"""Update-Hinweis: Abfrage der neuesten GitHub-Release-Version über die API-Schicht der GUI."""

import pytest

from djsync import __version__


def test_newer_release_is_reported_with_link(api, github):
    github.latest_tag = "v99.0.0"

    assert api.updates.check() == {
        "version": "99.0.0",
        "current": __version__,
        "url": "https://github.com/mhwso/djsync/releases/tag/v99.0.0",
    }


def test_same_version_gives_no_notice(api, github):
    github.latest_tag = f"v{__version__}"

    assert api.updates.check() is None


def test_same_version_with_extra_zero_gives_no_notice(api, github):
    github.latest_tag = f"v{__version__}.0"

    assert api.updates.check() is None


def test_older_release_gives_no_notice(api, github):
    github.latest_tag = "v0.0.1"

    assert api.updates.check() is None


@pytest.mark.parametrize(
    "fault",
    [
        pytest.param({"offline": True}, id="offline"),
        pytest.param({"status": 403}, id="rate-limit"),
        pytest.param({"status": 500}, id="serverfehler"),
        pytest.param({"latest_tag": None}, id="noch-kein-release"),
        pytest.param({"latest_tag": "nightly"}, id="unbekanntes-tag"),
    ],
)
def test_errors_are_ignored(api, github, fault):
    for name, value in fault.items():
        setattr(github, name, value)

    assert api.updates.check() is None
    assert github.requests  # es wurde wirklich gefragt
