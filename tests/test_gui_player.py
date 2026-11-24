"""Anhören der lokalen Datei über die API-Schicht der GUI."""

import io
import os
import shutil
import wave
from pathlib import Path

import httpx
import pytest

from djsync.gui.api import ApiError


@pytest.fixture(autouse=True)
def close_media(ctx):
    yield
    ctx.media.close()


@pytest.fixture
def folder(run_cli, music):
    """Synchronisierter Ordner mit einer (Schein-)MP3; ohne Katalog → „nicht gefunden“."""
    path = music.folder("Mix", "Alpha - One.mp3")
    assert run_cli("sync", path, "--yes") == 0
    return path


def fingerprint(api, folder, filename):
    return next(t["fingerprint"] for t in api.review.tracks(folder)["tracks"] if t["filename"] == filename)


def get(url, **headers):
    return httpx.get(url, headers=headers, timeout=5)


def test_local_file_is_served_unchanged(api, folder):
    fp = fingerprint(api, folder, "Alpha - One.mp3")

    played = api.player.local(folder, fp)

    response = get(played["url"])
    assert response.status_code == 200
    assert response.headers["content-type"] == "audio/mpeg"
    assert response.content == b"\0" * 16
    assert played["url"].startswith("http://127.0.0.1:")
    assert played["converted"] is False


def test_local_file_supports_ranges_for_seeking(api, folder, music):
    (music.root / "Mix" / "Alpha - One.mp3").write_bytes(bytes(range(100)))
    url = api.player.local(folder, fingerprint(api, folder, "Alpha - One.mp3"))["url"]

    middle = get(url, Range="bytes=10-19")
    tail = get(url, Range="bytes=95-")
    beyond = get(url, Range="bytes=200-")

    assert middle.status_code == 206
    assert middle.content == bytes(range(10, 20))
    assert middle.headers["content-range"] == "bytes 10-19/100"
    assert tail.content == bytes(range(95, 100))
    assert beyond.status_code == 416


def test_only_released_files_are_served(api, folder):
    url = api.player.local(folder, fingerprint(api, folder, "Alpha - One.mp3"))["url"]
    base = url.split("/media/")[0]

    assert get(f"{base}/media/geraten/Alpha%20-%20One.mp3").status_code == 404
    assert get(f"{base}/etc/passwd").status_code == 404


def test_missing_file_is_reported(api, folder, music):
    fp = fingerprint(api, folder, "Alpha - One.mp3")
    (music.root / "Mix" / "Alpha - One.mp3").unlink()

    with pytest.raises(ApiError, match="nicht .*vorhanden"):
        api.player.local(folder, fp)


def test_unknown_track_is_reported(api, folder):
    with pytest.raises(ApiError, match="Track"):
        api.player.local(folder, "gibt-es-nicht")


# ---- AIFF -------------------------------------------------------------------

DATA = Path(__file__).parent / "data"


@pytest.fixture
def aiff_folder(run_cli, music):
    """Ordner mit echten kleinen AIFF-Dateien (tests/data, 44,1 kHz)."""
    folder = music.root / "Aiff"
    folder.mkdir(parents=True)
    shutil.copy(DATA / "stereo-16bit.aiff", folder / "Alpha - Stereo.aiff")
    shutil.copy(DATA / "mono-24bit.aiff", folder / "Beta - Mono.aif")
    assert run_cli("sync", str(folder), "--yes") == 0
    return str(folder)


def wav_samples(url):
    """(Kanäle, Bytes pro Sample, Abtastrate, Samples) der WAV-Datei hinter der Adresse."""
    response = get(url)
    assert response.status_code == 200
    assert response.headers["content-type"] == "audio/wav"
    with wave.open(io.BytesIO(response.content)) as w:
        width = w.getsampwidth()
        raw = w.readframes(w.getnframes())
        samples = [int.from_bytes(raw[i : i + width], "little", signed=True) for i in range(0, len(raw), width)]
        return w.getnchannels(), width, w.getframerate(), samples


def test_aiff_is_converted_to_wav(api, aiff_folder):
    played = api.player.local(aiff_folder, fingerprint(api, aiff_folder, "Alpha - Stereo.aiff"))

    assert played["converted"] is True
    channels, width, rate, samples = wav_samples(played["url"])
    assert (channels, width, rate) == (2, 2, 44100)
    # links 0, 1000, 2000 …; rechts 0, -1000, -2000 …
    assert samples[:6] == [0, 0, 1000, -1000, 2000, -2000]
    assert samples[-2:] == [9000, -9000]
    assert len(samples) == 20


def test_24bit_aif_is_converted_to_wav(api, aiff_folder):
    played = api.player.local(aiff_folder, fingerprint(api, aiff_folder, "Beta - Mono.aif"))

    channels, width, rate, samples = wav_samples(played["url"])
    assert (channels, width, rate) == (1, 3, 44100)
    assert samples == [-400000, -300000, -200000, -100000, 0, 100000, 200000, 300000, 400000]


def cached(paths):
    return sorted((paths.data_dir / "cache").rglob("*.wav"))


def test_converted_aiff_is_reused_from_cache(api, aiff_folder, paths):
    fp = fingerprint(api, aiff_folder, "Alpha - Stereo.aiff")
    first = api.player.local(aiff_folder, fp)
    [wav] = cached(paths)
    os.utime(wav, (1_600_000_000, 1_600_000_000))  # erneutes Umwandeln würde das ändern

    second = api.player.local(aiff_folder, fp)

    assert second["url"] == first["url"]
    assert cached(paths) == [wav]
    assert wav.stat().st_mtime == 1_600_000_000


def test_changed_aiff_is_converted_again(api, aiff_folder, paths):
    source = Path(aiff_folder) / "Alpha - Stereo.aiff"
    fp = fingerprint(api, aiff_folder, "Alpha - Stereo.aiff")
    api.player.local(aiff_folder, fp)
    shutil.copy(DATA / "mono-24bit.aiff", source)  # andere Aufnahme unter demselben Namen

    played = api.player.local(aiff_folder, fp)

    channels, width, _rate, samples = wav_samples(played["url"])
    assert (channels, width) == (1, 3)
    assert samples[0] == -400000
    assert len(cached(paths)) == 1  # die alte Fassung ist entfernt


def test_unreadable_aiff_is_reported(api, aiff_folder):
    fp = fingerprint(api, aiff_folder, "Alpha - Stereo.aiff")
    (Path(aiff_folder) / "Alpha - Stereo.aiff").write_bytes(b"FORM\0\0\0\4AIFC")

    with pytest.raises(ApiError, match="lässt sich nicht abspielen"):
        api.player.local(aiff_folder, fp)
