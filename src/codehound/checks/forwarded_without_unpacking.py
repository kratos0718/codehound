"""CH052 - a function's own ``*args``/``**kwargs`` parameter is passed to
another call alongside a correctly-starred argument, but without its own
matching star.

A wrapper/decorator forwarding its variadic parameters is one of the most
common shapes in Python (``def wrapper(*args, **kwargs): return
func(*args, **kwargs)``). Dropping one star - ``func(*args, kwargs)`` -
is a plausible, easy typo, and its consequence depends entirely on what the
callee accepts: verified directly, if the callee also takes ``*args`` the
``kwargs`` dict is silently appended as one extra *positional* value instead
of being unpacked into keywords - no error, just wrong arguments, forever.

Only fires when the call *already* correctly unpacks something else with a
star (``*args`` or ``**other``) - a bare, un-starred ``args``/``kwargs``
passed completely on its own (``len(args)``, ``bool(kwargs)``,
``dict(kwargs)``) is an ordinary, extremely common way to use the collection
*itself* as a value, and the first corpus scan confirmed this is overwhelmingly
what a lone occurrence actually is: it was the single largest source of
false positives in this whole check, at over two thousand hits, almost all
of them exactly this shape (``len(args)`` inside the same function that also
declares ``*args``). A call that mixes a real star with a bare name of the
same kind is a much stronger, closer-to-unambiguous signal that this
specific call is a forwarding call that a `*`/`**` was dropped from midway
through writing it - not a call that never had unpacking syntax at all.

Also excludes ``dict(...)``/``.update(...)`` calls specifically: found for
real in letta's own decorator helper, ``dict(_kwargs, **kwargs)`` is the
standard, correct way to merge a mapping passed positionally with
additional keyword overrides - `dict`'s own constructor (and `.update()`)
is explicitly designed to accept a mapping as its first positional
argument, unlike an arbitrary user function, so a bare `kwargs` there is
never a dropped star.
"""

from __future__ import annotations

import ast

from codehound.core import Check, Finding, enclosing_function


def _variadic_param_names(func: ast.FunctionDef | ast.AsyncFunctionDef) -> tuple[str | None, str | None]:
    args = func.args
    star_name = args.vararg.arg if args.vararg else None
    kwarg_name = args.kwarg.arg if args.kwarg else None
    return star_name, kwarg_name


def _call_has_other_unpacking(call: ast.Call) -> bool:
    if any(isinstance(a, ast.Starred) for a in call.args):
        return True
    return any(kw.arg is None for kw in call.keywords)


def _is_dict_merge_call(call: ast.Call) -> bool:
    func = call.func
    if isinstance(func, ast.Name):
        return func.id == "dict"
    return isinstance(func, ast.Attribute) and func.attr == "update"


class ForwardedWithoutUnpacking(Check):
    code = "CH052"
    name = "forwarded-without-unpacking"
    description = "A call already unpacks one argument with a star but forwards *args/**kwargs bare, alongside it."

    def run(self, tree: ast.AST, parents: dict, path: str) -> list[Finding]:
        findings: list[Finding] = []
        for call in ast.walk(tree):
            if not isinstance(call, ast.Call):
                continue
            if not _call_has_other_unpacking(call):
                continue
            if _is_dict_merge_call(call):
                continue
            func = enclosing_function(call, parents)
            if func is None:
                continue
            star_name, kwarg_name = _variadic_param_names(func)
            if star_name is None and kwarg_name is None:
                continue
            for arg in call.args:
                if not isinstance(arg, ast.Name):
                    continue
                if arg.id == star_name:
                    findings.append(
                        Finding(
                            path=path,
                            line=arg.lineno,
                            col=arg.col_offset,
                            code=self.code,
                            message=(
                                f"`{arg.id}` is `{func.name}`'s own `*{arg.id}` parameter, passed "
                                f"here without a `*` even though this same call already unpacks "
                                f"another argument - it is forwarded as one extra positional "
                                f"tuple argument instead. Did you mean `*{arg.id}`?"
                            ),
                        )
                    )
                elif arg.id == kwarg_name:
                    findings.append(
                        Finding(
                            path=path,
                            line=arg.lineno,
                            col=arg.col_offset,
                            code=self.code,
                            message=(
                                f"`{arg.id}` is `{func.name}`'s own `**{arg.id}` parameter, passed "
                                f"here without `**` even though this same call already unpacks "
                                f"another argument - it is forwarded as one extra positional dict "
                                f"argument instead of being unpacked into keywords. Did you mean "
                                f"`**{arg.id}`?"
                            ),
                        )
                    )
        return findings
