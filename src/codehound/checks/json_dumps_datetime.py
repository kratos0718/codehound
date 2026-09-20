"""CH083 - ``json.dumps()``/``json.dump()`` is handed a ``datetime``/
``date`` object built inline, with no ``default=``/``cls=`` to handle it.

Verified directly:

    json.dumps(datetime.now())
    # TypeError: Object of type datetime is not JSON serializable

`json`'s encoder only knows a fixed set of built-in types - `datetime`
and `date` were never among them, and there's no version of the standard
library where this call succeeds without help. `default=` (a fallback
serializer function) or `cls=` (a custom `JSONEncoder`) are the documented
ways to handle it; either one present on the call means it's already
handled, so both are excluded.

Only fires when the value passed to `json.dumps`/`json.dump` is, right
there in the call, the direct result of a known datetime/date-producing
call (`datetime.now()`, `datetime.utcnow()`, `date.today()`,
`datetime.fromtimestamp(...)`, etc.) - a variable that merely *might*
hold a datetime is not something this check can see.
"""

from __future__ import annotations

import ast

from codehound.core import Check, Finding, attr_call_parts

_DATETIME_FACTORY_ATTRS = {"now", "utcnow", "today", "fromtimestamp", "utcfromtimestamp", "fromisoformat"}
_DATE_HINTS = ("date", "time")


def _is_datetime_factory_call(node: ast.expr) -> bool:
    if not isinstance(node, ast.Call) or not isinstance(node.func, ast.Attribute):
        return False
    if node.func.attr not in _DATETIME_FACTORY_ATTRS:
        return False
    base = node.func.value
    base_name = base.id if isinstance(base, ast.Name) else base.attr if isinstance(base, ast.Attribute) else ""
    return any(hint in base_name.lower() for hint in _DATE_HINTS)


class JsonDumpsDatetime(Check):
    code = "CH083"
    name = "json-dumps-datetime"
    description = "json.dumps()/dump() is given a datetime/date object built inline, with no default=/cls= to handle it - raises TypeError."

    def run(self, tree: ast.AST, parents: dict, path: str) -> list[Finding]:
        findings: list[Finding] = []
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            func = node.func
            if not (isinstance(func, ast.Attribute) and func.attr in ("dumps", "dump")):
                continue
            if not (isinstance(func.value, ast.Name) and func.value.id == "json"):
                continue
            if any(kw.arg in ("default", "cls") for kw in node.keywords):
                continue
            if not node.args or not _is_datetime_factory_call(node.args[0]):
                continue
            base, attr = attr_call_parts(node.args[0])
            call_desc = f"{base}.{attr}()" if base else f"{attr}()"
            findings.append(
                Finding(
                    path=path,
                    line=node.lineno,
                    col=node.col_offset,
                    code=self.code,
                    message=(
                        f"json.{func.attr}() is given {call_desc}, built inline, with no "
                        f"default=/cls= to handle it - raises TypeError: Object of type ... "
                        f"is not JSON serializable."
                    ),
                )
            )
        return findings
