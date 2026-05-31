"""Registry of all available checks."""

from __future__ import annotations

from codehound.checks.blocking_async import BlockingCallInAsync
from codehound.checks.datetime_utcnow import DeprecatedDatetimeUtcnow
from codehound.checks.floating_task import FloatingTask
from codehound.checks.get_event_loop import DeprecatedGetEventLoop
from codehound.checks.mutable_defaults import MutableDefaultArgument
from codehound.checks.resource_leak import UnclosedFileHandle
from codehound.core import Check

ALL_CHECKS: list[type[Check]] = [
    BlockingCallInAsync,
    MutableDefaultArgument,
    DeprecatedDatetimeUtcnow,
    DeprecatedGetEventLoop,
    UnclosedFileHandle,
    FloatingTask,
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
