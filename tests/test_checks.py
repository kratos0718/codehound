"""Unit tests for every check, using small inline source snippets.

Each test asserts both that the bad pattern is flagged and that a corrected
version is *not* flagged (no false positives).
"""

from __future__ import annotations

import ast

from codehound.checks import get_checks
from codehound.core import build_parents


def _run(code: str, select: list[str]) -> list:
    tree = ast.parse(code)
    parents = build_parents(tree)
    findings = []
    for check in get_checks(select):
        findings.extend(check.run(tree, parents, "<test>"))
    return findings


# --- CH001 blocking-call-in-async -------------------------------------------------


def test_ch001_flags_time_sleep_in_async():
    code = (
        "import time\n"
        "async def f():\n"
        "    time.sleep(1)\n"
    )
    findings = _run(code, ["CH001"])
    assert len(findings) == 1
    assert findings[0].code == "CH001"


def test_ch001_ignores_sleep_in_sync_function():
    code = (
        "import time\n"
        "def f():\n"
        "    time.sleep(1)\n"
    )
    assert _run(code, ["CH001"]) == []


def test_ch001_ignores_await_asyncio_sleep():
    code = (
        "import asyncio\n"
        "async def f():\n"
        "    await asyncio.sleep(1)\n"
    )
    assert _run(code, ["CH001"]) == []


# --- CH002 mutable-default-argument -----------------------------------------------


def test_ch002_flags_list_default():
    code = "def f(x=[]):\n    return x\n"
    findings = _run(code, ["CH002"])
    assert len(findings) == 1


def test_ch002_flags_dict_factory_default():
    code = "def f(x=dict()):\n    return x\n"
    assert len(_run(code, ["CH002"])) == 1


def test_ch002_ignores_none_default():
    code = "def f(x=None):\n    return x or []\n"
    assert _run(code, ["CH002"]) == []


# --- CH003 deprecated-datetime-utcnow ---------------------------------------------


def test_ch003_flags_utcnow():
    code = "from datetime import datetime\nx = datetime.utcnow()\n"
    assert len(_run(code, ["CH003"])) == 1


def test_ch003_ignores_now_with_tz():
    code = "from datetime import datetime, timezone\nx = datetime.now(timezone.utc)\n"
    assert _run(code, ["CH003"]) == []


# --- CH004 deprecated-get-event-loop ----------------------------------------------


def test_ch004_flags_get_event_loop():
    code = "import asyncio\nloop = asyncio.get_event_loop()\n"
    assert len(_run(code, ["CH004"])) == 1


def test_ch004_ignores_get_running_loop():
    code = "import asyncio\nloop = asyncio.get_running_loop()\n"
    assert _run(code, ["CH004"]) == []


# --- CH005 unclosed-file-handle ---------------------------------------------------


def test_ch005_flags_unclosed_open():
    code = "def f(p):\n    fh = open(p)\n    return fh.read()\n"
    assert len(_run(code, ["CH005"])) == 1


def test_ch005_ignores_with_open():
    code = "def f(p):\n    with open(p) as fh:\n        return fh.read()\n"
    assert _run(code, ["CH005"]) == []


def test_ch005_ignores_explicit_close():
    code = "def f(p):\n    fh = open(p)\n    data = fh.read()\n    fh.close()\n    return data\n"
    assert _run(code, ["CH005"]) == []


def test_ch005_ignores_returned_handle():
    code = "def open_reader(p):\n    fh = open(p, 'rb')\n    return fh\n"
    assert _run(code, ["CH005"]) == []


# --- CH006 floating-task ----------------------------------------------------------


def test_ch006_flags_discarded_create_task():
    code = (
        "import asyncio\n"
        "async def f(coro):\n"
        "    asyncio.create_task(coro)\n"
    )
    assert len(_run(code, ["CH006"])) == 1


def test_ch006_ignores_referenced_task():
    code = (
        "import asyncio\n"
        "async def f(coro):\n"
        "    t = asyncio.create_task(coro)\n"
        "    await t\n"
    )
    assert _run(code, ["CH006"]) == []


def test_ch006_ignores_taskgroup_create_task():
    code = (
        "async def f(tg, coro):\n"
        "    tg.create_task(coro)\n"
    )
    assert _run(code, ["CH006"]) == []
