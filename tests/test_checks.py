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


def test_ch001_ignores_awaited_call_on_sync_named_receiver():
    # A local variable named `requests` that is actually an async client; the
    # call is awaited, so it does not block the loop. (Real false positive seen
    # in AutoGPT's MCP client.)
    code = (
        "async def f(self):\n"
        "    requests = AsyncClient()\n"
        "    response = await requests.post(self.url, json={})\n"
    )
    assert _run(code, ["CH001"]) == []


def test_ch001_still_flags_unawaited_blocking_call_in_async():
    code = (
        "import requests\n"
        "async def f(url):\n"
        "    return requests.get(url)\n"
    )
    assert len(_run(code, ["CH001"])) == 1


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


# --- CH007 unawaited-coroutine-call ------------------------------------------------


def test_ch007_flags_bare_call_to_async_function():
    code = (
        "async def fetch():\n"
        "    ...\n"
        "async def f():\n"
        "    fetch()\n"
    )
    findings = _run(code, ["CH007"])
    assert len(findings) == 1
    assert findings[0].code == "CH007"


def test_ch007_ignores_awaited_call():
    code = (
        "async def fetch():\n"
        "    ...\n"
        "async def f():\n"
        "    await fetch()\n"
    )
    assert _run(code, ["CH007"]) == []


def test_ch007_ignores_call_wrapped_in_create_task():
    code = (
        "import asyncio\n"
        "async def fetch():\n"
        "    ...\n"
        "async def f():\n"
        "    asyncio.create_task(fetch())\n"
    )
    assert _run(code, ["CH007"]) == []


def test_ch007_ignores_assigned_result():
    code = (
        "async def fetch():\n"
        "    ...\n"
        "async def f():\n"
        "    coro = fetch()\n"
        "    await coro\n"
    )
    assert _run(code, ["CH007"]) == []


def test_ch007_ignores_call_to_sync_function():
    code = (
        "def fetch():\n"
        "    ...\n"
        "async def f():\n"
        "    fetch()\n"
    )
    assert _run(code, ["CH007"]) == []


def test_ch007_flags_bare_call_to_async_method_via_self():
    code = (
        "class C:\n"
        "    async def fetch(self):\n"
        "        ...\n"
        "    async def f(self):\n"
        "        self.fetch()\n"
    )
    findings = _run(code, ["CH007"])
    assert len(findings) == 1
    assert findings[0].code == "CH007"


def test_ch007_ignores_returned_coroutine():
    code = (
        "async def fetch():\n"
        "    ...\n"
        "def f():\n"
        "    return fetch()\n"
    )
    assert _run(code, ["CH007"]) == []


def test_ch007_ignores_sync_twin_method_on_different_class():
    # Real false positive found in agno: ZepTools.initialize is sync,
    # ZepAsyncTools.initialize (a different class) is async - calling
    # self.initialize() from ZepTools must not match the unrelated twin.
    code = (
        "class ZepTools:\n"
        "    def __init__(self):\n"
        "        self.initialize()\n"
        "    def initialize(self):\n"
        "        ...\n"
        "class ZepAsyncTools:\n"
        "    async def initialize(self):\n"
        "        ...\n"
    )
    assert _run(code, ["CH007"]) == []


def test_ch007_ignores_name_shadowed_by_parameter():
    # Real false positive found in agno: an unrelated `async def write`
    # exists elsewhere in the file, but `write` here is a plain callable
    # parameter, not a reference to that function.
    code = (
        "def run_with_retry(write):\n"
        "    write()\n"
        "async def write():\n"
        "    ...\n"
    )
    assert _run(code, ["CH007"]) == []


# --- CH008 asyncio-run-in-running-loop ---------------------------------------------


def test_ch008_flags_asyncio_run_inside_async_def():
    code = (
        "import asyncio\n"
        "async def f():\n"
        "    asyncio.run(g())\n"
    )
    findings = _run(code, ["CH008"])
    assert len(findings) == 1
    assert findings[0].code == "CH008"


def test_ch008_ignores_asyncio_run_in_sync_function():
    code = (
        "import asyncio\n"
        "def main():\n"
        "    asyncio.run(g())\n"
    )
    assert _run(code, ["CH008"]) == []


def test_ch008_ignores_asyncio_run_in_nested_sync_function():
    # inner() is itself sync; whether calling it from a running loop is
    # safe depends on what thread it runs on, which this check can't know.
    code = (
        "import asyncio\n"
        "async def outer():\n"
        "    def inner():\n"
        "        asyncio.run(g())\n"
        "    inner()\n"
    )
    assert _run(code, ["CH008"]) == []


# --- CH009 floating-thread ----------------------------------------------------------


def test_ch009_flags_chained_start_with_no_reference():
    code = (
        "import threading\n"
        "def f():\n"
        "    threading.Thread(target=work).start()\n"
    )
    findings = _run(code, ["CH009"])
    assert len(findings) == 1
    assert findings[0].code == "CH009"


def test_ch009_ignores_chained_daemon_thread():
    code = (
        "import threading\n"
        "def f():\n"
        "    threading.Thread(target=work, daemon=True).start()\n"
    )
    assert _run(code, ["CH009"]) == []


def test_ch009_flags_assigned_thread_never_joined():
    code = (
        "import threading\n"
        "def f():\n"
        "    t = threading.Thread(target=work)\n"
        "    t.start()\n"
    )
    findings = _run(code, ["CH009"])
    assert len(findings) == 1
    assert findings[0].code == "CH009"


def test_ch009_ignores_assigned_thread_that_is_joined():
    code = (
        "import threading\n"
        "def f():\n"
        "    t = threading.Thread(target=work)\n"
        "    t.start()\n"
        "    t.join()\n"
    )
    assert _run(code, ["CH009"]) == []


def test_ch009_ignores_thread_returned_to_caller():
    code = (
        "import threading\n"
        "def f():\n"
        "    t = threading.Thread(target=work)\n"
        "    t.start()\n"
        "    return t\n"
    )
    assert _run(code, ["CH009"]) == []


def test_ch009_ignores_thread_handed_off_via_another_objects_attribute():
    # Real false positive found in llama_index: the thread is stashed on a
    # *different* object's attribute (not self), which is itself returned;
    # that object joins the thread later once its caller finishes with it.
    code = (
        "import threading\n"
        "def f():\n"
        "    response = ChatResponse()\n"
        "    t = threading.Thread(target=work)\n"
        "    response.write_response_to_history_thread = t\n"
        "    t.start()\n"
        "    return response\n"
    )
    assert _run(code, ["CH009"]) == []


def test_ch009_ignores_daemon_set_after_construction():
    code = (
        "import threading\n"
        "def f():\n"
        "    t = threading.Thread(target=work)\n"
        "    t.daemon = True\n"
        "    t.start()\n"
    )
    assert _run(code, ["CH009"]) == []


def test_ch009_ignores_thread_never_started():
    # Created but never run at all - not a "floating" thread, just inert.
    code = (
        "import threading\n"
        "def f():\n"
        "    t = threading.Thread(target=work)\n"
        "    return t.name\n"
    )
    assert _run(code, ["CH009"]) == []


# --- CH010 loop-closure-capture ------------------------------------------------------


def test_ch010_flags_lambda_capturing_loop_variable_in_list():
    code = "callbacks = []\nfor i in range(3):\n    callbacks.append(lambda: i)\n"
    findings = _run(code, ["CH010"])
    assert len(findings) == 1
    assert findings[0].code == "CH010"


def test_ch010_flags_lambda_in_list_comprehension():
    code = "callbacks = [lambda: i for i in range(3)]\n"
    findings = _run(code, ["CH010"])
    assert len(findings) == 1


def test_ch010_ignores_default_arg_capture():
    code = "callbacks = []\nfor i in range(3):\n    callbacks.append(lambda i=i: i)\n"
    assert _run(code, ["CH010"]) == []


def test_ch010_ignores_lambda_not_referencing_loop_var():
    code = "callbacks = []\nfor i in range(3):\n    callbacks.append(lambda: 42)\n"
    assert _run(code, ["CH010"]) == []


def test_ch010_ignores_immediately_invoked_lambda():
    code = "results = []\nfor i in range(3):\n    results.append((lambda: i)())\n"
    assert _run(code, ["CH010"]) == []


def test_ch010_ignores_lambda_passed_as_sort_key():
    # Real false positive found in marimo: sorted() calls the key function
    # immediately, synchronously, using the loop variable's *current* value
    # - nothing outlives the iteration, even though field is referenced.
    code = (
        "for sort_arg in by:\n"
        "    rows = sorted(rows, key=lambda row: row[sort_arg.by])\n"
    )
    assert _run(code, ["CH010"]) == []


def test_ch010_ignores_lambda_passed_to_filter():
    code = "for prefix in prefixes:\n    kept = list(filter(lambda x: x.startswith(prefix), items))\n"
    assert _run(code, ["CH010"]) == []


def test_ch010_still_flags_lambda_appended_even_when_named_like_a_key_fn():
    # Contrast case: same "lambda referencing loop var" shape, but this
    # time it really is stored (appended) rather than consumed on the spot.
    code = "keys = []\nfor field in fields:\n    keys.append(lambda row: row[field])\n"
    findings = _run(code, ["CH010"])
    assert len(findings) == 1

