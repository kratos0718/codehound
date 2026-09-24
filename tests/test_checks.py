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


def test_ch005_ignores_deferred_close_via_bound_method():
    # Real pattern from CPython's lib2to3 pgen: the decision of *whether* to
    # close is made up front by extracting the bound method, independent of
    # *when* it's actually invoked.
    code = (
        "def f(filename, stream=None):\n"
        "    close_stream = None\n"
        "    if stream is None:\n"
        "        stream = open(filename)\n"
        "        close_stream = stream.close\n"
        "    data = stream.read()\n"
        "    if close_stream is not None:\n"
        "        close_stream()\n"
        "    return data\n"
    )
    assert _run(code, ["CH005"]) == []


def test_ch005_flags_bound_close_method_extracted_but_never_called():
    code = "def f(p):\n    fh = open(p)\n    closer = fh.close\n    return fh.read()\n"
    assert len(_run(code, ["CH005"])) == 1


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


def test_ch009_ignores_thread_appended_to_attribute_list():
    code = (
        "import threading\n"
        "class Supervisor:\n"
        "    def spawn(self):\n"
        "        t = threading.Thread(target=work)\n"
        "        t.start()\n"
        "        self.threads.append(t)\n"
        "    def join_all(self):\n"
        "        for t in self.threads:\n"
        "            t.join()\n"
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


def test_ch011_ignores_same_named_decorator_from_a_different_module():
    # Real false positive found in SQLAlchemy: dialect classes use
    # @reflection.cache on dozens of methods - same bare attribute name as
    # functools.cache, but it's SQLAlchemy's own decorator, only caches when
    # the caller passes an explicit info_cache dict, and doesn't retain self
    # anywhere the way functools.lru_cache's own persistent cache does.
    code = (
        "from myapp import reflection\n"
        "class Dialect:\n"
        "    @reflection.cache\n"
        "    def has_table(self, connection, table_name):\n"
        "        return True\n"
    )
    assert _run(code, ["CH011"]) == []


def test_ch011_ignores_bare_cache_name_not_imported_from_functools():
    code = (
        "class Dialect:\n"
        "    @cache\n"
        "    def has_table(self, connection, table_name):\n"
        "        return True\n"
    )
    assert _run(code, ["CH011"]) == []


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


def test_ch012_ignores_process_appended_to_attribute_list():
    # Real false positive found in uvicorn's multi-worker supervisor:
    # self.processes.append(process) right after .start(), with a separate
    # join_all() elsewhere in the class joining everything in self.processes.
    code = (
        "import multiprocessing\n"
        "class Supervisor:\n"
        "    def init_processes(self):\n"
        "        process = multiprocessing.Process(target=work)\n"
        "        process.start()\n"
        "        self.processes.append(process)\n"
        "    def join_all(self):\n"
        "        for process in self.processes:\n"
        "            process.join()\n"
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


def test_ch028_ignores_timer_appended_to_attribute_list():
    code = (
        "import threading\n"
        "class Supervisor:\n"
        "    def schedule(self):\n"
        "        t = threading.Timer(30, callback)\n"
        "        t.start()\n"
        "        self.timers.append(t)\n"
        "    def cancel_all(self):\n"
        "        for t in self.timers:\n"
        "            t.cancel()\n"
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


# --- CH034 raise-literal -----------------------------------------------------------------


def test_ch034_flags_raise_string_literal():
    code = "raise 'some error'\n"
    findings = _run(code, ["CH034"])
    assert len(findings) == 1
    assert findings[0].code == "CH034"


def test_ch034_flags_raise_fstring():
    code = "x = 1\nraise f'boom {x}'\n"
    findings = _run(code, ["CH034"])
    assert len(findings) == 1


def test_ch034_flags_raise_none():
    code = "raise None\n"
    findings = _run(code, ["CH034"])
    assert len(findings) == 1


def test_ch034_flags_raise_tuple_literal():
    code = "raise (1, 2)\n"
    findings = _run(code, ["CH034"])
    assert len(findings) == 1


def test_ch034_flags_raise_dict_literal():
    code = "raise {'error': 'bad'}\n"
    findings = _run(code, ["CH034"])
    assert len(findings) == 1


def test_ch034_ignores_raise_exception_instance():
    code = "raise ValueError('bad input')\n"
    assert _run(code, ["CH034"]) == []


def test_ch034_ignores_bare_reraise():
    code = "try:\n    pass\nexcept Exception:\n    raise\n"
    assert _run(code, ["CH034"]) == []


def test_ch034_ignores_raise_from_variable():
    code = "def f(exc):\n    raise exc\n"
    assert _run(code, ["CH034"]) == []


# --- CH035 empty-except-tuple -------------------------------------------------------------


def test_ch035_flags_empty_except_tuple():
    code = "try:\n    pass\nexcept ():\n    pass\n"
    findings = _run(code, ["CH035"])
    assert len(findings) == 1
    assert findings[0].code == "CH035"


def test_ch035_ignores_single_exception_type():
    code = "try:\n    pass\nexcept ValueError:\n    pass\n"
    assert _run(code, ["CH035"]) == []


def test_ch035_ignores_nonempty_exception_tuple():
    code = "try:\n    pass\nexcept (ValueError, TypeError):\n    pass\n"
    assert _run(code, ["CH035"]) == []


def test_ch035_ignores_bare_except():
    code = "try:\n    pass\nexcept:\n    pass\n"
    assert _run(code, ["CH035"]) == []


# --- CH036 environ-reassignment -----------------------------------------------------------


def test_ch036_flags_direct_environ_reassignment():
    code = "import os\nos.environ = {}\n"
    findings = _run(code, ["CH036"])
    assert len(findings) == 1
    assert findings[0].code == "CH036"


def test_ch036_flags_environ_reassignment_from_snapshot():
    code = "import os\nsaved = os.environ.copy()\nos.environ = saved\n"
    findings = _run(code, ["CH036"])
    assert len(findings) == 1


def test_ch036_ignores_environ_item_assignment():
    code = "import os\nos.environ['KEY'] = 'value'\n"
    assert _run(code, ["CH036"]) == []


def test_ch036_ignores_environ_clear():
    code = "import os\nos.environ.clear()\n"
    assert _run(code, ["CH036"]) == []


def test_ch036_ignores_environ_update():
    code = "import os\nos.environ.update({'KEY': 'value'})\n"
    assert _run(code, ["CH036"]) == []


def test_ch036_ignores_unrelated_attribute_named_environ():
    code = "config.environ = {}\n"
    assert _run(code, ["CH036"]) == []


# --- CH037 pointless-comparison-statement -------------------------------------------------


def test_ch037_flags_bare_equality_comparison():
    code = "x = 1\nx == 5\n"
    findings = _run(code, ["CH037"])
    assert len(findings) == 1
    assert findings[0].code == "CH037"


def test_ch037_flags_bare_is_comparison():
    code = "x = None\nx is None\n"
    findings = _run(code, ["CH037"])
    assert len(findings) == 1


def test_ch037_ignores_comparison_inside_assert():
    code = "x = 1\nassert x == 5\n"
    assert _run(code, ["CH037"]) == []


def test_ch037_ignores_comparison_inside_assignment():
    code = "x = 1\ny = (x == 5)\n"
    assert _run(code, ["CH037"]) == []


def test_ch037_ignores_comparison_inside_if():
    code = "x = 1\nif x == 5:\n    pass\n"
    assert _run(code, ["CH037"]) == []


# --- CH038 useless-expression-statement ---------------------------------------------------


def test_ch038_flags_bare_list_literal():
    code = "[1, 2, 3]\n"
    findings = _run(code, ["CH038"])
    assert len(findings) == 1
    assert findings[0].code == "CH038"


def test_ch038_flags_bare_int_literal():
    code = "42\n"
    findings = _run(code, ["CH038"])
    assert len(findings) == 1


def test_ch038_flags_bare_pure_builtin_call():
    code = "x = [1, 2]\nlen(x)\n"
    findings = _run(code, ["CH038"])
    assert len(findings) == 1


def test_ch038_ignores_string_literal_statement():
    code = "'this is used as an inline comment'\n"
    assert _run(code, ["CH038"]) == []


def test_ch038_ignores_docstring():
    code = "def f():\n    'docstring'\n    return 1\n"
    assert _run(code, ["CH038"]) == []


def test_ch038_ignores_validation_call_not_in_pure_list():
    code = "s = '5'\nint(s)\n"
    assert _run(code, ["CH038"]) == []


def test_ch038_ignores_regular_function_call():
    code = "def has_side_effect():\n    pass\n\nhas_side_effect()\n"
    assert _run(code, ["CH038"]) == []


def test_ch038_ignores_assigned_literal():
    code = "x = [1, 2, 3]\n"
    assert _run(code, ["CH038"]) == []


def test_ch038_ignores_tuple_of_calls_with_side_effects():
    code = "indices = [1, 2]\ntasks = [3, 4]\nindices.pop(0), tasks.pop(0)\n"
    assert _run(code, ["CH038"]) == []


def test_ch038_ignores_tuple_of_names_probing_existence():
    code = "try:\n    X, y\nexcept NameError:\n    X = 1\n    y = 2\n"
    assert _run(code, ["CH038"]) == []


def test_ch038_flags_tuple_of_pure_constants():
    code = "(1, 2, 3)\n"
    findings = _run(code, ["CH038"])
    assert len(findings) == 1


def test_ch038_ignores_shadowed_builtin_name():
    code = (
        "def run():\n"
        "    with Progress() as set:\n"
        "        set('Building...')\n"
    )
    assert _run(code, ["CH038"]) == []


def test_ch038_flags_unshadowed_pure_builtin():
    code = "x = [1, 2]\nlen(x)\n"
    findings = _run(code, ["CH038"])
    assert len(findings) == 1


def test_ch038_ignores_last_statement_in_notebook_cell_function():
    code = (
        "import marimo\n"
        "app = marimo.App()\n\n"
        "@app.cell\n"
        "def _(x):\n"
        "    [1, 2]\n"
    )
    assert _run(code, ["CH038"]) == []


def test_ch038_ignores_display_statement_right_before_trailing_return():
    code = (
        "import marimo\n"
        "app = marimo.App()\n\n"
        "@app.cell\n"
        "def _(x):\n"
        "    42\n"
        "    return x\n"
    )
    assert _run(code, ["CH038"]) == []


def test_ch038_flags_useless_statement_not_immediately_before_return():
    code = (
        "import marimo\n"
        "app = marimo.App()\n\n"
        "@app.cell\n"
        "def _(x):\n"
        "    42\n"
        "    y = x + 1\n"
        "    return y\n"
    )
    findings = _run(code, ["CH038"])
    assert len(findings) == 1


# --- CH039 lock-constructed-inline ---------------------------------------------------------


def test_ch039_flags_threading_lock_constructed_inline():
    code = "import threading\ndef f():\n    with threading.Lock():\n        pass\n"
    findings = _run(code, ["CH039"])
    assert len(findings) == 1
    assert findings[0].code == "CH039"


def test_ch039_flags_asyncio_lock_constructed_inline():
    code = "import asyncio\nasync def f():\n    async with asyncio.Lock():\n        pass\n"
    findings = _run(code, ["CH039"])
    assert len(findings) == 1


def test_ch039_flags_multiprocessing_lock_constructed_inline():
    code = "import multiprocessing\ndef f():\n    with multiprocessing.Lock():\n        pass\n"
    findings = _run(code, ["CH039"])
    assert len(findings) == 1


def test_ch039_ignores_lock_stored_as_attribute():
    code = (
        "import threading\n"
        "class C:\n"
        "    def __init__(self):\n"
        "        self.lock = threading.Lock()\n"
        "    def f(self):\n"
        "        with self.lock:\n"
        "            pass\n"
    )
    assert _run(code, ["CH039"]) == []


def test_ch039_ignores_lock_passed_as_variable():
    code = "def f(lock):\n    with lock:\n        pass\n"
    assert _run(code, ["CH039"]) == []


def test_ch039_ignores_unrelated_context_manager():
    code = "def f():\n    with open('x') as fh:\n        pass\n"
    assert _run(code, ["CH039"]) == []


# --- CH040 assert-raises-too-broad --------------------------------------------------------


def test_ch040_flags_pytest_raises_exception():
    code = "import pytest\ndef test_f():\n    with pytest.raises(Exception):\n        pass\n"
    findings = _run(code, ["CH040"])
    assert len(findings) == 1
    assert findings[0].code == "CH040"


def test_ch040_flags_assert_raises_base_exception():
    code = "class T:\n    def test_f(self):\n        with self.assertRaises(BaseException):\n            pass\n"
    findings = _run(code, ["CH040"])
    assert len(findings) == 1


def test_ch040_ignores_specific_exception_type():
    code = "import pytest\ndef test_f():\n    with pytest.raises(ValueError):\n        pass\n"
    assert _run(code, ["CH040"]) == []


def test_ch040_ignores_unrelated_with_statement():
    code = "def f():\n    with open('x') as fh:\n        pass\n"
    assert _run(code, ["CH040"]) == []


# --- CH041 suppress-empty ------------------------------------------------------------------


def test_ch041_flags_contextlib_suppress_empty():
    code = "import contextlib\ndef f():\n    with contextlib.suppress():\n        pass\n"
    findings = _run(code, ["CH041"])
    assert len(findings) == 1
    assert findings[0].code == "CH041"


def test_ch041_flags_bare_suppress_when_imported():
    code = "from contextlib import suppress\ndef f():\n    with suppress():\n        pass\n"
    findings = _run(code, ["CH041"])
    assert len(findings) == 1


def test_ch041_ignores_suppress_with_exception_type():
    code = "import contextlib\ndef f():\n    with contextlib.suppress(ValueError):\n        pass\n"
    assert _run(code, ["CH041"]) == []


def test_ch041_ignores_bare_suppress_not_imported():
    code = "def f():\n    with suppress():\n        pass\n"
    assert _run(code, ["CH041"]) == []


# --- CH042 duplicate-except-handler ---------------------------------------------------------


def test_ch042_flags_same_type_in_two_handlers():
    code = "try:\n    pass\nexcept ValueError:\n    pass\nexcept ValueError:\n    pass\n"
    findings = _run(code, ["CH042"])
    assert len(findings) == 1
    assert findings[0].code == "CH042"


def test_ch042_flags_duplicate_within_one_tuple():
    code = "try:\n    pass\nexcept (ValueError, ValueError):\n    pass\n"
    findings = _run(code, ["CH042"])
    assert len(findings) == 1


def test_ch042_ignores_different_exception_types():
    code = "try:\n    pass\nexcept ValueError:\n    pass\nexcept TypeError:\n    pass\n"
    assert _run(code, ["CH042"]) == []


# --- CH043 nan-equality-comparison -----------------------------------------------------------


def test_ch043_flags_equality_against_float_nan():
    code = "x = 1.0\nx == float('nan')\n"
    findings = _run(code, ["CH043"])
    assert len(findings) == 1
    assert findings[0].code == "CH043"


def test_ch043_flags_inequality_against_math_nan():
    code = "import math\nx = 1.0\nx != math.nan\n"
    findings = _run(code, ["CH043"])
    assert len(findings) == 1


def test_ch043_ignores_ordinary_float_comparison():
    code = "x = 1.0\nx == 2.0\n"
    assert _run(code, ["CH043"]) == []


def test_ch043_ignores_isnan_call():
    code = "import math\nx = 1.0\nmath.isnan(x)\n"
    assert _run(code, ["CH043"]) == []


# --- CH044 augassign-without-nonlocal --------------------------------------------------------


def test_ch044_flags_augassign_without_nonlocal():
    code = "def outer():\n    count = 0\n    def inc():\n        count += 1\n        return count\n    return inc()\n"
    findings = _run(code, ["CH044"])
    assert len(findings) == 1
    assert findings[0].code == "CH044"


def test_ch044_ignores_augassign_with_nonlocal():
    code = (
        "def outer():\n"
        "    count = 0\n"
        "    def inc():\n"
        "        nonlocal count\n"
        "        count += 1\n"
        "        return count\n"
        "    return inc()\n"
    )
    assert _run(code, ["CH044"]) == []


def test_ch044_ignores_augassign_on_parameter():
    code = "def outer():\n    def inc(count):\n        count += 1\n        return count\n    return inc(0)\n"
    assert _run(code, ["CH044"]) == []


def test_ch044_ignores_augassign_with_prior_local_assignment():
    code = (
        "def outer():\n"
        "    count = 0\n"
        "    def inc():\n"
        "        count = 5\n"
        "        count += 1\n"
        "        return count\n"
        "    return inc()\n"
    )
    assert _run(code, ["CH044"]) == []


def test_ch044_ignores_augassign_at_module_level_function():
    code = "count = 0\ndef inc():\n    count += 1\n    return count\n"
    assert _run(code, ["CH044"]) == []


# --- CH045 duplicate-dict-key -----------------------------------------------------------------


def test_ch045_flags_duplicate_string_key():
    code = "{'a': 1, 'b': 2, 'a': 3}\n"
    findings = _run(code, ["CH045"])
    assert len(findings) == 1
    assert findings[0].code == "CH045"


def test_ch045_flags_bool_int_collision():
    code = "{True: 1, 1: 2}\n"
    findings = _run(code, ["CH045"])
    assert len(findings) == 1


def test_ch045_ignores_distinct_keys():
    code = "{'a': 1, 'b': 2, 'c': 3}\n"
    assert _run(code, ["CH045"]) == []


def test_ch045_ignores_non_literal_keys():
    code = "x = 1\ny = 2\n{x: 'a', y: 'b'}\n"
    assert _run(code, ["CH045"]) == []


# --- CH046 duplicate-set-value ------------------------------------------------------------------


def test_ch046_flags_duplicate_int_value():
    code = "{1, 2, 2, 3}\n"
    findings = _run(code, ["CH046"])
    assert len(findings) == 1
    assert findings[0].code == "CH046"


def test_ch046_ignores_distinct_values():
    code = "{1, 2, 3}\n"
    assert _run(code, ["CH046"]) == []


# --- CH047 contextmanager-yield-unprotected ------------------------------------------------------


def test_ch047_flags_cleanup_after_bare_yield():
    code = (
        "import contextlib\n"
        "@contextlib.contextmanager\n"
        "def resource():\n"
        "    opened.append(1)\n"
        "    yield 'handle'\n"
        "    closed.append(1)\n"
    )
    findings = _run(code, ["CH047"])
    assert len(findings) == 1
    assert findings[0].code == "CH047"


def test_ch047_flags_cleanup_after_yield_inside_try_without_finally():
    code = (
        "import contextlib\n"
        "@contextlib.contextmanager\n"
        "def resource():\n"
        "    try:\n"
        "        opened.append(1)\n"
        "        yield 'handle'\n"
        "        closed.append(1)\n"
        "    except Exception:\n"
        "        raise\n"
    )
    findings = _run(code, ["CH047"])
    assert len(findings) == 1


def test_ch047_ignores_yield_wrapped_in_try_finally():
    code = (
        "import contextlib\n"
        "@contextlib.contextmanager\n"
        "def resource():\n"
        "    try:\n"
        "        opened.append(1)\n"
        "        yield 'handle'\n"
        "    finally:\n"
        "        closed.append(1)\n"
    )
    assert _run(code, ["CH047"]) == []


def test_ch047_ignores_yield_with_nothing_after():
    code = (
        "import contextlib\n"
        "@contextlib.contextmanager\n"
        "def resource():\n"
        "    opened.append(1)\n"
        "    yield 'handle'\n"
    )
    assert _run(code, ["CH047"]) == []


def test_ch047_ignores_plain_generator_function():
    code = "def gen():\n    yield 1\n    cleanup()\n"
    assert _run(code, ["CH047"]) == []


# --- CH048 assert-on-tuple ------------------------------------------------------------------------


def test_ch048_flags_assert_on_nonempty_tuple():
    code = "def check(x):\n    assert (x == 5, 'x should be 5')\n    return 'passed'\n"
    findings = _run(code, ["CH048"])
    assert len(findings) == 1
    assert findings[0].code == "CH048"


def test_ch048_ignores_assert_with_comma_message():
    code = "def check(x):\n    assert x == 5, 'x should be 5'\n    return 'passed'\n"
    assert _run(code, ["CH048"]) == []


def test_ch048_ignores_assert_on_empty_tuple():
    code = "def check():\n    assert ()\n"
    assert _run(code, ["CH048"]) == []


def test_ch048_ignores_plain_assert():
    code = "def check(x):\n    assert x == 5\n"
    assert _run(code, ["CH048"]) == []


# --- CH049 staticmethod-references-self -----------------------------------------------------------


def test_ch049_flags_staticmethod_referencing_self():
    code = "class C:\n    @staticmethod\n    def method(x):\n        return self.value + x\n"
    findings = _run(code, ["CH049"])
    assert len(findings) == 1
    assert findings[0].code == "CH049"


def test_ch049_flags_staticmethod_referencing_cls():
    code = "class C:\n    @staticmethod\n    def method():\n        return cls.value\n"
    findings = _run(code, ["CH049"])
    assert len(findings) == 1


def test_ch049_ignores_self_as_parameter_name():
    code = "class C:\n    @staticmethod\n    def method(self):\n        return self.value\n"
    assert _run(code, ["CH049"]) == []


def test_ch049_ignores_classmethod_referencing_cls():
    code = "class C:\n    @classmethod\n    def method(cls):\n        return cls.value\n"
    assert _run(code, ["CH049"]) == []


def test_ch049_ignores_instance_method_referencing_self():
    code = "class C:\n    def method(self):\n        return self.value\n"
    assert _run(code, ["CH049"]) == []


def test_ch049_ignores_nested_function_with_own_self_param():
    code = (
        "class C:\n"
        "    @staticmethod\n"
        "    def method(x):\n"
        "        def helper(self):\n"
        "            return self.value\n"
        "        return helper\n"
    )
    assert _run(code, ["CH049"]) == []


def test_ch049_ignores_self_reassigned_as_local_variable():
    code = (
        "class C:\n"
        "    @staticmethod\n"
        "    def create():\n"
        "        self = C.__new__(C)\n"
        "        self.value = 1\n"
        "        return self\n"
    )
    assert _run(code, ["CH049"]) == []


def test_ch049_ignores_cls_bound_by_comprehension_generator():
    code = (
        "class C:\n"
        "    @staticmethod\n"
        "    def method(items):\n"
        "        return {cls.__name__ for cls in items}\n"
    )
    assert _run(code, ["CH049"]) == []


def test_ch049_ignores_cls_assigned_as_ordinary_local():
    code = (
        "class C:\n"
        "    @staticmethod\n"
        "    def method(value):\n"
        "        cls = type(value)\n"
        "        return cls.__name__\n"
    )
    assert _run(code, ["CH049"]) == []


def test_ch049_ignores_self_in_decorator_expression():
    code = (
        "class T:\n"
        "    def test_it(self):\n"
        "        class Alpha:\n"
        "            @staticmethod\n"
        "            @self.app.task(shared=False)\n"
        "            def handler(x):\n"
        "                return x\n"
    )
    assert _run(code, ["CH049"]) == []


def test_ch049_ignores_locally_defined_class_closing_over_outer_self():
    code = (
        "class Outer:\n"
        "    def make(self):\n"
        "        class Inner:\n"
        "            @staticmethod\n"
        "            def helper():\n"
        "                return self.value\n"
        "        return Inner\n"
    )
    assert _run(code, ["CH049"]) == []


# --- CH050 static-dict-comprehension-key -------------------------------------------------------


def test_ch050_flags_key_not_referencing_loop_variable():
    code = "items = [1, 2, 3]\n{'result': item for item in items}\n"
    findings = _run(code, ["CH050"])
    assert len(findings) == 1
    assert findings[0].code == "CH050"


def test_ch050_flags_key_referencing_wrong_outer_variable():
    code = "other = 'x'\nitems = [1, 2, 3]\n{other: item for item in items}\n"
    findings = _run(code, ["CH050"])
    assert len(findings) == 1


def test_ch050_ignores_key_referencing_loop_variable():
    code = "items = [1, 2, 3]\n{item: item * 2 for item in items}\n"
    assert _run(code, ["CH050"]) == []


def test_ch050_ignores_key_referencing_unpacked_loop_variable():
    code = "pairs = [(1, 'a'), (2, 'b')]\n{k: v for k, v in pairs}\n"
    assert _run(code, ["CH050"]) == []


def test_ch050_ignores_key_with_function_call():
    code = "import uuid\nitems = [1, 2, 3]\n{uuid.uuid4(): item for item in items}\n"
    assert _run(code, ["CH050"]) == []


def test_ch050_ignores_key_with_walrus():
    code = "items = [1, 2, 3]\ni = 0\n{(i := i + 1): item for item in items}\n"
    assert _run(code, ["CH050"]) == []


def test_ch050_ignores_key_bound_by_walrus_in_if_clause():
    code = (
        "items = {'a': {'doc_hash': 'x'}, 'b': {'doc_hash': 'y'}}\n"
        "{doc_hash: doc_id for doc_id, doc in items.items() if (doc_hash := doc.get('doc_hash'))}\n"
    )
    assert _run(code, ["CH050"]) == []


# --- CH051 mutation-during-iteration ------------------------------------------------------


def test_ch051_flags_del_while_iterating_dict():
    code = "def f(d):\n    for key, value in d.items():\n        if value is None:\n            del d[key]\n"
    findings = _run(code, ["CH051"])
    assert len(findings) == 1
    assert findings[0].code == "CH051"


def test_ch051_flags_insert_new_key_while_iterating():
    code = "def f(d):\n    for k in d:\n        d['new'] = 1\n"
    assert len(_run(code, ["CH051"])) == 1


def test_ch051_flags_list_remove_while_iterating():
    code = "def f(lst):\n    for x in lst:\n        if x == 2:\n            lst.remove(x)\n"
    assert len(_run(code, ["CH051"])) == 1


def test_ch051_ignores_reassigning_the_loops_own_current_key():
    code = "def f(output):\n    for key, value in output.items():\n        output[key] = value\n"
    assert _run(code, ["CH051"]) == []


def test_ch051_ignores_reassigning_the_loops_own_key_by_literal():
    code = (
        "def f(schema):\n"
        "    for key, value in schema.items():\n"
        "        if key == '$ref':\n"
        "            schema['$ref'] = value\n"
        "        else:\n"
        "            schema[key] = value\n"
    )
    assert _run(code, ["CH051"]) == []


def test_ch051_ignores_mutation_immediately_followed_by_break():
    code = (
        "def f(state_dict):\n"
        "    for k in state_dict:\n"
        "        if 'old.' in k:\n"
        "            state_dict[k.replace('old.', 'new.')] = state_dict.pop(k)\n"
        "            break\n"
    )
    assert _run(code, ["CH051"]) == []


def test_ch051_ignores_list_append_while_iterating():
    code = "def f(candidates):\n    for c in candidates:\n        candidates.append(c)\n"
    assert _run(code, ["CH051"]) == []


def test_ch051_flags_set_add_while_iterating():
    code = "def f(s):\n    for x in s:\n        s.add(x)\n"
    assert len(_run(code, ["CH051"])) == 1


def test_ch051_ignores_mutation_of_a_different_collection():
    code = "def f(d, other):\n    for k in d:\n        other[k] = 1\n"
    assert _run(code, ["CH051"]) == []


# --- CH052 forwarded-without-unpacking ------------------------------------------------------


def test_ch052_flags_kwargs_forwarded_without_double_star():
    code = "def outer(*args, **kwargs):\n    inner(*args, kwargs)\n"
    findings = _run(code, ["CH052"])
    assert len(findings) == 1
    assert findings[0].code == "CH052"


def test_ch052_flags_args_forwarded_without_star():
    code = "def outer(*args, **kwargs):\n    inner(args, **kwargs)\n"
    assert len(_run(code, ["CH052"])) == 1


def test_ch052_ignores_lone_bare_name_with_no_other_unpacking():
    code = "def f(*args, **kwargs):\n    if len(args) == 2:\n        g(args)\n"
    assert _run(code, ["CH052"]) == []


def test_ch052_ignores_correctly_starred_forwarding():
    code = "def outer(*args, **kwargs):\n    inner(*args, **kwargs)\n"
    assert _run(code, ["CH052"]) == []


def test_ch052_ignores_dict_merge_idiom():
    code = "def f(*args, **kwargs):\n    g(*args, **dict(kwargs, **{'x': 1}))\n"
    assert _run(code, ["CH052"]) == []


# --- CH053 aliased-list-multiplication ------------------------------------------------------


def test_ch053_flags_2d_grid_aliasing_that_is_later_mutated():
    code = "def f(rows, cols):\n    grid = [[0] * cols] * rows\n    grid[0][0] = 99\n    return grid\n"
    findings = _run(code, ["CH053"])
    assert len(findings) == 1
    assert findings[0].code == "CH053"


def test_ch053_flags_repeated_dict_literal_that_is_later_mutated():
    code = "def f(n):\n    rows = [{}] * n\n    rows[0]['x'] = 1\n    return rows\n"
    assert len(_run(code, ["CH053"])) == 1


def test_ch053_ignores_repetition_never_indexed_and_mutated():
    code = "def f(batch_size, h, w):\n    grids = {}\n    grids['shape'] = [[h, w]] * batch_size\n    return grids\n"
    assert _run(code, ["CH053"]) == []


def test_ch053_ignores_immutable_element_repetition():
    code = "def f(n):\n    row = [0] * n\n    row[0] = 1\n    return row\n"
    assert _run(code, ["CH053"]) == []


# --- CH054 slots-blocks-dict ------------------------------------------------------


def test_ch054_flags_self_dict_access_with_slots():
    code = "class Foo:\n    __slots__ = ('x',)\n    def as_dict(self):\n        return self.__dict__\n"
    findings = _run(code, ["CH054"])
    assert len(findings) == 1
    assert findings[0].code == "CH054"


def test_ch054_flags_cached_property_with_slots():
    code = (
        "from functools import cached_property\n"
        "class Foo:\n"
        "    __slots__ = ('x',)\n"
        "    @cached_property\n"
        "    def doubled(self):\n"
        "        return self.x * 2\n"
    )
    assert len(_run(code, ["CH054"])) == 1


def test_ch054_ignores_slots_including_dict():
    code = "class Foo:\n    __slots__ = ('x', '__dict__')\n    def as_dict(self):\n        return self.__dict__\n"
    assert _run(code, ["CH054"]) == []


def test_ch054_ignores_class_with_a_custom_base():
    code = "class Foo(Base):\n    __slots__ = ('x',)\n    def as_dict(self):\n        return self.__dict__\n"
    assert _run(code, ["CH054"]) == []


def test_ch054_ignores_hasattr_guarded_dict_access():
    code = (
        "class Foo:\n"
        "    __slots__ = ()\n"
        "    def f(self):\n"
        "        if hasattr(self, '__dict__'):\n"
        "            return self.__dict__.keys()\n"
        "        return ()\n"
    )
    assert _run(code, ["CH054"]) == []


# --- CH055 duplicate-with-target ------------------------------------------------------


def test_ch055_flags_same_as_name_twice():
    code = "def f(a, b):\n    with open(a) as fh, open(b) as fh:\n        pass\n"
    findings = _run(code, ["CH055"])
    assert len(findings) == 1
    assert findings[0].code == "CH055"


def test_ch055_ignores_distinct_as_names():
    code = "def f(a, b):\n    with open(a) as f1, open(b) as f2:\n        pass\n"
    assert _run(code, ["CH055"]) == []


def test_ch055_ignores_single_context_manager():
    code = "def f(a):\n    with open(a) as fh:\n        pass\n"
    assert _run(code, ["CH055"]) == []


# --- CH056 path-absolute-literal-join ------------------------------------------------------


def test_ch056_flags_absolute_literal_joined_onto_path():
    code = "from pathlib import Path\np = Path('/etc/myapp') / '/passwd'\n"
    findings = _run(code, ["CH056"])
    assert len(findings) == 1
    assert findings[0].code == "CH056"


def test_ch056_ignores_relative_literal():
    code = "from pathlib import Path\np = Path('/etc/myapp') / 'config'\n"
    assert _run(code, ["CH056"]) == []


def test_ch056_ignores_non_path_division():
    code = "x = 10 / 2\n"
    assert _run(code, ["CH056"]) == []


# --- CH057 reused-exhausted-iterator ------------------------------------------------------


def test_ch057_flags_generator_consumed_twice():
    code = "def f():\n    gen = (x for x in range(5))\n    a = list(gen)\n    b = list(gen)\n    return a, b\n"
    findings = _run(code, ["CH057"])
    assert len(findings) == 1
    assert findings[0].code == "CH057"


def test_ch057_flags_map_consumed_twice():
    code = "def f():\n    m = map(str, range(3))\n    a = list(m)\n    b = list(m)\n    return a, b\n"
    assert len(_run(code, ["CH057"])) == 1


def test_ch057_ignores_reassignment_between_consumptions():
    code = (
        "def f():\n"
        "    gen = (x for x in range(5))\n"
        "    a = list(gen)\n"
        "    gen = (y for y in range(3))\n"
        "    b = list(gen)\n"
        "    return a, b\n"
    )
    assert _run(code, ["CH057"]) == []


def test_ch057_ignores_single_consumption():
    code = "def f():\n    gen = (x for x in range(5))\n    return list(gen)\n"
    assert _run(code, ["CH057"]) == []


# --- CH058 argparse-store-true-default ------------------------------------------------------


def test_ch058_flags_store_true_with_true_default():
    code = "p.add_argument('--flag', action='store_true', default=True)\n"
    findings = _run(code, ["CH058"])
    assert len(findings) == 1
    assert findings[0].code == "CH058"


def test_ch058_flags_store_false_with_false_default():
    code = "p.add_argument('--flag', action='store_false', default=False)\n"
    assert len(_run(code, ["CH058"])) == 1


def test_ch058_ignores_store_true_with_false_default():
    code = "p.add_argument('--flag', action='store_true', default=False)\n"
    assert _run(code, ["CH058"]) == []


def test_ch058_ignores_store_true_with_no_default():
    code = "p.add_argument('--flag', action='store_true')\n"
    assert _run(code, ["CH058"]) == []


# --- CH059 decorator-missing-return ------------------------------------------------------


def test_ch059_flags_wrapper_never_referenced_again():
    code = (
        "def my_decorator(func):\n"
        "    @functools.wraps(func)\n"
        "    def wrapper(*args, **kwargs):\n"
        "        return func(*args, **kwargs)\n"
    )
    findings = _run(code, ["CH059"])
    assert len(findings) == 1
    assert findings[0].code == "CH059"


def test_ch059_ignores_normal_return():
    code = (
        "def my_decorator(func):\n"
        "    @functools.wraps(func)\n"
        "    def wrapper(*args, **kwargs):\n"
        "        return func(*args, **kwargs)\n"
        "    return wrapper\n"
    )
    assert _run(code, ["CH059"]) == []


def test_ch059_ignores_ternary_return_between_two_wrapped_inners():
    code = (
        "def trace_method(trace_id):\n"
        "    def decorator(func):\n"
        "        @functools.wraps(func)\n"
        "        def wrapper(self, *args, **kwargs):\n"
        "            return func(self, *args, **kwargs)\n"
        "        @functools.wraps(func)\n"
        "        async def async_wrapper(self, *args, **kwargs):\n"
        "            return await func(self, *args, **kwargs)\n"
        "        return async_wrapper if inspect.iscoroutinefunction(func) else wrapper\n"
        "    return decorator\n"
    )
    assert _run(code, ["CH059"]) == []


def test_ch059_ignores_reassignment_to_another_name_then_return():
    code = (
        "def hook(func):\n"
        "    def decorator(f):\n"
        "        @wraps(f)\n"
        "        def sync_wrapper(*a, **k):\n"
        "            return f(*a, **k)\n"
        "        wrapper = sync_wrapper\n"
        "        return wrapper\n"
        "    return decorator\n"
    )
    assert _run(code, ["CH059"]) == []


def test_ch059_ignores_attribute_assignment_install():
    code = (
        "def wrap_init(cls):\n"
        "    @wraps(cls.__init__)\n"
        "    def __init__(self, *args, **kwargs):\n"
        "        pass\n"
        "    cls.__init__ = __init__\n"
        "    return cls\n"
    )
    assert _run(code, ["CH059"]) == []


def test_ch059_ignores_sibling_wrapped_helper_called_by_another_wrapper():
    code = (
        "def decorator(fn):\n"
        "    @wraps(fn)\n"
        "    def process_request(args, kwargs):\n"
        "        return {}\n"
        "    @wraps(fn)\n"
        "    def sync_wrapper(*args, **kwargs):\n"
        "        modified = process_request(args, kwargs)\n"
        "        return fn(*args, **kwargs)\n"
        "    return sync_wrapper\n"
    )
    assert _run(code, ["CH059"]) == []


# --- CH060 falsy-and-or-ternary ------------------------------------------------------


def test_ch060_flags_falsy_middle_value():
    code = "is_admin = True\nresult = is_admin and 0 or 'default'\n"
    findings = _run(code, ["CH060"])
    assert len(findings) == 1
    assert findings[0].code == "CH060"


def test_ch060_flags_empty_string_middle_value():
    code = "x = True\nresult = x and '' or 'fallback'\n"
    assert len(_run(code, ["CH060"])) == 1


def test_ch060_ignores_truthy_middle_value():
    code = "is_admin = True\nresult = is_admin and 1 or 'default'\n"
    assert _run(code, ["CH060"]) == []


def test_ch060_ignores_plain_or_without_and():
    code = "result = None or 'default'\n"
    assert _run(code, ["CH060"]) == []


# --- CH061 regex-backspace-escape ------------------------------------------------------


def test_ch061_flags_backspace_from_unraw_string():
    code = 'import re\nre.search("' + "\bword" + '", text)\n'
    findings = _run(code, ["CH061"])
    assert len(findings) == 1
    assert findings[0].code == "CH061"


def test_ch061_ignores_raw_string():
    code = "import re\nre.search(r'\\bword\\b', text)\n"
    assert _run(code, ["CH061"]) == []


def test_ch061_ignores_unrelated_builtin_compile():
    code = "compile('x=1', '<s>', 'exec')\n"
    assert _run(code, ["CH061"]) == []


def test_ch061_ignores_dotted_method_on_other_object():
    code = "obj.search(x)\n"
    assert _run(code, ["CH061"]) == []


# --- CH062 total-ordering-missing-eq ------------------------------------------------------


def test_ch062_flags_class_with_no_eq():
    code = (
        "import functools\n"
        "@functools.total_ordering\n"
        "class Money:\n"
        "    def __lt__(self, other):\n"
        "        return self.amount < other.amount\n"
    )
    findings = _run(code, ["CH062"])
    assert len(findings) == 1
    assert findings[0].code == "CH062"


def test_ch062_ignores_class_with_eq():
    code = (
        "import functools\n"
        "@functools.total_ordering\n"
        "class Money:\n"
        "    def __eq__(self, other):\n"
        "        return self.amount == other.amount\n"
        "    def __lt__(self, other):\n"
        "        return self.amount < other.amount\n"
    )
    assert _run(code, ["CH062"]) == []


def test_ch062_ignores_class_with_custom_base():
    code = (
        "import functools\n"
        "@functools.total_ordering\n"
        "class Money(Base):\n"
        "    def __lt__(self, other):\n"
        "        return self.amount < other.amount\n"
    )
    assert _run(code, ["CH062"]) == []


def test_ch062_ignores_undecorated_class():
    code = "class Money:\n    def __lt__(self, other):\n        return True\n"
    assert _run(code, ["CH062"]) == []


# --- CH063 unbounded-cycle-consumption ------------------------------------------------------


def test_ch063_flags_list_of_cycle():
    code = "import itertools\nlist(itertools.cycle([1, 2, 3]))\n"
    findings = _run(code, ["CH063"])
    assert len(findings) == 1
    assert findings[0].code == "CH063"


def test_ch063_flags_sum_of_cycle():
    code = "from itertools import cycle\nsum(cycle([1, 2, 3]))\n"
    assert len(_run(code, ["CH063"])) == 1


def test_ch063_ignores_islice_of_cycle():
    code = "import itertools\nlist(itertools.islice(itertools.cycle([1, 2, 3]), 10))\n"
    assert _run(code, ["CH063"]) == []


def test_ch063_ignores_list_of_plain_iterable():
    code = "list([1, 2, 3])\n"
    assert _run(code, ["CH063"]) == []


# --- CH064 asyncio-wait-bare-coroutine ------------------------------------------------------


def test_ch064_flags_bare_coroutine_in_wait_list():
    code = "import asyncio\nasync def f():\n    await asyncio.wait([g()])\n"
    findings = _run(code, ["CH064"])
    assert len(findings) == 1
    assert findings[0].code == "CH064"


def test_ch064_ignores_create_task_wrapped():
    code = "import asyncio\nasync def f():\n    await asyncio.wait([asyncio.create_task(g())])\n"
    assert _run(code, ["CH064"]) == []


def test_ch064_ignores_bare_name_reference():
    code = "import asyncio\nasync def f(tasks):\n    await asyncio.wait(tasks)\n"
    assert _run(code, ["CH064"]) == []


# --- CH065 dict-fromkeys-mutable-default ------------------------------------------------------


def test_ch065_flags_fromkeys_with_list_default():
    code = "d = dict.fromkeys(['a', 'b'], [])\n"
    findings = _run(code, ["CH065"])
    assert len(findings) == 1
    assert findings[0].code == "CH065"


def test_ch065_ignores_fromkeys_with_immutable_default():
    code = "d = dict.fromkeys(['a', 'b'], None)\n"
    assert _run(code, ["CH065"]) == []


def test_ch065_ignores_fromkeys_with_no_default():
    code = "d = dict.fromkeys(['a', 'b'])\n"
    assert _run(code, ["CH065"]) == []


# --- CH066 os-path-join-absolute-literal ------------------------------------------------------


def test_ch066_flags_absolute_literal_argument():
    code = "import os.path\nos.path.join('/etc/myapp', '/passwd')\n"
    findings = _run(code, ["CH066"])
    assert len(findings) == 1
    assert findings[0].code == "CH066"


def test_ch066_ignores_relative_literal_argument():
    code = "import os.path\nos.path.join('/etc/myapp', 'config')\n"
    assert _run(code, ["CH066"]) == []


def test_ch066_ignores_unrelated_join_call():
    code = "','.join(['a', '/b'])\n"
    assert _run(code, ["CH066"]) == []


# --- CH067 namedtuple-mutable-default ------------------------------------------------------


def test_ch067_flags_list_default_field():
    code = "from typing import NamedTuple\nclass Config(NamedTuple):\n    tags: list = []\n"
    findings = _run(code, ["CH067"])
    assert len(findings) == 1
    assert findings[0].code == "CH067"


def test_ch067_ignores_immutable_default_field():
    code = "from typing import NamedTuple\nclass Config(NamedTuple):\n    name: str = ''\n"
    assert _run(code, ["CH067"]) == []


def test_ch067_ignores_non_namedtuple_class():
    code = "class Config:\n    tags: list = []\n"
    assert _run(code, ["CH067"]) == []


# --- CH068 logging-extra-reserved-key ------------------------------------------------------


def test_ch068_flags_reserved_key_name():
    code = "import logging\nlogging.getLogger(__name__).warning('x', extra={'name': 'oops'})\n"
    findings = _run(code, ["CH068"])
    assert len(findings) == 1
    assert findings[0].code == "CH068"


def test_ch068_flags_reserved_key_message():
    code = "logger.info('x', extra={'message': 'oops'})\n"
    assert len(_run(code, ["CH068"])) == 1


def test_ch068_ignores_non_reserved_key():
    code = "logger.info('x', extra={'request_id': '123'})\n"
    assert _run(code, ["CH068"]) == []


def test_ch068_ignores_call_without_extra():
    code = "logger.info('x')\n"
    assert _run(code, ["CH068"]) == []


# --- CH069 contextvar-mutable-default ------------------------------------------------------


def test_ch069_flags_direct_mutation_on_get():
    code = (
        "from contextvars import ContextVar\n"
        "items_var = ContextVar('items', default=[])\n"
        "def add(x):\n"
        "    items_var.get().append(x)\n"
    )
    findings = _run(code, ["CH069"])
    assert len(findings) == 1
    assert findings[0].code == "CH069"


def test_ch069_ignores_copy_then_set():
    code = (
        "from contextvars import ContextVar\n"
        "items_var = ContextVar('items', default=[])\n"
        "def add(x):\n"
        "    current = items_var.get().copy()\n"
        "    current.append(x)\n"
        "    items_var.set(current)\n"
    )
    assert _run(code, ["CH069"]) == []


def test_ch069_ignores_read_only_usage():
    code = (
        "from contextvars import ContextVar\n"
        "headers_var = ContextVar('headers', default={})\n"
        "def get_header(k):\n"
        "    return headers_var.get().get(k)\n"
    )
    assert _run(code, ["CH069"]) == []


def test_ch069_ignores_immutable_default():
    code = "from contextvars import ContextVar\nvar = ContextVar('x', default=None)\n"
    assert _run(code, ["CH069"]) == []


# --- CH070 threading-local-mutable-class-attr ------------------------------------------------------


def test_ch070_flags_mutable_class_attr_on_threading_local():
    code = "import threading\nclass MyLocal(threading.local):\n    items = []\n"
    findings = _run(code, ["CH070"])
    assert len(findings) == 1
    assert findings[0].code == "CH070"


def test_ch070_ignores_mutable_class_attr_on_plain_class():
    code = "class Foo:\n    items = []\n"
    assert _run(code, ["CH070"]) == []


def test_ch070_ignores_immutable_class_attr_on_threading_local():
    code = "import threading\nclass MyLocal(threading.local):\n    name = 'default'\n"
    assert _run(code, ["CH070"]) == []


# --- CH071 weakref-to-ephemeral-object --------------------------------------------------------


def test_ch071_flags_weakref_to_inline_constructed_object():
    code = "import weakref\nclass Foo: pass\ndef make():\n    return weakref.ref(Foo())\n"
    findings = _run(code, ["CH071"])
    assert len(findings) == 1
    assert findings[0].code == "CH071"


def test_ch071_ignores_weakref_to_held_variable():
    code = "import weakref\nclass Foo: pass\ndef make():\n    obj = Foo()\n    return weakref.ref(obj)\n"
    assert _run(code, ["CH071"]) == []


def test_ch071_ignores_getter_like_call():
    code = "import weakref\nclass Registry:\n    def get_ref(self, key):\n        return weakref.ref(self._cache.get(key))\n"
    assert _run(code, ["CH071"]) == []


# --- CH072 itertools-tee-original-reused ------------------------------------------------------


def test_ch072_flags_original_iterated_after_tee():
    code = "import itertools\ndef f():\n    it = iter([1, 2, 3])\n    a, b = itertools.tee(it, 2)\n    next(it)\n"
    findings = _run(code, ["CH072"])
    assert len(findings) == 1
    assert findings[0].code == "CH072"


def test_ch072_ignores_tee_without_original_reuse():
    code = "import itertools\ndef f():\n    it = iter([1, 2, 3])\n    a, b = itertools.tee(it, 2)\n    return list(a), list(b)\n"
    assert _run(code, ["CH072"]) == []


# --- CH073 str-on-bytes ------------------------------------------------------------------------


def test_ch073_flags_str_on_bytes_literal():
    code = "def f():\n    return str(b'hello')\n"
    findings = _run(code, ["CH073"])
    assert len(findings) == 1
    assert findings[0].code == "CH073"


def test_ch073_flags_str_on_encode_result():
    code = "def f(x):\n    return str(x.encode('utf-8'))\n"
    findings = _run(code, ["CH073"])
    assert len(findings) == 1


def test_ch073_ignores_str_with_explicit_encoding():
    code = "def f(data):\n    return str(data, 'utf-8')\n"
    assert _run(code, ["CH073"]) == []


# --- CH074 empty-literal-sequence-crash -------------------------------------------------------


def test_ch074_flags_random_choice_on_empty_literal():
    code = "import random\ndef f():\n    return random.choice([])\n"
    findings = _run(code, ["CH074"])
    assert len(findings) == 1
    assert findings[0].code == "CH074"


def test_ch074_flags_max_without_default_on_empty_literal():
    code = "def f():\n    return max([])\n"
    findings = _run(code, ["CH074"])
    assert len(findings) == 1


def test_ch074_ignores_max_with_default():
    code = "def f():\n    return max([], default=0)\n"
    assert _run(code, ["CH074"]) == []


def test_ch074_ignores_random_choice_on_variable():
    code = "import random\ndef f(items):\n    return random.choice(items)\n"
    assert _run(code, ["CH074"]) == []


# --- CH075 repr-calls-str-recursion -----------------------------------------------------------


def test_ch075_flags_repr_calling_str_self_with_no_str_defined():
    code = "class Foo:\n    def __repr__(self):\n        return f'Foo({str(self)})'\n"
    findings = _run(code, ["CH075"])
    assert len(findings) == 1
    assert findings[0].code == "CH075"


def test_ch075_ignores_when_str_is_defined():
    code = "class Foo:\n    def __repr__(self):\n        return f'Foo({str(self)})'\n    def __str__(self):\n        return 'foo'\n"
    assert _run(code, ["CH075"]) == []


def test_ch075_ignores_class_with_base():
    code = "class PlainRepr(str):\n    def __repr__(self):\n        return str(self)\n"
    assert _run(code, ["CH075"]) == []


# --- CH076 duplicate-method-definition ---------------------------------------------------------


def test_ch076_flags_duplicate_method_definition():
    code = "class Foo:\n    def bar(self):\n        return 1\n    def bar(self):\n        return 2\n"
    findings = _run(code, ["CH076"])
    assert len(findings) == 1
    assert findings[0].code == "CH076"


def test_ch076_ignores_property_setter_pair():
    code = "class Foo:\n    @property\n    def x(self):\n        return self._x\n    @x.setter\n    def x(self, v):\n        self._x = v\n"
    assert _run(code, ["CH076"]) == []


def test_ch076_ignores_overload_pair():
    code = (
        "from typing import overload\n"
        "class Foo:\n"
        "    @overload\n"
        "    def f(self, x: int) -> int: ...\n"
        "    @overload\n"
        "    def f(self, x: str) -> str: ...\n"
        "    def f(self, x):\n        return x\n"
    )
    assert _run(code, ["CH076"]) == []


# --- CH077 abstractmethod-without-abc ----------------------------------------------------------


def test_ch077_flags_abstractmethod_with_no_base_no_abcmeta():
    code = "from abc import abstractmethod\nclass Foo:\n    @abstractmethod\n    def bar(self):\n        pass\n"
    findings = _run(code, ["CH077"])
    assert len(findings) == 1
    assert findings[0].code == "CH077"


def test_ch077_ignores_abcmeta_via_base():
    code = "from abc import ABC, abstractmethod\nclass Foo(ABC):\n    @abstractmethod\n    def bar(self):\n        pass\n"
    assert _run(code, ["CH077"]) == []


def test_ch077_ignores_abcmeta_via_metaclass_kwarg():
    code = (
        "from abc import ABCMeta, abstractmethod\n"
        "class Foo(metaclass=ABCMeta):\n"
        "    @abstractmethod\n    def bar(self):\n        pass\n"
    )
    assert _run(code, ["CH077"]) == []


def test_ch077_ignores_any_other_base():
    code = "from abc import abstractmethod\nclass Foo(SomeBase):\n    @abstractmethod\n    def bar(self):\n        pass\n"
    assert _run(code, ["CH077"]) == []


# --- CH078 frozen-dataclass-post-init-mutation ------------------------------------------------


def test_ch078_flags_self_assignment_in_post_init():
    code = (
        "from dataclasses import dataclass\n"
        "@dataclass(frozen=True)\n"
        "class Foo:\n"
        "    x: int\n"
        "    def __post_init__(self):\n        self.x = self.x * 2\n"
    )
    findings = _run(code, ["CH078"])
    assert len(findings) == 1
    assert findings[0].code == "CH078"


def test_ch078_ignores_object_setattr_workaround():
    code = (
        "from dataclasses import dataclass\n"
        "@dataclass(frozen=True)\n"
        "class Foo:\n"
        "    x: int\n"
        "    def __post_init__(self):\n        object.__setattr__(self, 'x', self.x * 2)\n"
    )
    assert _run(code, ["CH078"]) == []


def test_ch078_ignores_non_frozen_dataclass():
    code = (
        "from dataclasses import dataclass\n"
        "@dataclass\n"
        "class Foo:\n"
        "    x: int\n"
        "    def __post_init__(self):\n        self.x = self.x * 2\n"
    )
    assert _run(code, ["CH078"]) == []


# --- CH079 dataclass-non-default-after-default ------------------------------------------------


def test_ch079_flags_required_field_after_default_field():
    code = "from dataclasses import dataclass\n@dataclass\nclass Foo:\n    x: int = 0\n    y: int\n"
    findings = _run(code, ["CH079"])
    assert len(findings) == 1
    assert findings[0].code == "CH079"


def test_ch079_ignores_correct_field_order():
    code = "from dataclasses import dataclass\n@dataclass\nclass Foo:\n    x: int\n    y: int = 0\n"
    assert _run(code, ["CH079"]) == []


def test_ch079_ignores_class_level_kw_only():
    code = "from dataclasses import dataclass\n@dataclass(kw_only=True)\nclass Foo:\n    x: int = 0\n    y: int\n"
    assert _run(code, ["CH079"]) == []


def test_ch079_ignores_field_init_false():
    code = (
        "from dataclasses import dataclass, field\n"
        "@dataclass\nclass Foo:\n"
        "    x: int = 0\n"
        "    y: int = field(init=False)\n"
    )
    assert _run(code, ["CH079"]) == []


def test_ch079_ignores_classvar_field():
    code = (
        "from dataclasses import dataclass\n"
        "from typing import ClassVar\n"
        "@dataclass\nclass Foo:\n"
        "    x: int = 0\n"
        "    y: ClassVar[str]\n"
    )
    assert _run(code, ["CH079"]) == []


def test_ch079_ignores_after_kw_only_sentinel():
    code = (
        "from dataclasses import dataclass, KW_ONLY\n"
        "@dataclass\nclass Foo:\n"
        "    x: int = 0\n"
        "    _: KW_ONLY\n"
        "    y: int\n"
    )
    assert _run(code, ["CH079"]) == []


# --- CH080 namedtuple-non-default-after-default -----------------------------------------------


def test_ch080_flags_required_field_after_default_field():
    code = "from typing import NamedTuple\nclass Foo(NamedTuple):\n    x: int = 0\n    y: int\n"
    findings = _run(code, ["CH080"])
    assert len(findings) == 1
    assert findings[0].code == "CH080"


def test_ch080_ignores_correct_field_order():
    code = "from typing import NamedTuple\nclass Foo(NamedTuple):\n    x: int\n    y: int = 0\n"
    assert _run(code, ["CH080"]) == []


# --- CH081 slots-conflicts-class-variable ------------------------------------------------------


def test_ch081_flags_slot_name_with_class_level_value():
    code = "class Foo:\n    __slots__ = ('x',)\n    x = 5\n"
    findings = _run(code, ["CH081"])
    assert len(findings) == 1
    assert findings[0].code == "CH081"


def test_ch081_ignores_bare_annotation_no_value():
    code = "class Foo:\n    __slots__ = ('x',)\n    x: int\n"
    assert _run(code, ["CH081"]) == []


def test_ch081_ignores_custom_metaclass():
    code = "class Meta(type): pass\nclass Foo(metaclass=Meta):\n    __slots__ = ('x',)\n    x = 5\n"
    assert _run(code, ["CH081"]) == []


def test_ch081_flags_slot_name_with_method():
    code = "class Foo:\n    __slots__ = ('x',)\n    def x(self):\n        return 5\n"
    findings = _run(code, ["CH081"])
    assert len(findings) == 1
    assert findings[0].code == "CH081"


def test_ch081_flags_slot_name_with_property():
    code = "class Foo:\n    __slots__ = ('x',)\n    @property\n    def x(self):\n        return 5\n"
    findings = _run(code, ["CH081"])
    assert len(findings) == 1
    assert findings[0].code == "CH081"


# --- CH082 python2-removed-dunder ---------------------------------------------------------------


def test_ch082_flags_nonzero_dunder():
    code = "class Foo:\n    def __nonzero__(self):\n        return False\n"
    findings = _run(code, ["CH082"])
    assert len(findings) == 1
    assert findings[0].code == "CH082"


def test_ch082_flags_unicode_dunder():
    code = "class Foo:\n    def __unicode__(self):\n        return 'text'\n"
    findings = _run(code, ["CH082"])
    assert len(findings) == 1


def test_ch082_ignores_correct_py3_dunders():
    code = "class Foo:\n    def __bool__(self):\n        return False\n    def __str__(self):\n        return 'text'\n"
    assert _run(code, ["CH082"]) == []


# --- CH083 json-dumps-datetime ------------------------------------------------------------------


def test_ch083_flags_json_dumps_datetime_now():
    code = "import json, datetime\ndef f():\n    return json.dumps(datetime.datetime.now())\n"
    findings = _run(code, ["CH083"])
    assert len(findings) == 1
    assert findings[0].code == "CH083"


def test_ch083_ignores_json_dumps_with_default():
    code = "import json, datetime\ndef f():\n    return json.dumps(datetime.datetime.now(), default=str)\n"
    assert _run(code, ["CH083"]) == []


def test_ch083_ignores_json_dumps_on_plain_value():
    code = "import json\ndef f(x):\n    return json.dumps(x)\n"
    assert _run(code, ["CH083"]) == []


# --- CH084 defaultdict-read-creates-key ---------------------------------------------------------


def test_ch084_flags_bare_subscript_in_if_test():
    code = "from collections import defaultdict\ndef f():\n    d = defaultdict(list)\n    if d['k']:\n        pass\n"
    findings = _run(code, ["CH084"])
    assert len(findings) == 1
    assert findings[0].code == "CH084"


def test_ch084_ignores_get_based_check():
    code = "from collections import defaultdict\ndef f():\n    d = defaultdict(list)\n    if d.get('k'):\n        pass\n"
    assert _run(code, ["CH084"]) == []


def test_ch084_ignores_in_based_check():
    code = "from collections import defaultdict\ndef f():\n    d = defaultdict(list)\n    if 'k' in d:\n        pass\n"
    assert _run(code, ["CH084"]) == []


# --- CH085 decorator-missing-functools-wraps ----------------------------------------------------


def test_ch085_flags_wrapper_missing_wraps():
    code = (
        "def deco(func):\n"
        "    def wrapper(*args, **kwargs):\n"
        "        return func(*args, **kwargs)\n"
        "    return wrapper\n"
    )
    findings = _run(code, ["CH085"])
    assert len(findings) == 1
    assert findings[0].code == "CH085"


def test_ch085_ignores_wrapper_with_wraps():
    code = (
        "import functools\n"
        "def deco(func):\n"
        "    @functools.wraps(func)\n"
        "    def wrapper(*args, **kwargs):\n"
        "        return func(*args, **kwargs)\n"
        "    return wrapper\n"
    )
    assert _run(code, ["CH085"]) == []


def test_ch085_ignores_manual_name_assignment():
    code = (
        "def deco(func):\n"
        "    def wrapper(*args, **kwargs):\n"
        "        return func(*args, **kwargs)\n"
        "    wrapper.__name__ = func.__name__\n"
        "    return wrapper\n"
    )
    assert _run(code, ["CH085"]) == []


def test_ch085_ignores_update_wrapper_call():
    code = (
        "import functools\n"
        "def deco(func):\n"
        "    def wrapper(*args, **kwargs):\n"
        "        return func(*args, **kwargs)\n"
        "    return functools.update_wrapper(wrapper, func)\n"
    )
    assert _run(code, ["CH085"]) == []


def test_ch085_ignores_non_passthrough_helper():
    code = (
        "def make_counter(encode_length, chunk_size=10):\n"
        "    def count_tokens(text):\n"
        "        return sum(encode_length(text[i:i + chunk_size]) for i in range(0, len(text), chunk_size))\n"
        "    return count_tokens\n"
    )
    assert _run(code, ["CH085"]) == []


def test_ch085_ignores_non_first_param_call():
    code = (
        "def make_validator(env_name, choices):\n"
        "    def get():\n"
        "        return choices()\n"
        "    return get\n"
    )
    assert _run(code, ["CH085"]) == []


# --- CH086 deepcopy-self-with-lock ---------------------------------------------------------------


def test_ch086_flags_deepcopy_self_with_lock_attr():
    code = (
        "import copy, threading\n"
        "class Foo:\n"
        "    def __init__(self):\n        self.lock = threading.Lock()\n"
        "    def clone(self):\n        return copy.deepcopy(self)\n"
    )
    findings = _run(code, ["CH086"])
    assert len(findings) == 1
    assert findings[0].code == "CH086"


def test_ch086_ignores_deepcopy_without_lock_attr():
    code = (
        "import copy\n"
        "class Foo:\n"
        "    def __init__(self):\n        self.x = 1\n"
        "    def clone(self):\n        return copy.deepcopy(self)\n"
    )
    assert _run(code, ["CH086"]) == []


# --- CH087 enumerate-start-offset-reindex ---------------------------------------------------------


def test_ch087_flags_reindex_with_offset_counter():
    code = "def f(items):\n    for i, item in enumerate(items, start=1):\n        print(items[i])\n"
    findings = _run(code, ["CH087"])
    assert len(findings) == 1
    assert findings[0].code == "CH087"


def test_ch087_ignores_default_start_zero():
    code = "def f(items):\n    for i, item in enumerate(items):\n        print(items[i])\n"
    assert _run(code, ["CH087"]) == []


def test_ch087_ignores_using_item_not_index():
    code = "def f(items):\n    for i, item in enumerate(items, start=1):\n        print(item)\n"
    assert _run(code, ["CH087"]) == []


# --- CH088 regex-flags-passed-as-count -------------------------------------------------------------


def test_ch088_flags_flag_passed_positionally_to_sub():
    code = "import re\ndef f(text):\n    return re.sub('a', 'b', text, re.IGNORECASE)\n"
    findings = _run(code, ["CH088"])
    assert len(findings) == 1
    assert findings[0].code == "CH088"


def test_ch088_flags_flag_passed_positionally_to_split():
    code = "import re\ndef f(text):\n    return re.split('a', text, re.IGNORECASE)\n"
    findings = _run(code, ["CH088"])
    assert len(findings) == 1


def test_ch088_ignores_flags_keyword():
    code = "import re\ndef f(text):\n    return re.sub('a', 'b', text, flags=re.IGNORECASE)\n"
    assert _run(code, ["CH088"]) == []


def test_ch088_ignores_explicit_count_int():
    code = "import re\ndef f(text):\n    return re.sub('a', 'b', text, 2)\n"
    assert _run(code, ["CH088"]) == []


# --- CH089 bytes-str-join-mismatch --------------------------------------------------------------


def test_ch089_flags_str_join_on_bytes_list():
    code = "def f():\n    return ', '.join([b'a', b'b'])\n"
    findings = _run(code, ["CH089"])
    assert len(findings) == 1
    assert findings[0].code == "CH089"


def test_ch089_flags_bytes_join_on_str_list():
    code = "def f():\n    return b', '.join(['a', 'b'])\n"
    findings = _run(code, ["CH089"])
    assert len(findings) == 1


def test_ch089_ignores_matching_types():
    code = "def f():\n    return ', '.join(['a', 'b'])\n"
    assert _run(code, ["CH089"]) == []


# --- CH090 exit-returns-true-unconditionally ----------------------------------------------------


def test_ch090_flags_exit_always_returns_true():
    code = (
        "class CM:\n"
        "    def __enter__(self):\n        return self\n"
        "    def __exit__(self, exc_type, exc_val, exc_tb):\n"
        "        print('cleanup')\n        return True\n"
    )
    findings = _run(code, ["CH090"])
    assert len(findings) == 1
    assert findings[0].code == "CH090"


def test_ch090_ignores_conditional_suppression():
    code = (
        "class CM:\n"
        "    def __exit__(self, exc_type, exc_val, exc_tb):\n"
        "        if exc_type is ValueError:\n            return True\n"
        "        return False\n"
    )
    assert _run(code, ["CH090"]) == []


def test_ch090_ignores_returns_false():
    code = "class CM:\n    def __exit__(self, exc_type, exc_val, exc_tb):\n        return False\n"
    assert _run(code, ["CH090"]) == []


# --- CH091 hash-eq-field-mismatch -----------------------------------------------------------------


def test_ch091_flags_hash_using_field_not_in_eq():
    code = (
        "class Bad:\n"
        "    def __init__(self, a, b):\n        self.a = a\n        self.b = b\n"
        "    def __eq__(self, other):\n        return self.a == other.a\n"
        "    def __hash__(self):\n        return hash((self.a, self.b))\n"
    )
    findings = _run(code, ["CH091"])
    assert len(findings) == 1
    assert findings[0].code == "CH091"


def test_ch091_ignores_matching_fields():
    code = (
        "class Good:\n"
        "    def __init__(self, a, b):\n        self.a = a\n        self.b = b\n"
        "    def __eq__(self, other):\n        return self.a == other.a and self.b == other.b\n"
        "    def __hash__(self):\n        return hash((self.a, self.b))\n"
    )
    assert _run(code, ["CH091"]) == []


def test_ch091_ignores_tuple_comparison_shape():
    code = (
        "class Good:\n"
        "    def __init__(self, a, b):\n        self.a = a\n        self.b = b\n"
        "    def __eq__(self, other):\n        return (self.a, self.b) == (other.a, other.b)\n"
        "    def __hash__(self):\n        return hash((self.a, self.b))\n"
    )
    assert _run(code, ["CH091"]) == []


def test_ch091_ignores_hash_using_a_method_call():
    code = (
        "class Good:\n"
        "    def __eq__(self, other):\n        return self.a == other.a\n"
        "    def __hash__(self):\n        return hash(self.to_json())\n"
    )
    assert _run(code, ["CH091"]) == []


def test_ch091_ignores_dict_equality():
    code = (
        "class Good:\n"
        "    def __eq__(self, other):\n        return self.__dict__ == other.__dict__\n"
        "    def __hash__(self):\n        return hash((self.a, self.b))\n"
    )
    assert _run(code, ["CH091"]) == []


# --- CH092 path-write-type-mismatch ---------------------------------------------------------------


def test_ch092_flags_write_text_with_bytes():
    code = "def f(p):\n    return p.write_text(b'hello')\n"
    findings = _run(code, ["CH092"])
    assert len(findings) == 1
    assert findings[0].code == "CH092"


def test_ch092_flags_write_bytes_with_str():
    code = "def f(p):\n    return p.write_bytes('hello')\n"
    findings = _run(code, ["CH092"])
    assert len(findings) == 1


def test_ch092_ignores_correct_types():
    code = "def f(p):\n    p.write_text('hello')\n    p.write_bytes(b'hello')\n"
    assert _run(code, ["CH092"]) == []


# --- CH093 asyncio-to-thread-async-function ---------------------------------------------------------


def test_ch093_flags_to_thread_on_async_function():
    code = "import asyncio\nasync def worker():\n    return 42\nasync def f():\n    return await asyncio.to_thread(worker)\n"
    findings = _run(code, ["CH093"])
    assert len(findings) == 1
    assert findings[0].code == "CH093"


def test_ch093_ignores_sync_function():
    code = "import asyncio\ndef worker():\n    return 42\nasync def f():\n    return await asyncio.to_thread(worker)\n"
    assert _run(code, ["CH093"]) == []


# --- CH094 duplicate-kwarg-via-dict-unpack -----------------------------------------------------------


def test_ch094_flags_duplicate_keyword_via_dict_unpack():
    code = "def f(**kwargs):\n    return kwargs\ndef g():\n    return f(a=1, **{'a': 2})\n"
    findings = _run(code, ["CH094"])
    assert len(findings) == 1
    assert findings[0].code == "CH094"


def test_ch094_ignores_no_overlap():
    code = "def f(**kwargs):\n    return kwargs\ndef g():\n    return f(a=1, **{'b': 2})\n"
    assert _run(code, ["CH094"]) == []


# --- CH095 multiprocessing-spawn-lambda-target --------------------------------------------------------


def test_ch095_flags_lambda_target_on_spawn_context():
    code = (
        "import multiprocessing\n"
        "def f():\n"
        "    ctx = multiprocessing.get_context('spawn')\n"
        "    p = ctx.Process(target=lambda: None)\n"
        "    return p\n"
    )
    findings = _run(code, ["CH095"])
    assert len(findings) == 1
    assert findings[0].code == "CH095"


def test_ch095_ignores_default_context():
    code = "import multiprocessing\ndef f():\n    p = multiprocessing.Process(target=lambda: None)\n    return p\n"
    assert _run(code, ["CH095"]) == []


def test_ch095_ignores_named_function_target():
    code = (
        "import multiprocessing\n"
        "def worker(): pass\n"
        "def f():\n"
        "    ctx = multiprocessing.get_context('spawn')\n"
        "    p = ctx.Process(target=worker)\n"
        "    return p\n"
    )
    assert _run(code, ["CH095"]) == []


# --- CH096 post-init-on-non-dataclass --------------------------------------------------------------


def test_ch096_flags_post_init_on_plain_class():
    code = "class Foo:\n    def __init__(self):\n        pass\n    def __post_init__(self):\n        self.ready = True\n"
    findings = _run(code, ["CH096"])
    assert len(findings) == 1
    assert findings[0].code == "CH096"


def test_ch096_ignores_dataclass():
    code = "from dataclasses import dataclass\n@dataclass\nclass Foo:\n    x: int\n    def __post_init__(self):\n        self.ready = True\n"
    assert _run(code, ["CH096"]) == []


def test_ch096_ignores_custom_decorator():
    code = "@config\nclass Foo:\n    def __post_init__(self):\n        self.ready = True\n"
    assert _run(code, ["CH096"]) == []


def test_ch096_ignores_dataclass_subclass_inheriting_it():
    code = (
        "from dataclasses import dataclass\n"
        "class Base:\n"
        "    def __post_init__(self):\n        self.ready = True\n"
        "@dataclass\n"
        "class Sub(Base):\n    x: int\n"
    )
    assert _run(code, ["CH096"]) == []


# --- CH097 raise-not-implemented-singleton ------------------------------------------------------------


def test_ch097_flags_raise_not_implemented():
    code = "def f():\n    raise NotImplemented\n"
    findings = _run(code, ["CH097"])
    assert len(findings) == 1
    assert findings[0].code == "CH097"


def test_ch097_ignores_not_implemented_error():
    code = "def f():\n    raise NotImplementedError\n"
    assert _run(code, ["CH097"]) == []


# --- CH098 multiple-slots-layout-conflict ---------------------------------------------------------------


def test_ch098_flags_two_slotted_bases():
    code = "class A:\n    __slots__ = ('a',)\nclass B:\n    __slots__ = ('b',)\nclass C(A, B):\n    __slots__ = ()\n"
    findings = _run(code, ["CH098"])
    assert len(findings) == 1
    assert findings[0].code == "CH098"


def test_ch098_ignores_one_slotted_base():
    code = "class A:\n    __slots__ = ('a',)\nclass B:\n    pass\nclass C(A, B):\n    __slots__ = ()\n"
    assert _run(code, ["CH098"]) == []


# --- CH099 maketrans-mismatched-length ------------------------------------------------------------------


def test_ch099_flags_mismatched_length_literals():
    code = "def f():\n    return str.maketrans('abc', 'de')\n"
    findings = _run(code, ["CH099"])
    assert len(findings) == 1
    assert findings[0].code == "CH099"


def test_ch099_ignores_matching_length():
    code = "def f():\n    return str.maketrans('abc', 'xyz')\n"
    assert _run(code, ["CH099"]) == []


# --- CH100 iter-returns-self-no-next --------------------------------------------------------------------


def test_ch100_flags_iter_returns_self_no_next():
    code = "class Foo:\n    def __iter__(self):\n        return self\n"
    findings = _run(code, ["CH100"])
    assert len(findings) == 1
    assert findings[0].code == "CH100"


def test_ch100_ignores_with_next_defined():
    code = "class Foo:\n    def __iter__(self):\n        return self\n    def __next__(self):\n        raise StopIteration\n"
    assert _run(code, ["CH100"]) == []


# --- CH101 setter-before-property -------------------------------------------------------------------------


def test_ch101_flags_setter_with_no_property():
    code = "class Foo:\n    @x.setter\n    def x(self, value):\n        self._x = value\n"
    findings = _run(code, ["CH101"])
    assert len(findings) == 1
    assert findings[0].code == "CH101"


def test_ch101_flags_setter_before_property_wrong_order():
    code = (
        "class Foo:\n"
        "    @x.setter\n"
        "    def x(self, value):\n"
        "        self._x = value\n"
        "    @property\n"
        "    def x(self):\n"
        "        return self._x\n"
    )
    findings = _run(code, ["CH101"])
    assert len(findings) == 1
    assert findings[0].code == "CH101"


def test_ch101_ignores_property_before_setter():
    code = (
        "class Foo:\n"
        "    @property\n"
        "    def x(self):\n"
        "        return self._x\n"
        "    @x.setter\n"
        "    def x(self, value):\n"
        "        self._x = value\n"
    )
    assert _run(code, ["CH101"]) == []


def test_ch101_ignores_inherited_property_still_needs_local_binding():
    # Inheriting the property doesn't help at runtime either - still a hit.
    code = (
        "class Base:\n"
        "    @property\n"
        "    def x(self):\n"
        "        return self._x\n"
        "class Foo(Base):\n"
        "    @x.setter\n"
        "    def x(self, value):\n"
        "        self._x = value\n"
    )
    findings = _run(code, ["CH101"])
    assert len(findings) == 1
    assert findings[0].code == "CH101"


# --- CH102 total-ordering-no-methods -----------------------------------------------------------------------


def test_ch102_flags_total_ordering_with_only_eq():
    code = (
        "import functools\n"
        "@functools.total_ordering\n"
        "class Foo:\n"
        "    def __eq__(self, other):\n"
        "        return True\n"
    )
    findings = _run(code, ["CH102"])
    assert len(findings) == 1
    assert findings[0].code == "CH102"


def test_ch102_ignores_with_lt_defined():
    code = (
        "import functools\n"
        "@functools.total_ordering\n"
        "class Foo:\n"
        "    def __eq__(self, other):\n"
        "        return True\n"
        "    def __lt__(self, other):\n"
        "        return False\n"
    )
    assert _run(code, ["CH102"]) == []


def test_ch102_ignores_custom_base():
    code = (
        "import functools\n"
        "@functools.total_ordering\n"
        "class Foo(Base):\n"
        "    def __eq__(self, other):\n"
        "        return True\n"
    )
    assert _run(code, ["CH102"]) == []


# --- CH103 slots-non-identifier-string ---------------------------------------------------------------------


def test_ch103_flags_space_separated_slots_string():
    code = "class Foo:\n    __slots__ = 'foo bar'\n"
    findings = _run(code, ["CH103"])
    assert len(findings) == 1
    assert findings[0].code == "CH103"


def test_ch103_flags_comma_separated_slots_string():
    code = "class Foo:\n    __slots__ = 'foo,bar'\n"
    findings = _run(code, ["CH103"])
    assert len(findings) == 1
    assert findings[0].code == "CH103"


def test_ch103_ignores_single_identifier_string():
    code = "class Foo:\n    __slots__ = 'foobar'\n"
    assert _run(code, ["CH103"]) == []


def test_ch103_ignores_tuple_slots():
    code = "class Foo:\n    __slots__ = ('foo', 'bar')\n"
    assert _run(code, ["CH103"]) == []


# --- CH104 dataclass-field-mutable-default -----------------------------------------------------------------


def test_ch104_flags_field_default_list_literal():
    code = "from dataclasses import dataclass, field\n@dataclass\nclass Foo:\n    items: list = field(default=[])\n"
    findings = _run(code, ["CH104"])
    assert len(findings) == 1
    assert findings[0].code == "CH104"


def test_ch104_flags_field_default_dict_call():
    code = "from dataclasses import dataclass, field\n@dataclass\nclass Foo:\n    items: dict = field(default=dict())\n"
    findings = _run(code, ["CH104"])
    assert len(findings) == 1
    assert findings[0].code == "CH104"


def test_ch104_ignores_default_factory():
    code = "from dataclasses import dataclass, field\n@dataclass\nclass Foo:\n    items: list = field(default_factory=list)\n"
    assert _run(code, ["CH104"]) == []


def test_ch104_ignores_non_mutable_default():
    code = "from dataclasses import dataclass, field\n@dataclass\nclass Foo:\n    count: int = field(default=0)\n"
    assert _run(code, ["CH104"]) == []

