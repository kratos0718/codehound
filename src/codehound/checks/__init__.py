"""Registry of all available checks."""

from __future__ import annotations

from codehound.checks.async_property import AsyncProperty
from codehound.checks.asyncio_coroutine_decorator import AsyncioCoroutineDecorator
from codehound.checks.asyncio_run_in_loop import AsyncioRunInRunningLoop
from codehound.checks.bare_except import BareExcept
from codehound.checks.blocking_async import BlockingCallInAsync
from codehound.checks.collections_abc_import import CollectionsAbcImport
from codehound.checks.datetime_utcnow import DeprecatedDatetimeUtcnow
from codehound.checks.discarded_future import DiscardedFuture
from codehound.checks.empty_except_tuple import EmptyExceptTuple
from codehound.checks.environ_reassignment import EnvironReassignment
from codehound.checks.finally_swallows_exception import FinallySwallowsException
from codehound.checks.floating_process import FloatingProcess
from codehound.checks.floating_task import FloatingTask
from codehound.checks.floating_thread import FloatingThread
from codehound.checks.floating_timer import FloatingTimer
from codehound.checks.get_event_loop import DeprecatedGetEventLoop
from codehound.checks.is_literal_comparison import IsLiteralComparison
from codehound.checks.lock_constructed_inline import LockConstructedInline
from codehound.checks.loop_closure_capture import LoopClosureCapture
from codehound.checks.lru_cache_on_async_function import LruCacheOnAsyncFunction
from codehound.checks.lru_cache_on_method import LruCacheOnMethod
from codehound.checks.mutable_class_attribute import MutableClassAttribute
from codehound.checks.mutable_defaults import MutableDefaultArgument
from codehound.checks.nondeterministic_default import NondeterministicDefault
from codehound.checks.pointless_comparison import PointlessComparisonStatement
from codehound.checks.raise_literal import RaiseLiteral
from codehound.checks.removed_asyncio_task_methods import RemovedAsyncioTaskMethods
from codehound.checks.removed_getargspec import RemovedGetargspec
from codehound.checks.removed_stdlib_attribute import RemovedStdlibAttribute
from codehound.checks.removed_stdlib_module import RemovedStdlibModule
from codehound.checks.resource_leak import UnclosedFileHandle
from codehound.checks.strip_multichar import StripMultichar
from codehound.checks.unawaited_coroutine import UnawaitedCoroutineCall
from codehound.checks.unclosed_pool import UnclosedPool
from codehound.checks.unclosed_socket import UnclosedSocket
from codehound.checks.unittest_deprecated_alias import UnittestDeprecatedAlias
from codehound.checks.unprotected_lock import UnprotectedLockAcquire
from codehound.checks.unwaited_subprocess import UnwaitedSubprocess
from codehound.checks.useless_expression import UselessExpressionStatement
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
    RemovedStdlibModule,
    AsyncioCoroutineDecorator,
    RemovedStdlibAttribute,
    UnittestDeprecatedAlias,
    IsLiteralComparison,
    MutableClassAttribute,
    UnwaitedSubprocess,
    FloatingTimer,
    FinallySwallowsException,
    LruCacheOnAsyncFunction,
    UnclosedPool,
    NondeterministicDefault,
    StripMultichar,
    RaiseLiteral,
    EmptyExceptTuple,
    EnvironReassignment,
    PointlessComparisonStatement,
    UselessExpressionStatement,
    LockConstructedInline,
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
