"""SPA fallback must only serve files inside the static directory."""

from __future__ import annotations

from app.main import static_file


def test_serves_file_inside_static_dir(tmp_path):
    static = tmp_path / "static"
    static.mkdir()
    (static / "favicon.svg").write_text("<svg/>")
    assert static_file(static, "favicon.svg") == (static / "favicon.svg").resolve()


def test_missing_file_returns_none(tmp_path):
    static = tmp_path / "static"
    static.mkdir()
    assert static_file(static, "cycle") is None


def test_parent_traversal_is_refused(tmp_path):
    static = tmp_path / "static"
    static.mkdir()
    (tmp_path / "secret.txt").write_text("nope")
    assert static_file(static, "../secret.txt") is None
    assert static_file(static, "assets/../../secret.txt") is None


def test_absolute_path_is_refused(tmp_path):
    static = tmp_path / "static"
    static.mkdir()
    (tmp_path / "secret.txt").write_text("nope")
    assert static_file(static, str(tmp_path / "secret.txt")) is None
