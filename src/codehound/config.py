"""Project config: ``[tool.codehound]`` in ``pyproject.toml``.

Loaded with the standard-library ``tomllib`` (Python 3.11+), falling back
to the ``tomli`` backport *only if it happens to already be installed*
(it's listed in the ``dev`` extras so the test suite can exercise config
loading on 3.9/3.10 too) - never a required install. If neither is
available, config loading is silently skipped rather than failing: the
CLI still works identically with explicit flags either way, so a missing
TOML parser never blocks a scan, it only means the config-file
convenience isn't available on that Python. This keeps the
zero-runtime-dependency guarantee: nothing here is ever a hard
requirement to run `codehound scan`.

Recognized keys, all optional:

    [tool.codehound]
    select = ["CH001", "CH006"]   # same as --select
    exclude = ["migrations"]      # extra directory names to skip, merged
                                   # with the built-in DEFAULT_SKIP_DIRS
    paths = ["src"]               # default paths when none given on the CLI

Explicit CLI flags always take precedence over the config file - the
config only fills in what wasn't passed on the command line.
"""

from __future__ import annotations

import os

try:
    import tomllib
except ImportError:  # Python < 3.11
    try:
        import tomli as tomllib  # type: ignore[import-not-found,no-redef]
    except ImportError:
        tomllib = None  # type: ignore[assignment]


class CodehoundConfig:
    def __init__(
        self,
        select: list[str] | None = None,
        exclude: list[str] | None = None,
        paths: list[str] | None = None,
    ) -> None:
        self.select = select
        self.exclude = exclude or []
        self.paths = paths


_EMPTY = CodehoundConfig()


def load_config(start_dir: str = ".") -> CodehoundConfig:
    """Read ``[tool.codehound]`` from ``pyproject.toml`` in ``start_dir``.

    Returns an empty config (every field ``None``/``[]``) if the file
    doesn't exist, has no ``[tool.codehound]`` table, or ``tomllib`` isn't
    available on this Python version - never raises for any of those.
    """
    if tomllib is None:
        return _EMPTY

    pyproject_path = os.path.join(start_dir, "pyproject.toml")
    if not os.path.isfile(pyproject_path):
        return _EMPTY

    try:
        with open(pyproject_path, "rb") as fh:
            data = tomllib.load(fh)
    except (OSError, tomllib.TOMLDecodeError):
        return _EMPTY

    table = data.get("tool", {}).get("codehound", {})
    if not isinstance(table, dict):
        return _EMPTY

    select = table.get("select")
    exclude = table.get("exclude")
    paths = table.get("paths")
    return CodehoundConfig(
        select=list(select) if isinstance(select, list) else None,
        exclude=list(exclude) if isinstance(exclude, list) else None,
        paths=list(paths) if isinstance(paths, list) else None,
    )
