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


def test_ch010_flags_nested_def_capturing_loop_variable():
    # Same bug as the lambda case, `def` instead - flake8-bugbear's B023
    # covers this shape too.
    code = (
        "callbacks = []\n"
        "for i in range(3):\n"
        "    def handler():\n"
        "        return i\n"
        "    callbacks.append(handler)\n"
    )
    findings = _run(code, ["CH010"])
    assert len(findings) == 1
    assert findings[0].code == "CH010"


def test_ch010_flags_nested_def_returned():
    code = (
        "def make_handlers():\n"
        "    handlers = []\n"
        "    for i in range(3):\n"
        "        def handler():\n"
        "            return i\n"
        "        handlers.append(handler)\n"
        "    return handlers\n"
    )
    findings = _run(code, ["CH010"])
    assert len(findings) == 1


def test_ch010_ignores_nested_def_shadowed_by_own_parameter():
    # def's own parameter `i` shadows the outer loop variable - the same
    # guard the lambda case already has for lambda i=i: i.
    code = (
        "callbacks = []\n"
        "for i in range(3):\n"
        "    def handler(i):\n"
        "        return i\n"
        "    callbacks.append(handler)\n"
    )
    assert _run(code, ["CH010"]) == []


def test_ch010_ignores_nested_def_not_referencing_loop_var():
    code = (
        "callbacks = []\n"
        "for i in range(3):\n"
        "    def handler():\n"
        "        return 42\n"
        "    callbacks.append(handler)\n"
    )
    assert _run(code, ["CH010"]) == []


def test_ch010_ignores_nested_def_never_stored():
    # Defined and called immediately within the same iteration - nothing
    # outlives the loop, same idea as the immediately-invoked lambda case.
    code = (
        "for i in range(3):\n"
        "    def handler():\n"
        "        return i\n"
        "    print(handler())\n"
    )
    assert _run(code, ["CH010"]) == []


# --- CH011 lru-cache-on-method ------------------------------------------------------


def test_ch011_flags_lru_cache_on_instance_method():
    code = (
        "from functools import lru_cache\n"
        "class C:\n"
        "    @lru_cache\n"
        "    def compute(self, x):\n"
        "        return x\n"
    )
    findings = _run(code, ["CH011"])
    assert len(findings) == 1
    assert findings[0].code == "CH011"


def test_ch011_flags_cache_decorator_call_form():
    code = (
        "import functools\n"
        "class C:\n"
        "    @functools.lru_cache(maxsize=128)\n"
        "    def compute(self, x):\n"
        "        return x\n"
    )
    assert len(_run(code, ["CH011"])) == 1


def test_ch011_ignores_lru_cache_on_module_level_function():
    code = "from functools import lru_cache\n@lru_cache\ndef compute(x):\n    return x\n"
    assert _run(code, ["CH011"]) == []


def test_ch011_ignores_lru_cache_on_staticmethod():
    code = (
        "from functools import lru_cache\n"
        "class C:\n"
        "    @staticmethod\n"
        "    @lru_cache\n"
        "    def compute(x):\n"
        "        return x\n"
    )
    assert _run(code, ["CH011"]) == []


def test_ch011_ignores_uncached_instance_method():
    code = "class C:\n    def compute(self, x):\n        return x\n"
    assert _run(code, ["CH011"]) == []


def test_ch011_ignores_frozen_dataclass():
    # A frozen dataclass is hashable and equal by field value, not identity -
    # verified empirically: two separately constructed instances with the
    # same field values hash equal, and lru_cache serves the second one
    # straight from the first's cache entry without ever storing it. Bounded
    # by maxsize the same way an equivalent free function cached by value
    # would be - not a leak.
    code = (
        "from dataclasses import dataclass\n"
        "from functools import lru_cache\n"
        "@dataclass(frozen=True)\n"
        "class Point:\n"
        "    x: int\n"
        "    @lru_cache\n"
        "    def scaled(self, factor):\n"
        "        return self.x * factor\n"
    )
    assert _run(code, ["CH011"]) == []


def test_ch011_ignores_frozen_pydantic_model():
    # Real false positive found in dspy: Image (model_config =
    # ConfigDict(frozen=True)) caches format() with @lru_cache(maxsize=32) -
    # confirmed via a REPL check that this is value-based memoization, not a
    # per-instance leak.
    code = (
        "import pydantic\n"
        "from functools import lru_cache\n"
        "class Image(pydantic.BaseModel):\n"
        "    url: str\n"
        "    model_config = pydantic.ConfigDict(frozen=True)\n"
        "    @lru_cache(maxsize=32)\n"
        "    def format(self):\n"
        "        return self.url.upper()\n"
    )
    assert _run(code, ["CH011"]) == []


def test_ch011_ignores_frozen_pydantic_model_v1_style_config():
    code = (
        "import pydantic\n"
        "from functools import lru_cache\n"
        "class Image(pydantic.BaseModel):\n"
        "    url: str\n"
        "    class Config:\n"
        "        frozen = True\n"
        "    @lru_cache\n"
        "    def format(self):\n"
        "        return self.url.upper()\n"
    )
    assert _run(code, ["CH011"]) == []


def test_ch011_still_flags_mutable_dataclass():
    # Guard against the frozen-class check over-suppressing: a plain (not
    # frozen) dataclass is not hashable by value, so this must still flag.
    code = (
        "from dataclasses import dataclass\n"
        "from functools import lru_cache\n"
        "@dataclass\n"
        "class Point:\n"
        "    x: int\n"
        "    @lru_cache\n"
        "    def scaled(self, factor):\n"
        "        return self.x * factor\n"
    )
    findings = _run(code, ["CH011"])
    assert len(findings) == 1
    assert findings[0].code == "CH011"


def test_ch011_still_flags_pydantic_model_without_frozen_config():
    code = (
        "import pydantic\n"
        "from functools import lru_cache\n"
        "class Image(pydantic.BaseModel):\n"
        "    url: str\n"
        "    @lru_cache\n"
        "    def format(self):\n"
        "        return self.url.upper()\n"
    )
    findings = _run(code, ["CH011"])
    assert len(findings) == 1
    assert findings[0].code == "CH011"


# --- CH012 floating-process ----------------------------------------------------------


def test_ch012_flags_chained_start_with_no_reference():
    code = "import multiprocessing\ndef f():\n    multiprocessing.Process(target=work).start()\n"
    findings = _run(code, ["CH012"])
    assert len(findings) == 1


def test_ch012_ignores_daemon_process():
    code = "import multiprocessing\ndef f():\n    multiprocessing.Process(target=work, daemon=True).start()\n"
    assert _run(code, ["CH012"]) == []


def test_ch012_flags_assigned_process_never_joined():
    code = (
        "import multiprocessing\n"
        "def f():\n"
        "    p = multiprocessing.Process(target=work)\n"
        "    p.start()\n"
    )
    findings = _run(code, ["CH012"])
    assert len(findings) == 1


def test_ch012_ignores_process_that_is_joined():
    code = (
        "import multiprocessing\n"
        "def f():\n"
        "    p = multiprocessing.Process(target=work)\n"
        "    p.start()\n"
        "    p.join()\n"
    )
    assert _run(code, ["CH012"]) == []


def test_ch012_ignores_process_returned_to_caller():
    code = (
        "import multiprocessing\n"
        "def f():\n"
        "    p = multiprocessing.Process(target=work)\n"
        "    p.start()\n"
        "    return p\n"
    )
    assert _run(code, ["CH012"]) == []


# --- CH013 discarded-future -----------------------------------------------------------


def test_ch013_flags_bare_submit_call():
    code = (
        "from concurrent.futures import ThreadPoolExecutor\n"
        "def f():\n"
        "    executor = ThreadPoolExecutor()\n"
        "    executor.submit(work)\n"
    )
    findings = _run(code, ["CH013"])
    assert len(findings) == 1
    assert findings[0].code == "CH013"


def test_ch013_flags_submit_inside_with_block():
    code = (
        "from concurrent.futures import ThreadPoolExecutor\n"
        "def f():\n"
        "    with ThreadPoolExecutor() as executor:\n"
        "        executor.submit(work)\n"
    )
    assert len(_run(code, ["CH013"])) == 1


def test_ch013_ignores_captured_future():
    code = (
        "from concurrent.futures import ThreadPoolExecutor\n"
        "def f():\n"
        "    executor = ThreadPoolExecutor()\n"
        "    future = executor.submit(work)\n"
        "    future.result()\n"
    )
    assert _run(code, ["CH013"]) == []


def test_ch013_ignores_submit_on_untracked_object():
    # `queue.submit(...)` where queue is some unrelated object with its own
    # submit method - not a tracked ThreadPoolExecutor/ProcessPoolExecutor.
    code = "def f():\n    queue.submit(work)\n"
    assert _run(code, ["CH013"]) == []


# --- CH014 unprotected-lock-acquire --------------------------------------------------


def test_ch014_flags_unguarded_acquire_release_pair():
    code = (
        "import threading\n"
        "lock = threading.Lock()\n"
        "def f():\n"
        "    lock.acquire()\n"
        "    do_work()\n"
        "    lock.release()\n"
    )
    findings = _run(code, ["CH014"])
    assert len(findings) == 1
    assert findings[0].code == "CH014"


def test_ch014_ignores_with_statement():
    code = (
        "import threading\n"
        "lock = threading.Lock()\n"
        "def f():\n"
        "    with lock:\n"
        "        do_work()\n"
    )
    assert _run(code, ["CH014"]) == []


def test_ch014_ignores_release_guarded_by_finally():
    code = (
        "import threading\n"
        "lock = threading.Lock()\n"
        "def f():\n"
        "    lock.acquire()\n"
        "    try:\n"
        "        do_work()\n"
        "    finally:\n"
        "        lock.release()\n"
    )
    assert _run(code, ["CH014"]) == []


def test_ch014_ignores_acquire_with_no_release_at_all():
    # Nothing to flag as "unprotected pairing" if there's no release to pair with
    # (a different bug, out of scope for this check).
    code = "import threading\nlock = threading.Lock()\ndef f():\n    lock.acquire()\n"
    assert _run(code, ["CH014"]) == []


# --- CH015 async-property -------------------------------------------------------------


def test_ch015_flags_async_def_property():
    code = "class C:\n    @property\n    async def value(self):\n        return 1\n"
    findings = _run(code, ["CH015"])
    assert len(findings) == 1
    assert findings[0].code == "CH015"


def test_ch015_ignores_sync_property():
    code = "class C:\n    @property\n    def value(self):\n        return 1\n"
    assert _run(code, ["CH015"]) == []


def test_ch015_ignores_plain_async_method():
    code = "class C:\n    async def value(self):\n        return 1\n"
    assert _run(code, ["CH015"]) == []


# --- CH016 unclosed-socket ------------------------------------------------------------


def test_ch016_flags_unclosed_socket():
    code = (
        "import socket\n"
        "def f():\n"
        "    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)\n"
        "    s.connect(('localhost', 80))\n"
        "    return s.recv(1024)\n"
    )
    findings = _run(code, ["CH016"])
    assert len(findings) == 1
    assert findings[0].code == "CH016"


def test_ch016_ignores_with_socket():
    code = (
        "import socket\n"
        "def f():\n"
        "    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:\n"
        "        return s.recv(1024)\n"
    )
    assert _run(code, ["CH016"]) == []


def test_ch016_ignores_explicit_close():
    code = (
        "import socket\n"
        "def f():\n"
        "    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)\n"
        "    data = s.recv(1024)\n"
        "    s.close()\n"
        "    return data\n"
    )
    assert _run(code, ["CH016"]) == []


def test_ch016_ignores_returned_socket():
    code = (
        "import socket\n"
        "def connect():\n"
        "    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)\n"
        "    return s\n"
    )
    assert _run(code, ["CH016"]) == []


def test_ch016_ignores_socket_returned_inside_a_tuple():
    # Real false positive found in vllm's distributed process-group setup:
    # `return port, s` hands the socket off to the caller just as much as a
    # bare `return s` does - it's just wrapped in a tuple alongside other data.
    code = (
        "import socket\n"
        "def bind():\n"
        "    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)\n"
        "    s.bind(('localhost', 0))\n"
        "    port = s.getsockname()[1]\n"
        "    return port, s\n"
    )
    assert _run(code, ["CH016"]) == []


def test_ch016_ignores_socket_appended_to_a_returned_list():
    # Real false positive found in vllm: sockets are collected into a list
    # inside a loop, and the list itself (not any individual socket name) is
    # returned - `socks.append(s)` is the hand-off.
    code = (
        "import socket\n"
        "def bind_group():\n"
        "    socks = []\n"
        "    for _ in range(3):\n"
        "        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)\n"
        "        s.bind(('localhost', 0))\n"
        "        socks.append(s)\n"
        "    return socks\n"
    )
    assert _run(code, ["CH016"]) == []


def test_ch016_ignores_socket_passed_as_call_argument():
    # Real false positive found in vllm: a listen socket is built, then
    # handed straight into another function that takes ownership of it
    # (`create_tcp_store(..., listen_socket=listen_socket)`), never returned
    # and never closed in this function because the callee owns it now.
    code = (
        "import socket\n"
        "def setup(host, port):\n"
        "    listen_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)\n"
        "    listen_socket.bind((host, port))\n"
        "    listen_socket.listen()\n"
        "    store = create_tcp_store(host, port, listen_socket=listen_socket)\n"
        "    return store\n"
    )
    assert _run(code, ["CH016"]) == []


def test_ch016_still_flags_socket_used_only_as_a_call_receiver():
    # Guard against the passed-as-argument escape swallowing real bugs:
    # `s.connect(...)`/`s.recv(...)` use `s` as the receiver of the call, not
    # as an argument, so this must still be flagged.
    code = (
        "import socket\n"
        "def f():\n"
        "    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)\n"
        "    s.connect(('localhost', 80))\n"
        "    data = s.recv(1024)\n"
        "    print(data)\n"
    )
    findings = _run(code, ["CH016"])
    assert len(findings) == 1
    assert findings[0].code == "CH016"


# --- CH017 collections-abc-import ----------------------------------------------------


def test_ch017_flags_direct_import_from_collections():
    code = "from collections import Mapping\n"
    findings = _run(code, ["CH017"])
    assert len(findings) == 1
    assert findings[0].code == "CH017"


def test_ch017_flags_attribute_access():
    code = "import collections\nx = collections.Mapping\n"
    assert len(_run(code, ["CH017"])) == 1


def test_ch017_ignores_correct_abc_import():
    code = "from collections.abc import Mapping\n"
    assert _run(code, ["CH017"]) == []


def test_ch017_ignores_non_abc_collections_members():
    code = "from collections import OrderedDict, defaultdict, deque, namedtuple, Counter\n"
    assert _run(code, ["CH017"]) == []


def test_ch017_ignores_qualified_collections_abc_attribute_access():
    code = "import collections.abc\nx = collections.abc.Mapping\n"
    assert _run(code, ["CH017"]) == []


# --- CH018 removed-asyncio-task-methods ------------------------------------------------


def test_ch018_flags_qualified_current_task():
    code = "import asyncio\nt = asyncio.Task.current_task()\n"
    findings = _run(code, ["CH018"])
    assert len(findings) == 1
    assert findings[0].code == "CH018"


def test_ch018_flags_all_tasks_when_task_imported_directly():
    code = "from asyncio import Task\nt = Task.all_tasks()\n"
    assert len(_run(code, ["CH018"])) == 1


def test_ch018_ignores_module_level_replacement():
    code = "import asyncio\nt = asyncio.current_task()\n"
    assert _run(code, ["CH018"]) == []


def test_ch018_ignores_unrelated_task_class_with_same_method_name():
    # `Task` here is never imported from asyncio - a false positive risk
    # this check specifically guards against (same lesson as CH007).
    code = "class Task:\n    @classmethod\n    def current_task(cls):\n        return None\nTask.current_task()\n"
    assert _run(code, ["CH018"]) == []


# --- CH019 removed-getargspec ----------------------------------------------------------


def test_ch019_flags_import():
    code = "from inspect import getargspec\n"
    findings = _run(code, ["CH019"])
    assert len(findings) == 1
    assert findings[0].code == "CH019"


def test_ch019_flags_qualified_call():
    code = "import inspect\ninspect.getargspec(f)\n"
    assert len(_run(code, ["CH019"])) == 1


def test_ch019_ignores_signature():
    code = "import inspect\ninspect.signature(f)\n"
    assert _run(code, ["CH019"]) == []


# --- CH020 bare-except ------------------------------------------------------------------


def test_ch020_flags_bare_except():
    code = "try:\n    risky()\nexcept:\n    pass\n"
    findings = _run(code, ["CH020"])
    assert len(findings) == 1
    assert findings[0].code == "CH020"


def test_ch020_flags_except_base_exception():
    code = "try:\n    risky()\nexcept BaseException:\n    pass\n"
    assert len(_run(code, ["CH020"])) == 1


def test_ch020_ignores_specific_exception():
    code = "try:\n    risky()\nexcept ValueError:\n    pass\n"
    assert _run(code, ["CH020"]) == []


def test_ch020_ignores_except_exception():
    # `except Exception:` is broad but does NOT catch KeyboardInterrupt/SystemExit
    # (they inherit from BaseException, not Exception) - a real, meaningful
    # distinction this check must not blur.
    code = "try:\n    risky()\nexcept Exception:\n    pass\n"
    assert _run(code, ["CH020"]) == []


def test_ch020_ignores_base_exception_that_is_captured_and_used():
    # Real false positive found in agno: a background-thread runner
    # deliberately catches BaseException (including Ctrl-C/SystemExit)
    # and reports it back to the consumer via a queue - not a silent
    # swallow, since the exception is captured and used.
    code = (
        "def f():\n"
        "    try:\n"
        "        risky()\n"
        "    except BaseException as e:\n"
        "        thread_error.append(e)\n"
    )
    assert _run(code, ["CH020"]) == []


def test_ch020_flags_base_exception_bound_but_unused():
    code = (
        "def f():\n"
        "    try:\n"
        "        risky()\n"
        "    except BaseException as e:\n"
        "        pass\n"
    )
    assert len(_run(code, ["CH020"])) == 1


def test_ch020_ignores_base_exception_with_no_name_that_reraises():
    # Real false positive found in agno: `except BaseException:` (no bound
    # name) that resets internal state then bare-`raise`s - properly
    # propagates the original error after cleanup, so nothing is swallowed.
    code = (
        "def f(self):\n"
        "    try:\n"
        "        risky()\n"
        "    except BaseException:\n"
        "        self._tools = None\n"
        "        raise\n"
    )
    assert _run(code, ["CH020"]) == []


def test_ch020_ignores_bare_except_that_reraises():
    code = "try:\n    risky()\nexcept:\n    cleanup()\n    raise\n"
    assert _run(code, ["CH020"]) == []


def test_ch020_flags_base_exception_with_raise_only_in_nested_handler():
    # The outer handler itself swallows - a `raise` inside a *nested*
    # try/except's own handler shouldn't count as the outer handler
    # re-raising anything.
    code = (
        "def f():\n"
        "    try:\n"
        "        risky()\n"
        "    except BaseException:\n"
        "        try:\n"
        "            cleanup()\n"
        "        except Exception:\n"
        "            raise\n"
    )
    assert len(_run(code, ["CH020"])) == 1


# --- CH021 removed-stdlib-module ------------------------------------------------------


def test_ch021_flags_distutils_import():
    findings = _run("import distutils\n", ["CH021"])
    assert len(findings) == 1
    assert findings[0].code == "CH021"


def test_ch021_flags_distutils_submodule_import():
    findings = _run("import distutils.core\n", ["CH021"])
    assert len(findings) == 1


def test_ch021_flags_distutils_from_import():
    code = "from distutils.core import setup\n"
    findings = _run(code, ["CH021"])
    assert len(findings) == 1


def test_ch021_flags_pep594_dead_battery_modules():
    for mod in ["cgi", "imghdr", "telnetlib", "nntplib", "asynchat", "asyncore", "imp"]:
        findings = _run(f"import {mod}\n", ["CH021"])
        assert len(findings) == 1, f"expected {mod} to be flagged"


def test_ch021_ignores_unrelated_modules():
    code = "import os\nimport sys\nfrom collections import OrderedDict\n"
    assert _run(code, ["CH021"]) == []


def test_ch021_ignores_similarly_named_local_module():
    # A module named e.g. `imp` in the removed set shouldn't false-positive
    # on an unrelated attribute/name access - only actual import statements.
    code = "imp = 5\nprint(imp)\n"
    assert _run(code, ["CH021"]) == []


def test_ch021_ignores_relative_import_of_same_named_local_module():
    # Real false positive found in vllm: `from .chunk import
    # chunk_gated_delta_rule` imports a local sibling module named
    # chunk.py, not the removed stdlib `chunk` module - `node.module` is
    # "chunk" either way, so only `node.level == 0` (absolute) tells them
    # apart.
    code = "from .chunk import chunk_gated_delta_rule\n"
    assert _run(code, ["CH021"]) == []


def test_ch021_ignores_import_guarded_by_import_error_handler():
    # Real false positive found in agno: `try: import imghdr except
    # ImportError: import filetype` explicitly anticipates and falls back
    # from the removal - already handled, not a bug waiting to happen.
    code = "try:\n    import imghdr\nexcept ImportError:\n    import filetype\n"
    assert _run(code, ["CH021"]) == []


def test_ch021_ignores_from_import_guarded_by_broad_except():
    code = "try:\n    from distutils.core import setup\nexcept Exception:\n    setup = None\n"
    assert _run(code, ["CH021"]) == []


def test_ch021_still_flags_import_in_try_with_unrelated_handler():
    # A try/except that doesn't actually catch ImportError provides no
    # real protection, so this must still be flagged.
    code = "try:\n    import distutils\nexcept ValueError:\n    pass\n"
    findings = _run(code, ["CH021"])
    assert len(findings) == 1


def test_ch021_still_flags_import_outside_any_try():
    code = "import distutils\ntry:\n    risky()\nexcept ImportError:\n    pass\n"
    findings = _run(code, ["CH021"])
    assert len(findings) == 1


# --- CH022 removed-asyncio-coroutine-decorator -----------------------------------------


def test_ch022_flags_asyncio_coroutine_decorator():
    code = "import asyncio\n@asyncio.coroutine\ndef f():\n    yield from g()\n"
    findings = _run(code, ["CH022"])
    assert len(findings) == 1
    assert findings[0].code == "CH022"


def test_ch022_flags_bare_coroutine_when_imported_from_asyncio():
    code = "from asyncio import coroutine\n@coroutine\ndef f():\n    yield from g()\n"
    findings = _run(code, ["CH022"])
    assert len(findings) == 1


def test_ch022_ignores_bare_coroutine_not_imported_from_asyncio():
    # Real name-collision guard, same shape as CH018's for `Task`: a
    # same-named decorator from somewhere else shouldn't be misidentified.
    code = "from mylib import coroutine\n@coroutine\ndef f():\n    return 1\n"
    assert _run(code, ["CH022"]) == []


def test_ch022_ignores_async_def_without_decorator():
    code = "async def f():\n    return 1\n"
    assert _run(code, ["CH022"]) == []


def test_ch022_ignores_unrelated_attribute_named_coroutine():
    code = "import asyncio\n@other.coroutine\ndef f():\n    return 1\n"
    assert _run(code, ["CH022"]) == []


# --- CH023 removed-stdlib-attribute ----------------------------------------------------


def test_ch023_flags_time_clock():
    findings = _run("import time\ntime.clock()\n", ["CH023"])
    assert len(findings) == 1
    assert findings[0].code == "CH023"


def test_ch023_flags_platform_linux_distribution_and_dist():
    code = "import platform\nplatform.linux_distribution()\nplatform.dist()\n"
    findings = _run(code, ["CH023"])
    assert len(findings) == 2


def test_ch023_flags_cgi_escape():
    findings = _run("import cgi\ncgi.escape(x)\n", ["CH023"])
    assert len(findings) == 1


def test_ch023_flags_base64_encodestring_decodestring():
    code = "import base64\nbase64.encodestring(x)\nbase64.decodestring(y)\n"
    findings = _run(code, ["CH023"])
    assert len(findings) == 2


def test_ch023_ignores_replacement_calls():
    code = "import time\ntime.perf_counter()\nimport base64\nbase64.encodebytes(x)\n"
    assert _run(code, ["CH023"]) == []


def test_ch023_ignores_unrelated_name_not_imported():
    # Real name-collision guard: an unrelated local object named `time`
    # with its own `.clock` attribute shouldn't be misidentified as the
    # stdlib module unless `time` was actually imported.
    code = "class Fake:\n    clock = 1\ntime = Fake()\nprint(time.clock)\n"
    assert _run(code, ["CH023"]) == []


# --- CH024 unittest-deprecated-alias ---------------------------------------------------


def test_ch024_flags_assert_equals():
    code = "class T:\n    def test_x(self):\n        self.assertEquals(1, 1)\n"
    findings = _run(code, ["CH024"])
    assert len(findings) == 1
    assert findings[0].code == "CH024"


def test_ch024_flags_fail_unless_raises():
    code = "class T:\n    def test_x(self):\n        self.failUnlessRaises(ValueError, f)\n"
    findings = _run(code, ["CH024"])
    assert len(findings) == 1


def test_ch024_ignores_modern_assert_equal():
    code = "class T:\n    def test_x(self):\n        self.assertEqual(1, 1)\n"
    assert _run(code, ["CH024"]) == []


# --- CH025 is-literal-comparison -------------------------------------------------------


def test_ch025_flags_is_comparison_with_int_literal():
    findings = _run("x = 1000\nif x is 1000:\n    pass\n", ["CH025"])
    assert len(findings) == 1
    assert findings[0].code == "CH025"


def test_ch025_flags_is_not_comparison_with_string_literal():
    code = "x = 'hello world'\nif x is not 'hello world':\n    pass\n"
    findings = _run(code, ["CH025"])
    assert len(findings) == 1


def test_ch025_ignores_is_none():
    code = "x = None\nif x is None:\n    pass\n"
    assert _run(code, ["CH025"]) == []


def test_ch025_ignores_is_true_and_is_false():
    code = "x = True\nif x is True:\n    pass\nif x is False:\n    pass\n"
    assert _run(code, ["CH025"]) == []


def test_ch025_ignores_equality_comparison():
    code = "x = 1000\nif x == 1000:\n    pass\n"
    assert _run(code, ["CH025"]) == []


def test_ch025_ignores_is_comparison_between_two_names():
    code = "if a is b:\n    pass\n"
    assert _run(code, ["CH025"]) == []


def test_ch025_ignores_chained_comparison_where_literal_pairs_with_different_op():
    # Real false positive found in litellm: `"usage" in response_obj is
    # not None` chains `in` and `is not` in one ast.Compare - the string
    # literal is the left side of `in`, not of `is not`, which is
    # comparing response_obj against the allowed singleton None. Each op
    # must be checked against only its own adjacent operands.
    code = "if 'usage' in response_obj is not None:\n    pass\n"
    assert _run(code, ["CH025"]) == []


def test_ch025_flags_literal_in_a_real_chained_is_comparison():
    # `a is 5 is b` is two adjacent pairs (a is 5) and (5 is b) - both
    # involve the literal, so both are correctly flagged individually.
    code = "if a is 5 is b:\n    pass\n"
    findings = _run(code, ["CH025"])
    assert len(findings) == 2


# --- CH026 mutable-class-attribute ------------------------------------------------------


def test_ch026_flags_class_level_list_mutated_via_self():
    code = (
        "class Handler:\n"
        "    listeners = []\n"
        "    def register(self, cb):\n"
        "        self.listeners.append(cb)\n"
    )
    findings = _run(code, ["CH026"])
    assert len(findings) == 1
    assert findings[0].code == "CH026"


def test_ch026_flags_class_level_dict_mutated_via_subscript():
    code = (
        "class Cache:\n"
        "    store = {}\n"
        "    def put(self, key, value):\n"
        "        self.store[key] = value\n"
    )
    findings = _run(code, ["CH026"])
    assert len(findings) == 1


def test_ch026_ignores_when_reassigned_per_instance_in_init():
    code = (
        "class Handler:\n"
        "    listeners = []\n"
        "    def __init__(self):\n"
        "        self.listeners = []\n"
        "    def register(self, cb):\n"
        "        self.listeners.append(cb)\n"
    )
    assert _run(code, ["CH026"]) == []


def test_ch026_ignores_class_attribute_never_mutated_in_place():
    code = (
        "class Config:\n"
        "    defaults = {}\n"
        "    def get(self, key):\n"
        "        return self.defaults.get(key)\n"
    )
    assert _run(code, ["CH026"]) == []


def test_ch026_ignores_immutable_class_level_default():
    code = "class C:\n    name = 'default'\n    def f(self):\n        return self.name\n"
    assert _run(code, ["CH026"]) == []


# --- CH027 unwaited-subprocess ----------------------------------------------------------


def test_ch027_flags_popen_never_waited():
    code = (
        "import subprocess\n"
        "def run():\n"
        "    p = subprocess.Popen(['ls'])\n"
        "    return p.pid\n"
    )
    findings = _run(code, ["CH027"])
    assert len(findings) == 1
    assert findings[0].code == "CH027"


def test_ch027_ignores_popen_with_context_manager():
    code = "import subprocess\ndef run():\n    with subprocess.Popen(['ls']) as p:\n        return p.pid\n"
    assert _run(code, ["CH027"]) == []


def test_ch027_ignores_popen_with_wait_call():
    code = "import subprocess\ndef run():\n    p = subprocess.Popen(['ls'])\n    p.wait()\n"
    assert _run(code, ["CH027"]) == []


def test_ch027_ignores_popen_with_communicate_call():
    code = "import subprocess\ndef run():\n    p = subprocess.Popen(['ls'])\n    p.communicate()\n"
    assert _run(code, ["CH027"]) == []


def test_ch027_ignores_popen_returned_to_caller():
    code = "import subprocess\ndef run():\n    p = subprocess.Popen(['ls'])\n    return p\n"
    assert _run(code, ["CH027"]) == []


def test_ch027_ignores_popen_passed_as_argument():
    code = (
        "import subprocess\n"
        "def run():\n"
        "    p = subprocess.Popen(['ls'])\n"
        "    register_process(p)\n"
    )
    assert _run(code, ["CH027"]) == []


def test_ch027_ignores_popen_stored_as_attribute():
    # Real pattern found in dspy: `lm.process = process` hands the Popen
    # off to a different object entirely, which reaps it later through a
    # separate terminate_process(lm.process) call elsewhere.
    code = (
        "import subprocess\n"
        "def run(lm):\n"
        "    process = subprocess.Popen(['ls'])\n"
        "    lm.process = process\n"
    )
    assert _run(code, ["CH027"]) == []


# --- CH028 floating-timer ----------------------------------------------------------------


def test_ch028_flags_chained_timer_start():
    code = "import threading\nthreading.Timer(30, callback).start()\n"
    findings = _run(code, ["CH028"])
    assert len(findings) == 1
    assert findings[0].code == "CH028"


def test_ch028_flags_assigned_timer_never_cancelled():
    code = (
        "import threading\n"
        "def schedule():\n"
        "    t = threading.Timer(30, callback)\n"
        "    t.start()\n"
    )
    findings = _run(code, ["CH028"])
    assert len(findings) == 1


def test_ch028_ignores_timer_that_is_cancelled():
    code = (
        "import threading\n"
        "def schedule():\n"
        "    t = threading.Timer(30, callback)\n"
        "    t.start()\n"
        "    t.cancel()\n"
    )
    assert _run(code, ["CH028"]) == []


def test_ch028_ignores_timer_returned_to_caller():
    code = (
        "import threading\n"
        "def schedule():\n"
        "    t = threading.Timer(30, callback)\n"
        "    t.start()\n"
        "    return t\n"
    )
    assert _run(code, ["CH028"]) == []


def test_ch028_ignores_timer_stored_as_attribute():
    code = (
        "import threading\n"
        "def schedule(obj):\n"
        "    t = threading.Timer(30, callback)\n"
        "    t.start()\n"
        "    obj.timer = t\n"
    )
    assert _run(code, ["CH028"]) == []


def test_ch028_ignores_unrelated_bare_timer_class():
    # Real false positive found in agno: its own stopwatch-style Timer
    # class (from agno.utils.timer import Timer), called as Timer() with
    # no arguments at all - threading.Timer requires interval and
    # function and would raise TypeError immediately if it were really
    # that class.
    code = "from mylib.timer import Timer\nt = Timer()\nt.start()\n"
    assert _run(code, ["CH028"]) == []


def test_ch028_flags_bare_timer_when_imported_from_threading():
    code = "from threading import Timer\nTimer(30, callback).start()\n"
    findings = _run(code, ["CH028"])
    assert len(findings) == 1


def test_ch028_ignores_daemon_true_kwarg_chained():
    code = "import threading\nthreading.Timer(30, callback, daemon=True).start()\n"
    assert _run(code, ["CH028"]) == []


def test_ch028_ignores_daemon_true_kwarg_assigned():
    code = (
        "import threading\n"
        "def schedule():\n"
        "    t = threading.Timer(30, callback, daemon=True)\n"
        "    t.start()\n"
    )
    assert _run(code, ["CH028"]) == []


def test_ch028_ignores_daemon_set_post_construction():
    # Real pattern found in weaviate-python-client: a watchdog timer
    # explicitly marked daemon=True after construction, a deliberate
    # "let this outlive the caller" choice, same escape CH009 recognizes.
    code = (
        "import threading\n"
        "def schedule():\n"
        "    t = threading.Timer(30, callback)\n"
        "    t.daemon = True\n"
        "    t.start()\n"
    )
    assert _run(code, ["CH028"]) == []


# --- CH029 finally-swallows-exception --------------------------------------------------


def test_ch029_flags_return_in_finally():
    code = "def f():\n    try:\n        raise ValueError()\n    finally:\n        return 5\n"
    findings = _run(code, ["CH029"])
    assert len(findings) == 1
    assert findings[0].code == "CH029"


def test_ch029_flags_break_escaping_finally():
    code = (
        "def f():\n"
        "    for i in range(3):\n"
        "        try:\n"
        "            raise ValueError()\n"
        "        finally:\n"
        "            break\n"
    )
    findings = _run(code, ["CH029"])
    assert len(findings) == 1


def test_ch029_flags_continue_escaping_finally():
    code = (
        "def f():\n"
        "    for i in range(3):\n"
        "        try:\n"
        "            raise ValueError()\n"
        "        finally:\n"
        "            continue\n"
    )
    findings = _run(code, ["CH029"])
    assert len(findings) == 1


def test_ch029_ignores_break_local_to_a_loop_inside_finally():
    # A break inside a loop that itself lives entirely within the
    # finally block is local to that loop and does not escape - the
    # pending exception still propagates correctly.
    code = (
        "def f():\n"
        "    try:\n"
        "        raise ValueError()\n"
        "    finally:\n"
        "        for i in range(1):\n"
        "            break\n"
    )
    assert _run(code, ["CH029"]) == []


def test_ch029_ignores_normal_finally_cleanup():
    code = (
        "def f():\n"
        "    try:\n"
        "        risky()\n"
        "    finally:\n"
        "        cleanup()\n"
    )
    assert _run(code, ["CH029"]) == []


def test_ch029_ignores_return_in_try_body():
    code = "def f():\n    try:\n        return 1\n    finally:\n        cleanup()\n"
    assert _run(code, ["CH029"]) == []


def test_ch029_ignores_return_in_nested_function_inside_finally():
    code = (
        "def f():\n"
        "    try:\n"
        "        raise ValueError()\n"
        "    finally:\n"
        "        def helper():\n"
        "            return 1\n"
        "        helper()\n"
    )
    assert _run(code, ["CH029"]) == []


def test_ch029_ignores_return_when_except_fully_absorbs_and_never_reraises():
    # Real pattern found in letta: except Exception logs and records the
    # error into a result dict, deliberately never re-raises (docstring:
    # "callback failures should not affect job completion") - by the
    # time finally runs, nothing is pending to swallow.
    code = (
        "def f():\n"
        "    result = {}\n"
        "    try:\n"
        "        risky()\n"
        "    except Exception as e:\n"
        "        result['error'] = str(e)\n"
        "    finally:\n"
        "        return result\n"
    )
    assert _run(code, ["CH029"]) == []


def test_ch029_still_flags_return_when_except_reraises():
    # Real pattern found in letta: the except handler logs, then
    # re-raises (or raises a wrapped error) - the finally's return still
    # discards that live, in-flight exception.
    code = (
        "def f():\n"
        "    try:\n"
        "        risky()\n"
        "    except Exception as e:\n"
        "        log(e)\n"
        "        raise\n"
        "    finally:\n"
        "        return None\n"
    )
    findings = _run(code, ["CH029"])
    assert len(findings) == 1


def test_ch029_still_flags_return_when_no_except_at_all():
    code = "def f():\n    try:\n        raise ValueError()\n    finally:\n        return 5\n"
    findings = _run(code, ["CH029"])
    assert len(findings) == 1


def test_ch029_still_flags_when_one_of_several_handlers_reraises():
    code = (
        "def f():\n"
        "    try:\n"
        "        risky()\n"
        "    except ValueError:\n"
        "        pass\n"
        "    except TypeError:\n"
        "        raise\n"
        "    finally:\n"
        "        return None\n"
    )
    findings = _run(code, ["CH029"])
    assert len(findings) == 1


# --- CH030 lru-cache-on-async-function --------------------------------------------------


def test_ch030_flags_lru_cache_on_module_level_async_function():
    code = "from functools import lru_cache\n@lru_cache\nasync def fetch(x):\n    return x\n"
    findings = _run(code, ["CH030"])
    assert len(findings) == 1
    assert findings[0].code == "CH030"


def test_ch030_flags_cache_decorator_call_form_on_async_method():
    code = (
        "import functools\n"
        "class C:\n"
        "    @functools.lru_cache(maxsize=128)\n"
        "    async def fetch(self, x):\n"
        "        return x\n"
    )
    findings = _run(code, ["CH030"])
    assert len(findings) == 1


def test_ch030_ignores_lru_cache_on_sync_function():
    code = "from functools import lru_cache\n@lru_cache\ndef compute(x):\n    return x\n"
    assert _run(code, ["CH030"]) == []


def test_ch030_ignores_uncached_async_function():
    code = "async def fetch(x):\n    return x\n"
    assert _run(code, ["CH030"]) == []


# --- CH031 unclosed-pool -----------------------------------------------------------------


def test_ch031_flags_pool_never_closed():
    code = (
        "import multiprocessing\n"
        "def run():\n"
        "    pool = multiprocessing.Pool(4)\n"
        "    pool.map(f, items)\n"
    )
    findings = _run(code, ["CH031"])
    assert len(findings) == 1
    assert findings[0].code == "CH031"


def test_ch031_ignores_pool_with_context_manager():
    code = (
        "import multiprocessing\n"
        "def run():\n"
        "    with multiprocessing.Pool(4) as pool:\n"
        "        pool.map(f, items)\n"
    )
    assert _run(code, ["CH031"]) == []


def test_ch031_ignores_pool_with_close_call():
    code = (
        "import multiprocessing\n"
        "def run():\n"
        "    pool = multiprocessing.Pool(4)\n"
        "    pool.map(f, items)\n"
        "    pool.close()\n"
        "    pool.join()\n"
    )
    assert _run(code, ["CH031"]) == []


def test_ch031_ignores_pool_with_terminate_call():
    code = (
        "import multiprocessing\n"
        "def run():\n"
        "    pool = multiprocessing.Pool(4)\n"
        "    pool.map(f, items)\n"
        "    pool.terminate()\n"
    )
    assert _run(code, ["CH031"]) == []


def test_ch031_ignores_pool_returned_to_caller():
    code = "import multiprocessing\ndef run():\n    pool = multiprocessing.Pool(4)\n    return pool\n"
    assert _run(code, ["CH031"]) == []


def test_ch031_ignores_pool_stored_as_attribute():
    code = (
        "import multiprocessing\n"
        "def run(obj):\n"
        "    pool = multiprocessing.Pool(4)\n"
        "    obj.pool = pool\n"
    )
    assert _run(code, ["CH031"]) == []


# --- CH032 nondeterministic-default-argument --------------------------------------------


def test_ch032_flags_time_time_default():
    code = "import time\ndef f(x=time.time()):\n    return x\n"
    findings = _run(code, ["CH032"])
    assert len(findings) == 1
    assert findings[0].code == "CH032"


def test_ch032_flags_datetime_now_default():
    code = "from datetime import datetime\ndef f(x=datetime.now()):\n    return x\n"
    findings = _run(code, ["CH032"])
    assert len(findings) == 1


def test_ch032_flags_random_default_on_lambda():
    code = "import random\nf = lambda x=random.random(): x\n"
    findings = _run(code, ["CH032"])
    assert len(findings) == 1


def test_ch032_flags_uuid4_keyword_only_default():
    code = "import uuid\ndef f(*, id=uuid.uuid4()):\n    return id\n"
    findings = _run(code, ["CH032"])
    assert len(findings) == 1


def test_ch032_ignores_none_default():
    code = "def f(x=None):\n    return x\n"
    assert _run(code, ["CH032"]) == []


def test_ch032_ignores_literal_default():
    code = "def f(x=10):\n    return x\n"
    assert _run(code, ["CH032"]) == []


def test_ch032_ignores_unrelated_call_default():
    code = "def f(x=get_default_timeout()):\n    return x\n"
    assert _run(code, ["CH032"]) == []


def test_ch032_ignores_module_constant_default():
    code = "import time\ndef f(x=time.sleep):\n    return x\n"
    assert _run(code, ["CH032"]) == []


# --- CH033 strip-multichar-argument ------------------------------------------------------


def test_ch033_flags_strip_with_multichar_string():
    code = "'report.txt'.strip('.txt')\n"
    findings = _run(code, ["CH033"])
    assert len(findings) == 1
    assert findings[0].code == "CH033"


def test_ch033_flags_lstrip_with_multichar_string():
    code = "'v1.2.3'.lstrip('v.')\n"
    findings = _run(code, ["CH033"])
    assert len(findings) == 1


def test_ch033_flags_rstrip_with_multichar_string():
    code = "'name.txt'.rstrip('.txt')\n"
    findings = _run(code, ["CH033"])
    assert len(findings) == 1


def test_ch033_ignores_single_char_argument():
    code = "'name,'.strip(',')\n"
    assert _run(code, ["CH033"]) == []


def test_ch033_ignores_strip_with_no_argument():
    code = "'  name  '.strip()\n"
    assert _run(code, ["CH033"]) == []


def test_ch033_ignores_non_string_variable_argument():
    code = "chars = build_chars()\n'name'.strip(chars)\n"
    assert _run(code, ["CH033"]) == []


def test_ch033_ignores_repeated_single_character():
    code = "'```sql```'.strip('```')\n"
    assert _run(code, ["CH033"]) == []


def test_ch033_ignores_bracket_or_quote_character_set():
    code = "'[1,2,3]'.strip('[]')\nline.rstrip('\\r\\n')\ns.strip('\\'\"')\n"
    assert _run(code, ["CH033"]) == []


def test_ch033_flags_argument_with_letters_even_with_punctuation():
    code = "url.strip('/v1')\n"
    findings = _run(code, ["CH033"])
    assert len(findings) == 1

