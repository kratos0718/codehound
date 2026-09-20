"""CH095 - a ``multiprocessing.Process``/``Pool`` built from an explicit
``spawn``/``forkserver`` context is given a lambda as its target.

Verified directly:

    ctx = multiprocessing.get_context("spawn")
    p = ctx.Process(target=lambda: None)
    p.start()
    # PicklingError: Can't pickle <function <lambda> ...>: attribute
    # lookup <lambda> on __main__ failed

`spawn`/`forkserver` start a brand-new interpreter for the child process
and pickle the target callable (plus args) to hand it over - and a
lambda, having no importable qualified name, can never be pickled. The
default `fork` context (Linux's default) doesn't need this - it copies
the parent process directly, so a lambda works there - which is exactly
why this only breaks on an *explicit* spawn/forkserver context: code
that runs fine under the platform's own default silently stops working
the moment someone pins spawn/forkserver (a common thing to do
deliberately, e.g. for CUDA-using workers, which don't fork-safely).

Only fires when the context was built from a literal `get_context("spawn")`/
`get_context("forkserver")` call assigned to a name, and that same name's
`.Process(...)`/`.Pool(...)` call is given a `target=`/`initializer=`
argument that's a `Lambda` directly - not a variable that might hold one,
which this check has no way to trace.
"""

from __future__ import annotations

import ast

from codehound.core import Check, Finding

_UNPICKLABLE_CONTEXTS = {"spawn", "forkserver"}
_TARGET_KEYWORDS = {"target", "initializer"}


def _spawn_context_names(tree: ast.AST) -> set[str]:
    names: set[str] = set()
    for node in ast.walk(tree):
        if not isinstance(node, ast.Assign) or len(node.targets) != 1:
            continue
        target = node.targets[0]
        value = node.value
        if not isinstance(target, ast.Name) or not isinstance(value, ast.Call):
            continue
        func = value.func
        is_get_context = (isinstance(func, ast.Attribute) and func.attr == "get_context") or (
            isinstance(func, ast.Name) and func.id == "get_context"
        )
        if not is_get_context or not value.args:
            continue
        arg = value.args[0]
        if isinstance(arg, ast.Constant) and arg.value in _UNPICKLABLE_CONTEXTS:
            names.add(target.id)
    return names


class MultiprocessingSpawnLambdaTarget(Check):
    code = "CH095"
    name = "multiprocessing-spawn-lambda-target"
    description = "A spawn/forkserver multiprocessing context is given a lambda as target/initializer - always raises PicklingError."

    def run(self, tree: ast.AST, parents: dict, path: str) -> list[Finding]:
        findings: list[Finding] = []
        spawn_names = _spawn_context_names(tree)
        if not spawn_names:
            return findings
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call) or not isinstance(node.func, ast.Attribute):
                continue
            if not isinstance(node.func.value, ast.Name) or node.func.value.id not in spawn_names:
                continue
            if node.func.attr not in ("Process", "Pool"):
                continue
            for kw in node.keywords:
                if kw.arg in _TARGET_KEYWORDS and isinstance(kw.value, ast.Lambda):
                    findings.append(
                        Finding(
                            path=path,
                            line=kw.value.lineno,
                            col=kw.value.col_offset,
                            code=self.code,
                            message=(
                                f"`{kw.arg}=` is a lambda on a spawn/forkserver multiprocessing "
                                f"context - spawn pickles the target to send it to the new "
                                f"interpreter, and a lambda can never be pickled. Raises "
                                f"PicklingError on start()."
                            ),
                        )
                    )
        return findings
