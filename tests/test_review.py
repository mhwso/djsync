import builtins

from djsync.review import _ask


def test_ask_returns_none_on_eof(monkeypatch):
    def eof(_prompt):
        raise EOFError

    monkeypatch.setattr(builtins, "input", eof)
    assert _ask("> ") is None


def test_ask_passes_input_through(monkeypatch):
    monkeypatch.setattr(builtins, "input", lambda _prompt: "2")
    assert _ask("> ") == "2"
