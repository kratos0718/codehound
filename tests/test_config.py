"""Tests for [tool.codehound] project config loading."""

from __future__ import annotations

import tempfile
import os

from codehound.config import load_config


def _write_pyproject(tmpdir: str, content: str) -> None:
    with open(os.path.join(tmpdir, "pyproject.toml"), "w") as fh:
        fh.write(content)


def test_load_config_reads_select_exclude_paths():
    with tempfile.TemporaryDirectory() as tmpdir:
        _write_pyproject(
            tmpdir,
            """
            [tool.codehound]
            select = ["CH001", "CH006"]
            exclude = ["migrations"]
            paths = ["src"]
            """,
        )
        config = load_config(tmpdir)
        assert config.select == ["CH001", "CH006"]
        assert config.exclude == ["migrations"]
        assert config.paths == ["src"]


def test_load_config_missing_file_returns_empty_config():
    with tempfile.TemporaryDirectory() as tmpdir:
        config = load_config(tmpdir)
        assert config.select is None
        assert config.exclude == []
        assert config.paths is None


def test_load_config_file_without_codehound_table_returns_empty_config():
    with tempfile.TemporaryDirectory() as tmpdir:
        _write_pyproject(tmpdir, "[tool.black]\nline-length = 100\n")
        config = load_config(tmpdir)
        assert config.select is None
        assert config.exclude == []
        assert config.paths is None


def test_load_config_partial_table_leaves_other_fields_empty():
    with tempfile.TemporaryDirectory() as tmpdir:
        _write_pyproject(tmpdir, '[tool.codehound]\nselect = ["CH002"]\n')
        config = load_config(tmpdir)
        assert config.select == ["CH002"]
        assert config.exclude == []
        assert config.paths is None


def test_load_config_malformed_toml_does_not_raise():
    with tempfile.TemporaryDirectory() as tmpdir:
        _write_pyproject(tmpdir, "this is not [valid toml")
        config = load_config(tmpdir)
        assert config.select is None
