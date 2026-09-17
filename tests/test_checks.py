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

