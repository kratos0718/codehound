"""Registry of all available checks."""

from __future__ import annotations

from codehound.checks.async_property import AsyncProperty
from codehound.checks.asyncio_run_in_loop import AsyncioRunInRunningLoop
from codehound.checks.bare_except import BareExcept
from codehound.checks.blocking_async import BlockingCallInAsync
from codehound.checks.collections_abc_import import CollectionsAbcImport
from codehound.checks.datetime_utcnow import DeprecatedDatetimeUtcnow
from codehound.checks.discarded_future import DiscardedFuture
from codehound.checks.floating_process import FloatingProcess
from codehound.checks.floating_task import FloatingTask
from codehound.checks.floating_thread import FloatingThread
from codehound.checks.get_event_loop import DeprecatedGetEventLoop
from codehound.checks.loop_closure_capture import LoopClosureCapture
from codehound.checks.lru_cache_on_method import LruCacheOnMethod
from codehound.checks.mutable_defaults import MutableDefaultArgument
from codehound.checks.removed_asyncio_task_methods import RemovedAsyncioTaskMethods
from codehound.checks.removed_getargspec import RemovedGetargspec
from codehound.checks.resource_leak import UnclosedFileHandle
from codehound.checks.unawaited_coroutine import UnawaitedCoroutineCall
from codehound.checks.unclosed_socket import UnclosedSocket
from codehound.checks.unprotected_lock import UnprotectedLockAcquire
from codehound.core import Check

ALL_CHECKS: list[type[Check]] = [
    BlockingCallInAsync,
    MutableDefaultArgument,
    DeprecatedDatetimeUtcnow,
    DeprecatedGetEventLoop,
    UnclosedFileHandle,
    FloatingTask,
    UnawaitedCoroutineCall,
    AsyncioRunInRunningLoop,
    FloatingThread,
    LoopClosureCapture,
    LruCacheOnMethod,
    FloatingProcess,
    DiscardedFuture,
    UnprotectedLockAcquire,
    AsyncProperty,
    UnclosedSocket,
    CollectionsAbcImport,
    RemovedAsyncioTaskMethods,
    RemovedGetargspec,
    BareExcept,
]


def get_checks(selected: list[str] | None = None) -> list[Check]:
    """Instantiate checks, optionally filtered by a list of codes/names."""
    if not selected:
        return [cls() for cls in ALL_CHECKS]
    wanted = {s.upper() for s in selected}
    out: list[Check] = []
    for cls in ALL_CHECKS:
        if cls.code.upper() in wanted or cls.name.upper() in wanted:
            out.append(cls())
    return out
