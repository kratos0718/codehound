"""Registry of all available checks."""

from __future__ import annotations

from codehound.checks.abstractmethod_without_abc import AbstractmethodWithoutAbc
from codehound.checks.aliased_list_multiplication import AliasedListMultiplication
from codehound.checks.argparse_store_true_default import ArgparseStoreTrueDefault
from codehound.checks.assert_on_tuple import AssertOnTuple
from codehound.checks.assert_raises_too_broad import AssertRaisesTooBroad
from codehound.checks.async_property import AsyncProperty
from codehound.checks.asyncio_coroutine_decorator import AsyncioCoroutineDecorator
from codehound.checks.asyncio_run_in_loop import AsyncioRunInRunningLoop
from codehound.checks.asyncio_to_thread_async_function import AsyncioToThreadAsyncFunction
from codehound.checks.asyncio_wait_bare_coroutine import AsyncioWaitBareCoroutine
from codehound.checks.augassign_without_nonlocal import AugassignWithoutNonlocal
from codehound.checks.bare_except import BareExcept
from codehound.checks.blocking_async import BlockingCallInAsync
from codehound.checks.bytes_str_join_mismatch import BytesStrJoinMismatch
from codehound.checks.collections_abc_import import CollectionsAbcImport
from codehound.checks.contextmanager_yield_unprotected import ContextmanagerYieldUnprotected
from codehound.checks.contextvar_mutable_default import ContextvarMutableDefault
from codehound.checks.dataclass_field_mutable_default import DataclassFieldMutableDefault
from codehound.checks.dataclass_non_default_after_default import DataclassNonDefaultAfterDefault
from codehound.checks.datetime_utcnow import DeprecatedDatetimeUtcnow
from codehound.checks.decorator_missing_functools_wraps import DecoratorMissingFunctoolsWraps
from codehound.checks.decorator_missing_return import DecoratorMissingReturn
from codehound.checks.deepcopy_self_with_lock import DeepcopySelfWithLock
from codehound.checks.defaultdict_read_creates_key import DefaultdictReadCreatesKey
from codehound.checks.dict_fromkeys_mutable_default import DictFromkeysMutableDefault
from codehound.checks.discarded_future import DiscardedFuture
from codehound.checks.duplicate_dict_key import DuplicateDictKey
from codehound.checks.duplicate_except_handler import DuplicateExceptHandler
from codehound.checks.duplicate_kwarg_via_dict_unpack import DuplicateKwargViaDictUnpack
from codehound.checks.duplicate_method_definition import DuplicateMethodDefinition
from codehound.checks.duplicate_set_value import DuplicateSetValue
from codehound.checks.duplicate_with_target import DuplicateWithTarget
from codehound.checks.empty_except_tuple import EmptyExceptTuple
from codehound.checks.empty_literal_sequence_crash import EmptyLiteralSequenceCrash
from codehound.checks.enumerate_start_offset_reindex import EnumerateStartOffsetReindex
from codehound.checks.environ_reassignment import EnvironReassignment
from codehound.checks.exit_returns_true_unconditionally import ExitReturnsTrueUnconditionally
from codehound.checks.falsy_and_or_ternary import FalsyAndOrTernary
from codehound.checks.finally_swallows_exception import FinallySwallowsException
from codehound.checks.floating_process import FloatingProcess
from codehound.checks.floating_task import FloatingTask
from codehound.checks.floating_thread import FloatingThread
from codehound.checks.floating_timer import FloatingTimer
from codehound.checks.forwarded_without_unpacking import ForwardedWithoutUnpacking
from codehound.checks.frozen_dataclass_post_init_mutation import FrozenDataclassPostInitMutation
from codehound.checks.get_event_loop import DeprecatedGetEventLoop
from codehound.checks.hash_eq_field_mismatch import HashEqFieldMismatch
from codehound.checks.is_literal_comparison import IsLiteralComparison
from codehound.checks.iter_returns_self_no_next import IterReturnsSelfNoNext
from codehound.checks.itertools_tee_original_reused import IteratorTeeOriginalReused
from codehound.checks.json_dumps_datetime import JsonDumpsDatetime
from codehound.checks.lock_constructed_inline import LockConstructedInline
from codehound.checks.logging_extra_reserved_key import LoggingExtraReservedKey
from codehound.checks.loop_closure_capture import LoopClosureCapture
from codehound.checks.lru_cache_on_async_function import LruCacheOnAsyncFunction
from codehound.checks.lru_cache_on_method import LruCacheOnMethod
from codehound.checks.maketrans_mismatched_length import MaketransMismatchedLength
from codehound.checks.multiple_slots_layout_conflict import MultipleSlotsLayoutConflict
from codehound.checks.multiprocessing_spawn_lambda_target import MultiprocessingSpawnLambdaTarget
from codehound.checks.mutable_class_attribute import MutableClassAttribute
from codehound.checks.mutable_defaults import MutableDefaultArgument
from codehound.checks.mutation_during_iteration import MutationDuringIteration
from codehound.checks.namedtuple_mutable_default import NamedTupleMutableDefault
from codehound.checks.namedtuple_non_default_after_default import NamedTupleNonDefaultAfterDefault
from codehound.checks.nan_equality import NanEqualityComparison
from codehound.checks.nondeterministic_default import NondeterministicDefault
from codehound.checks.os_path_join_absolute_literal import OsPathJoinAbsoluteLiteral
from codehound.checks.path_absolute_literal_join import PathAbsoluteLiteralJoin
from codehound.checks.path_write_type_mismatch import PathWriteTypeMismatch
from codehound.checks.pointless_comparison import PointlessComparisonStatement
from codehound.checks.post_init_on_non_dataclass import PostInitOnNonDataclass
from codehound.checks.python2_removed_dunder import Python2RemovedDunder
from codehound.checks.raise_literal import RaiseLiteral
from codehound.checks.raise_not_implemented_singleton import RaiseNotImplementedSingleton
from codehound.checks.regex_backspace_escape import RegexBackspaceEscape
from codehound.checks.regex_flags_passed_as_count import RegexFlagsPassedAsCount
from codehound.checks.repr_calls_str_recursion import ReprCallsStrRecursion
from codehound.checks.reused_exhausted_iterator import ReusedExhaustedIterator
from codehound.checks.removed_asyncio_task_methods import RemovedAsyncioTaskMethods
from codehound.checks.removed_getargspec import RemovedGetargspec
from codehound.checks.removed_stdlib_attribute import RemovedStdlibAttribute
from codehound.checks.removed_stdlib_module import RemovedStdlibModule
from codehound.checks.resource_leak import UnclosedFileHandle
from codehound.checks.setter_before_property import SetterBeforeProperty
from codehound.checks.slots_blocks_dict import SlotsBlocksDict
from codehound.checks.slots_conflicts_class_variable import SlotsConflictsClassVariable
from codehound.checks.slots_non_identifier_string import SlotsNonIdentifierString
from codehound.checks.static_dict_comprehension_key import StaticDictComprehensionKey
from codehound.checks.staticmethod_references_self import StaticmethodReferencesSelf
from codehound.checks.str_on_bytes import StrOnBytes
from codehound.checks.strip_multichar import StripMultichar
from codehound.checks.suppress_empty import SuppressEmpty
from codehound.checks.threading_local_mutable_class_attr import ThreadingLocalMutableClassAttr
from codehound.checks.total_ordering_missing_eq import TotalOrderingMissingEq
from codehound.checks.total_ordering_no_methods import TotalOrderingNoMethods
from codehound.checks.unawaited_coroutine import UnawaitedCoroutineCall
from codehound.checks.unbounded_cycle_consumption import UnboundedCycleConsumption
from codehound.checks.unclosed_pool import UnclosedPool
from codehound.checks.unclosed_socket import UnclosedSocket
from codehound.checks.unittest_deprecated_alias import UnittestDeprecatedAlias
from codehound.checks.unprotected_lock import UnprotectedLockAcquire
from codehound.checks.unwaited_subprocess import UnwaitedSubprocess
from codehound.checks.useless_expression import UselessExpressionStatement
from codehound.checks.weakref_to_ephemeral_object import WeakrefToEphemeralObject
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
    AssertRaisesTooBroad,
    SuppressEmpty,
    DuplicateExceptHandler,
    NanEqualityComparison,
    AugassignWithoutNonlocal,
    DuplicateDictKey,
    DuplicateSetValue,
    ContextmanagerYieldUnprotected,
    AssertOnTuple,
    StaticmethodReferencesSelf,
    StaticDictComprehensionKey,
    MutationDuringIteration,
    ForwardedWithoutUnpacking,
    AliasedListMultiplication,
    SlotsBlocksDict,
    DuplicateWithTarget,
    PathAbsoluteLiteralJoin,
    ReusedExhaustedIterator,
    ArgparseStoreTrueDefault,
    DecoratorMissingReturn,
    FalsyAndOrTernary,
    RegexBackspaceEscape,
    TotalOrderingMissingEq,
    UnboundedCycleConsumption,
    AsyncioWaitBareCoroutine,
    DictFromkeysMutableDefault,
    OsPathJoinAbsoluteLiteral,
    NamedTupleMutableDefault,
    LoggingExtraReservedKey,
    ContextvarMutableDefault,
    ThreadingLocalMutableClassAttr,
    WeakrefToEphemeralObject,
    IteratorTeeOriginalReused,
    StrOnBytes,
    EmptyLiteralSequenceCrash,
    ReprCallsStrRecursion,
    DuplicateMethodDefinition,
    AbstractmethodWithoutAbc,
    FrozenDataclassPostInitMutation,
    DataclassNonDefaultAfterDefault,
    NamedTupleNonDefaultAfterDefault,
    SlotsConflictsClassVariable,
    Python2RemovedDunder,
    JsonDumpsDatetime,
    DefaultdictReadCreatesKey,
    DecoratorMissingFunctoolsWraps,
    DeepcopySelfWithLock,
    EnumerateStartOffsetReindex,
    RegexFlagsPassedAsCount,
    BytesStrJoinMismatch,
    ExitReturnsTrueUnconditionally,
    HashEqFieldMismatch,
    PathWriteTypeMismatch,
    AsyncioToThreadAsyncFunction,
    DuplicateKwargViaDictUnpack,
    MultiprocessingSpawnLambdaTarget,
    PostInitOnNonDataclass,
    RaiseNotImplementedSingleton,
    MultipleSlotsLayoutConflict,
    MaketransMismatchedLength,
    IterReturnsSelfNoNext,
    SetterBeforeProperty,
    TotalOrderingNoMethods,
    SlotsNonIdentifierString,
    DataclassFieldMutableDefault,
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
