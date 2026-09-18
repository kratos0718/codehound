"""CH032 - a default argument computed from a call to a non-deterministic function.

A default value is evaluated exactly *once*, when the function is
defined, not on every call - the same fact CH002 is about, but this is
a distinct shape: a call to something like `time.time()` or
`datetime.now()` isn't mutable, so CH002's "shared mutable object" check
doesn't fire, and it's syntactically identical to a perfectly reasonable
default like `def f(x=DEFAULT_TIMEOUT):`. What makes it a bug is that
the *value itself* depends on when it's called, and every default
argument only ever captures the value from function-definition time.
Verified directly:

    def f(x=time.time()):
        return x

    a = f()
    time.sleep(0.05)
    b = f()
    a == b  # True - both calls return the exact same timestamp

Deliberately narrow, unlike a general "any call as a default is
suspicious" rule (flake8-bugbear's B008, which also flags things like
`def f(x=some_factory()):` that may well be an intentional
compute-once memoization): this only flags a curated set of functions
where "the same value every call" can never be what the author wanted -
the current time, a random number, a new UUID. A generic factory call
as a default might be deliberate; a cached `time.time()` never is.
"""

from __future__ import annotations

import ast

from codehound.core import Check, Finding

# (module, attribute) pairs whose result changes every call and would
# never sensibly be memoized as a shared default.
_NONDETERMINISTIC_CALLS: dict[tuple[str, str], str] = {
    ("time", "time"): "time.time()",
    ("time", "monotonic"): "time.monotonic()",
    ("time", "perf_counter"): "time.perf_counter()",
    ("datetime", "now"): "datetime.now()",
    ("datetime", "utcnow"): "datetime.utcnow()",
    ("date", "today"): "date.today()",
    ("random", "random"): "random.random()",
    ("random", "randint"): "random.randint()",
    ("random", "choice"): "random.choice()",
    ("uuid", "uuid4"): "uuid.uuid4()",
}


def _nondeterministic_call_name(node: ast.expr) -> str | None:
    if not isinstance(node, ast.Call):
        return None
    func = node.func
    if isinstance(func, ast.Attribute) and isinstance(func.value, ast.Name):
        return _NONDETERMINISTIC_CALLS.get((func.value.id, func.attr))
    return None


def _iter_defaults(args: ast.arguments):
    positional = args.posonlyargs + args.args
    for arg, default in zip(reversed(positional), reversed(args.defaults)):
        yield arg, default
    for arg, default in zip(args.kwonlyargs, args.kw_defaults):
        if default is not None:
            yield arg, default


class NondeterministicDefault(Check):
    code = "CH032"
    name = "nondeterministic-default-argument"
    description = "Default argument calls a function (time/random/uuid) whose result changes every call."

    def run(self, tree: ast.AST, parents: dict, path: str) -> list[Finding]:
        findings: list[Finding] = []
        for node in ast.walk(tree):
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.Lambda)):
                continue
            for arg, default in _iter_defaults(node.args):
                call_text = _nondeterministic_call_name(default)
                if call_text is None:
                    continue
                name = getattr(node, "name", "<lambda>")
                findings.append(
                    Finding(
                        path=path,
                        line=default.lineno,
                        col=default.col_offset,
                        code=self.code,
                        message=(
                            f"default value for `{arg.arg}` in `{name}` calls `{call_text}` - "
                            f"evaluated once, at definition time, not on every call. Every "
                            f"invocation using the default gets the exact same value. Use "
                            f"`{arg.arg}=None` and compute it inside the function body instead."
                        ),
                    )
                )
        return findings
