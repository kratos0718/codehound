"""Tests for --fix: CH017 and CH004 (inside async only)."""

from __future__ import annotations

import ast

from codehound.core import build_parents
from codehound.fixes import fix_source


def _fix(code: str) -> tuple[str, int]:
    tree = ast.parse(code)
    parents = build_parents(tree)
    return fix_source(code, tree, parents)


def test_fixes_collections_import_from():
    code = "from collections import Mapping\n"
    new_code, count = _fix(code)
    assert count == 1
    assert new_code == "from collections.abc import Mapping\n"


def test_fixes_collections_import_from_multiple_names():
    code = "from collections import Mapping, Sequence\n"
    new_code, count = _fix(code)
    assert count == 1
    assert new_code == "from collections.abc import Mapping, Sequence\n"


def test_fixes_collections_attribute_usage():
    code = "import collections\nx = collections.Mapping\n"
    new_code, count = _fix(code)
    assert count == 1
    assert new_code == "import collections\nx = collections.abc.Mapping\n"


def test_fixes_get_event_loop_inside_async_function():
    code = "import asyncio\nasync def f():\n    loop = asyncio.get_event_loop()\n"
    new_code, count = _fix(code)
    assert count == 1
    assert new_code == "import asyncio\nasync def f():\n    loop = asyncio.get_running_loop()\n"


def test_does_not_fix_get_event_loop_outside_async_function():
    # get_running_loop() raises RuntimeError with no running loop, where
    # get_event_loop() wouldn't - not a safe blind rewrite outside async.
    code = "import asyncio\ndef f():\n    loop = asyncio.get_event_loop()\n"
    new_code, count = _fix(code)
    assert count == 0
    assert new_code == code


def test_fixes_nothing_when_no_fixable_findings():
    code = "import os\nprint(os.getcwd())\n"
    new_code, count = _fix(code)
    assert count == 0
    assert new_code is code


def test_fixes_multiple_edits_in_one_file():
    code = (
        "from collections import Mapping\n"
        "import asyncio\n"
        "\n"
        "async def f():\n"
        "    loop = asyncio.get_event_loop()\n"
        "    return isinstance({}, collections.Mapping)\n"
    )
    new_code, count = _fix(code)
    assert count == 3
    assert "from collections.abc import Mapping" in new_code
    assert "asyncio.get_running_loop()" in new_code
    assert "collections.abc.Mapping" in new_code
    # Original line count/structure preserved.
    assert new_code.count("\n") == code.count("\n")


def test_fixes_ignores_already_qualified_collections_abc():
    code = "from collections.abc import Mapping\n"
    new_code, count = _fix(code)
    assert count == 0
    assert new_code is code
