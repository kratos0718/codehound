"""CH068 - a logging call's ``extra={}`` dict uses a key that's already a
``LogRecord`` attribute name.

Verified directly against the real `Logger.makeRecord` source: it raises
``KeyError: "Attempt to overwrite 'name' in LogRecord"`` for any `extra`
key that's either `"message"`/`"asctime"` or already in the fresh
`LogRecord`'s own `__dict__` - which includes `name`, `msg`, `args`,
`levelname`, `levelno`, `module`, `funcName`, `lineno`, `thread`, and
every other attribute a `LogRecord` always has. The trap: this only
raises once the log call actually reaches `makeRecord` - a logger whose
effective level filters the call out (a `.debug(...)` call under a
`WARNING`-level logger, the common case in production) never constructs
a `LogRecord` at all, so the bug is invisible until someone turns
verbosity up to actually investigate something, which is exactly when a
new `KeyError` is the least welcome.
"""

from __future__ import annotations

import ast

from codehound.core import Check, Finding

_LOG_METHODS = {"debug", "info", "warning", "warn", "error", "exception", "critical", "log"}

_RESERVED_KEYS = {
    "name",
    "msg",
    "args",
    "levelname",
    "levelno",
    "pathname",
    "filename",
    "module",
    "exc_info",
    "exc_text",
    "stack_info",
    "lineno",
    "funcName",
    "created",
    "msecs",
    "relativeCreated",
    "thread",
    "threadName",
    "processName",
    "process",
    "message",
    "asctime",
}


class LoggingExtraReservedKey(Check):
    code = "CH068"
    name = "logging-extra-reserved-key"
    description = "A logging call's extra={} dict uses a key that's already a LogRecord attribute - KeyError."

    def run(self, tree: ast.AST, parents: dict, path: str) -> list[Finding]:
        findings: list[Finding] = []
        for node in ast.walk(tree):
            if not (
                isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and node.func.attr in _LOG_METHODS
            ):
                continue
            extra_kw = next((kw for kw in node.keywords if kw.arg == "extra"), None)
            if extra_kw is None or not isinstance(extra_kw.value, ast.Dict):
                continue
            for key_node in extra_kw.value.keys:
                if (
                    isinstance(key_node, ast.Constant)
                    and isinstance(key_node.value, str)
                    and key_node.value in _RESERVED_KEYS
                ):
                    findings.append(
                        Finding(
                            path=path,
                            line=key_node.lineno,
                            col=key_node.col_offset,
                            code=self.code,
                            message=(
                                f"`extra={{{key_node.value!r}: ...}}` collides with a "
                                f"LogRecord attribute of the same name - this raises `KeyError: "
                                f"\"Attempt to overwrite {key_node.value!r} in LogRecord\"` the "
                                f"moment this log call actually fires, not before. Rename the key."
                            ),
                        )
                    )
        return findings
