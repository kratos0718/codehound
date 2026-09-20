# Findings in the wild

Eight of the eighty-eight `codehound` rules were distilled from a bug
found in a real, widely-used open-source project, with the fix submitted
as a pull request. The rest (CH007-CH009, CH012-CH050, CH052-CH057,
CH059-CH066, CH069-CH075, CH078-CH083, CH086-CH088) are hardening rules
verified through real false positives against a ~29-framework validation
corpus instead of a found-and-merged bug - see "Notes on precision" below
for why, and what that absence itself says. CH026, CH029, CH034, CH036,
CH038, CH045, CH046, CH047, CH051, CH058, CH067, CH068, CH076, CH077,
CH084, and CH085 are partial exceptions: each found real,
previously-unreported bugs on their first (or, for CH051/CH058/CH069/
CH079/CH085, a later narrowed) scan, but not all of them have a PR yet -
see "Real bugs found, not yet filed" below.

Five more checks were built, corpus-scanned, and **rejected outright**
across this project's history, joining the same discipline that turned
down `exception-chaining` and `cancelled-error-swallowed` originally:
`assignment-from-sort-or-reverse`, `enum-duplicate-value`,
`eq-without-hash`/`abstract-stub-missing-decorator` from an earlier
round, and two more from this round - `enum-implicit-alias` and
`bare-except-swallows-cancelled-error` - that independently rediscovered
the exact same two rejections (enum aliasing, cancellation-swallowing)
from first principles, using different real-world examples, before this
file was even re-read - see the end of "Notes on precision" for all of
it and why.

| Rule | Project | ⭐ | The bug | Fix |
|------|---------|----|---------|-----|
| CH001 `blocking-call-in-async` | agno | 25k+ | **Found by codehound itself:** `requests.get()` inside the async `on_message` Discord handler froze the event loop on every video/document attachment (and could 403 on authenticated URLs) | replaced with `await media.read()`; regression test via `inspect.getsource` |
| CH001 `blocking-call-in-async` | agno | 25k+ | `time.sleep(1)` inside `_async_create_collection_and_scope` froze the event loop during a Couchbase collection overwrite | replaced with `await asyncio.sleep(1)`; regression test via `inspect.getsource` |
| CH002 `mutable-default-argument` | agno | 25k+ | Mutable default args in `MCPToolbox` (`_handle_auth_params`, `load_tool`, `load_toolset`) | PR #10217 (open) — 9 sites fixed, regression tests; supersedes #8152, which went stale on unresolved merge conflicts after inactivity (fix itself was never rejected) |
| CH002 `mutable-default-argument` | mem0 | 35k+ | `Completions.create(messages=[])` and `BaseEmbedderConfig.__init__(azure_kwargs={})` | PR #5302 — `None`-default + body init, `inspect.signature` test |
| CH002 `mutable-default-argument` | llama_index | 40k+ | `BeirEvaluator._download_datasets`/`.run` (`datasets=["nfcorpus"]`, `metrics_k_values=[3, 10]`), `SimpleGraphStore.query`/`GraphStore.query`/`PropertyGraphStore.astructured_query` (`param_map={}`) | PR #23085 (open) — 6 sites fixed, `inspect.signature` tests. 5 more hits from the same sweep (pydantic `BaseModel.__init__`s, one `Document(metadata=...)` call) were verified false positives - see below |
| CH003 `deprecated-datetime-utcnow` | crewAI | 30k+ | 9 calls to `datetime.utcnow()` across the memory subsystem (removed in 3.14) | PR #5970 — `datetime.now(timezone.utc).replace(tzinfo=None)` |
| CH004 `deprecated-get-event-loop` | crewAI | 30k+ | `asyncio.get_event_loop()` in structured-tool / Snowflake search tool | PR #5969 — `get_running_loop()`; bot-approved |
| CH005 `unclosed-file-handle` | agno | 25k+ | `audio_file = open(audio_path, "rb")` never closed in `OpenAITools.transcribe_audio` | wrapped in `with open(...) as audio_file:` |
| CH006 + CH004 `floating-task` + `deprecated-get-event-loop` | agno | 25k+ | **Found by codehound itself:** fire-and-forget `asyncio.create_task` + deprecated `get_event_loop()` in `tracing/exporter.py::_export_async` — traces could be silently dropped | PR #8183 (open) — strong task ref (set + done-callback) + `get_running_loop()` |
| CH006 `floating-task` | agno | 25k+ | Two more `asyncio.create_task(...)` results discarded in `Workflow._broadcast_to_websocket` / `_apublish_stream_event` — same weak-reference GC risk as #8183 above | PR #10222 (open) — retained via the file's existing `_workflow_background_tasks` set + done-callback |
| CH010 `loop-closure-capture` | accelerate (HuggingFace) | 9k+ | **Found by codehound itself:** `MegatronEngine.get_module_config`'s `param_sync_func` list builds one callback per distributed-training model chunk, but every lambda captures `model_index` by reference - whichever chunk's callback fires, it reports the *last* chunk's index to `finish_param_sync`, not its own | PR [huggingface/accelerate#4273](https://github.com/huggingface/accelerate/pull/4273) (open) — `model_index=model_index` default-arg capture; isolated regression test (the real method needs the optional `megatron-core` package, not available in CI) verified to fail pre-fix (all callbacks report index 2) and pass post-fix |
| CH011 `lru-cache-on-method` | optuna | 12k+ | **Found by codehound itself:** `_FanovaTree`'s seven node-lookup methods are `@lru_cache(maxsize=None)` directly on the class - every tree built for a `get_param_importances()` call (one per random-forest estimator) stays reachable through the cache for the life of the process instead of being freed once the importances are computed | PR [optuna/optuna#6859](https://github.com/optuna/optuna/pull/6859) (open) — moved the caching to per-instance by wrapping the bound methods in `__init__`; regression test constructs a tree, drops the only reference, and asserts it's collected - verified to fail pre-fix and pass post-fix |
| CH011 `lru-cache-on-method` | llama_index | 40k+ | **Found by codehound itself:** `VectaraIndex._get_corpus_key` is `@lru_cache(maxsize=None)` on the class - every index that calls it (insert/query/delete/update all do) leaks forever, which also means `VectaraIndex.__del__` (written specifically to close `self._session`) never runs, so the HTTP session leaks too | PR [run-llama/llama_index#23089](https://github.com/run-llama/llama_index/pull/23089) (open) — same per-instance-caching fix; regression test constructs an index with dummy credentials, calls the cached method, drops the reference, and asserts collection - verified to fail pre-fix and pass post-fix |
| CH011 `lru-cache-on-method` | litellm | 30k+ | **Found by codehound itself:** `Router._cached_get_model_group_info` is `@lru_cache` on the class - every `Router` that's served a request through it (`set_response_headers` calls it on every one) leaks forever. Proved this is a real, independent bug and not a "you forgot to clean up" issue: the leak survives even after correctly calling `Router.discard()`, the class's own documented cleanup method | PR [BerriAI/litellm#41582](https://github.com/BerriAI/litellm/pull/41582) (open) — same per-instance-caching fix, matching a sibling method (`cached_deployment_model_info`) that already used the correct pattern; regression test constructs a Router, calls the cached method, calls `discard()`, drops the reference, and asserts collection - verified to fail pre-fix and pass post-fix; as a side effect also fixes `cache_clear()` bleeding across every Router in the process instead of just the one being invalidated |

## Notes on precision

`codehound` is deliberately conservative. While building it, several AST
"hits" were investigated and **correctly rejected** as non-bugs — exactly
the false positives a naive grep would have reported:

- **dspy `syncify.run_async`** — a lingering `asyncio.get_event_loop()` sits inside
  a branch guarded by `loop.is_running()`, where it does *not* trigger the
  deprecation. CH004 flags the call but a human (correctly) decides it isn't worth
  a PR. The lesson — *a finding is a lead, not a verdict* — shaped the project's
  framing.
- **optuna `FileSystemArtifactStore.open_reader`** — returns the open handle to the
  caller (`-> BinaryIO`). CH005 suppresses this because the handle is `return`ed,
  so ownership passes to the caller. (Verified: no false positive emitted.)
- **llama_index's pydantic-model `__init__`s** — `SummaryExtractor`,
  `UnstructuredElementNodeParser`, `TokenTextSplitter` (both `__init__` and
  `from_defaults`) all have literal mutable defaults (`= ["self"]`,
  `= ["\n"]`) on parameters that get forwarded into a `pydantic.BaseModel`
  field. Confirmed empirically, not just by inspection: constructing two
  instances from the same default and mutating one's field never affects
  the other, because pydantic's field validation copies list/dict values
  per instance on construction, regardless of the shared default object at
  the Python signature level. Same mechanism neutralizes a
  `Document(metadata=extra_info)` call in the JSON reader. CH002 doesn't
  yet know about this (it would need to resolve whether a parameter flows
  into a pydantic field), so these are correctly-identified-by-a-human
  false positives, not something the checker itself suppresses.
- **CH007's own design, twice** — building the check surfaced two real false
  positives against agno before it was safe to ship: matching `self.foo()`
  against *any* same-named async method in the file (not just the same
  class) flagged `ZepTools.initialize` — sync — against `ZepAsyncTools.initialize`
  — async, a different class entirely, following agno's own documented
  sync/async "twin method" convention. And matching bare `foo()` by name
  alone flagged a `write` parameter against an unrelated same-named
  `async def write` 140 lines away in the same file. Both are now regression
  tests (`test_ch007_ignores_sync_twin_method_on_different_class`,
  `test_ch007_ignores_name_shadowed_by_parameter`). After fixing both, a
  scan of ~20 major Python AI/ML frameworks (agno, litellm, crewAI, mem0,
  llama_index, vllm, pydantic-ai, langchain, dspy, and others) found zero
  real CH007 instances - a real result, not a gap: same-file name matching
  by design doesn't chase cross-module calls, which is plausibly where most
  real "unawaited coroutine" bugs actually live, and mature async test
  suites likely catch same-file cases before merge anyway.
- **CH009 (llama_index)** — six chat-engine `stream_chat` methods
  (`SimpleChatEngine`, `CondenseQuestionChatEngine`,
  `ContextChatEngine`, and their multi-modal / condense-plus-context
  variants) all spawn a background thread that writes the response to
  memory, then do `chat_response.write_response_to_history_thread = thread`
  and `return chat_response` - never `thread.join()` directly. Looked like
  six real leaks. It isn't: `chat_engine/types.py` joins the thread through
  that exact attribute once the caller finishes consuming the stream
  (`self.write_response_to_history_thread.join()`). The thread is handed
  off through a *different* object's attribute, not lost. Fixed the check
  to treat assignment to any object's attribute as an intentional escape,
  not just `self.<attr>`.
- **CH010 (marimo)** — `default_table.py`'s row sorter does
  `sorted(non_none_rows, key=lambda row: row[sort_arg.by], ...)` inside
  `for sort_arg in reversed(by):`. The lambda references the loop
  variable, which is exactly the buggy shape - except `sorted()` calls the
  lambda immediately and synchronously, entirely within the current
  iteration, before `sort_arg` ever moves on. Nothing is ever stale. This
  is the single most common way a lambda actually appears inside a real
  loop (as a `key=`/`filter`-style callback, not a stored closure), so
  getting this wrong would have made CH010 fire constantly. Rewrote the
  check to require that the lambda be directly *stored* - an argument to
  `.append()`/`.add()`, the value of an assignment, or `return`ed/`yield`ed
  - rather than merely passed as an argument to *anything*.
- **`exception-chaining`, built and not shipped** — a check for `except X
  as e: raise Y(...)` with no `from e` (discards the real traceback;
  overlaps flake8-bugbear B904) worked exactly as designed and found
  **1,911 hits across the same ~20-framework corpus**. That volume is
  itself the finding: the pattern is common enough that flagging it
  everywhere would make codehound read as a noisy style linter rather than
  a tool whose every finding is defensible. Removed from the shipped check
  set rather than quietly kept at a lower confidence tier - a real design
  decision, documented here instead of just left out silently.
- **`cancelled-error-swallowed`, built and not shipped** — a check for
  `except asyncio.CancelledError: pass`, premised on "silently swallowing
  task cancellation is a bug." This one failed on more than volume: the
  **first two real hits checked, in two different frameworks, were both
  correct code**. agno's was `existing_task.cancel(); try: await
  existing_task; except CancelledError: pass` - the textbook-correct way
  to await a task's own cancellation, not a bug. letta's was an explicit
  logged recovery path, `except (asyncio.CancelledError,
  RunCancelledException) as e: logger.info(...); async for message in
  self._process_event(...)`, with the log message itself saying it was
  deliberately overriding the cancellation. Unlike exception-chaining's
  volume problem, this meant the check's underlying premise was false in a
  large fraction of real occurrences at 118 corpus hits, so it was deleted
  outright (file removed, not kept at a lower tier) rather than patched -
  a lesson from checking real hits before trusting a check that "worked"
  by its own logic.
- **CH020 (agno, two distinct false-positive shapes)** — a bare `except:`
  or unused `except BaseException:` also catches `KeyboardInterrupt`/
  `SystemExit`, so it's flagged unconditionally by default. Two real
  patterns in agno needed guards before that default was safe to ship.
  First, `agents/base.py`'s background-thread runner does `except
  BaseException as e: thread_error.append(e)`, then surfaces the caught
  exception to the consumer via a queue afterward, `finally:` guaranteeing
  the consumer never blocks - not a swallow, since the exception is
  captured and used; fixed by skipping when the bound name is referenced
  anywhere in the handler body. Second, `context/mcp/provider.py`'s
  `_ensure_session` does `except BaseException:` (no bound name at all)
  around a `_connect()` call, then resets `self._tools`/
  `self._tool_descriptions` and bare-`raise`s to propagate the original
  error after cleanup - the first guard didn't apply since there was no
  name to check, so a second guard was added: skip when the handler
  contains a `raise` anywhere in its own scope (not counting a nested
  try/except's own handler, the same scoping pitfall already solved for
  `exception-chaining` above). Fixing both cut CH020's corpus-wide hit
  count from 200+ to roughly 50, and a follow-up scan of the remaining
  hits (llama_index's event dispatcher: `except BaseException: pass`
  around every registered handler call, no logging, no re-raise) confirmed
  they're real - the check earns its keep at the same rate a well-known
  linter rule does (this is pylint's `W0702`/flake8-bugbear's `B036`
  territory), not a modeling bug like the two rejected checks above.
- **CH011 (mlflow, marimo) — two more shapes that don't need a code
  change** were found while chasing CH011 hits for PR candidates, worth
  recording even though nothing in the checker itself needed fixing:
  mlflow's `ModelRegistryStoreRegistry._get_store_with_resolved_uri` is
  `@lru_cache`'d on a class that's instantiated exactly once, as a
  module-level singleton (`_get_store_registry()`'s `if
  _model_registry_store_registry is not None: return ...` guard) — the
  cache keeping `self` alive forever is meaningless when the singleton
  was always going to live for the process's whole lifetime anyway.
  marimo's five hits (`calculate_top_k_rows`, `_apply_filters_query_sort_cached`,
  `get_config` ×2) all carry `# noqa: B019` — flake8-bugbear's own rule
  number for exactly this pattern — meaning marimo's maintainers already
  reviewed and deliberately accepted each one. Filing PRs for either
  would mean "fixing" code the projects have already correctly reasoned
  about; recorded here instead as real corpus signal a future CH011 guard
  (skip a singleton-shaped class, skip a line already carrying a
  suppressing `noqa`) would need to account for, without changing today's
  shipped behavior speculatively.
- **CH011 (dspy), a third shape that DID get a guard** — dspy's `Image`
  (a pydantic model representing an image) caches `format()` with
  `@lru_cache(maxsize=32)`. Unlike the leak cases above, `Image` sets
  `model_config = ConfigDict(frozen=True)`, and a frozen pydantic model is
  hashable and equal *by its field values*, not by identity. Checked
  directly rather than assumed: constructing two separate `Image`-like
  instances with the same field value and calling the cached method on
  both, only the *first* call actually runs the method body - the second
  is served from the first instance's cache entry without the second
  instance ever being inserted as a key. The cache is bounded by
  `maxsize` distinct field-value combinations, exactly like caching a
  pure function by value would be - not a per-instance leak. Unlike the
  mlflow/marimo shapes above, this one *is* staticly detectable (a frozen
  stdlib `@dataclass` or a pydantic `model_config=ConfigDict(frozen=True)`
  / `class Config: frozen = True`), so CH011 now skips it. Verified
  against the real dspy file (no longer flagged) and a full corpus
  rescan (only dspy's hit disappeared; the other 8 corpus repos' CH011
  hits are unaffected, confirming the guard doesn't over-suppress mutable
  classes).
- **CH011 (litellm), a red herring worth recording** — before trusting
  litellm's `Router` hit, checked whether `Router` was a singleton like
  mlflow's registry (it isn't: the proxy reassigns the global `llm_router`
  via `global` in about ten places, a real hot-reload path). Constructing
  a `Router` and dropping every reference to it still didn't collect it
  even with the CH011 fix applied - `gc.get_referrers` showed it was also
  held by bound-method callbacks appended into global `litellm.
  success_callback`/`failure_callback` lists. That turned out to be a
  *different*, already-known issue with its own documented fix:
  `Router.discard()`, a "pseudo-destructor" that exists specifically to
  unhook those callbacks. Confirmed the two were genuinely independent by
  testing all four combinations: without `discard()` the Router leaks
  regardless of the CH011 fix (expected, `discard()` is required either
  way); with `discard()` called, the unfixed code still leaks and the
  fixed code doesn't. That's what makes the CH011 fix real rather than
  redundant with calling `discard()`.
- **CH016 (vllm), found and fixed the day it shipped** — the very first
  real-corpus scan of the brand new `unclosed-socket` check turned up
  three hits in vllm's distributed process-group rendezvous code, and all
  three were false positives in a shape CH005 (the check CH016 was
  modeled on) never had to handle: a socket handed off by being `return`ed
  *inside a tuple* (`return port, s`, not the bare name), one collected
  into a list that's itself `return`ed (`socks.append(s)` then `return
  ports, socks`), and one passed straight into another function that takes
  ownership of it (`create_tcp_store(host, port,
  listen_socket=listen_socket)`). Files aren't handed off this way nearly
  as often as sockets are in networking/rendezvous code, which is likely
  why CH005 never needed these guards. Fixed by treating a name as escaped
  if it's returned as part of a tuple/list, or passed as an argument to
  any call (as opposed to being the receiver of a method call on itself,
  like `s.bind(...)`) — verified against the exact three vllm sites, and a
  full corpus rescan afterward found zero remaining CH016 hits across all
  ~29 frameworks, a real result rather than a gap (sockets not handed off
  this way and never closed appear to be genuinely rare here).
- **CH021, two false positives found minutes apart** — the first
  real-corpus scan found vllm's `from .chunk import chunk_gated_delta_rule`
  flagged as a removed-stdlib-module import. It's a relative import of
  vllm's own local `chunk.py` sibling file, not the removed stdlib
  `chunk` module - `ast.ImportFrom.module` is `"chunk"` either way, and
  only the separate `level` field (the leading-dot count) distinguishes
  them. Fixed by requiring `level == 0`, rescanned, and immediately found
  a second one in agno: `try: import imghdr except ImportError: import
  filetype`, a real, deliberate fallback that already anticipates the
  exact removal being flagged, not a bug waiting to happen. Fixed by
  skipping an import inside a `try:` body whose `except` catches
  `ImportError` or anything broader. A full corpus rescan after both
  fixes found zero remaining CH021 hits across all ~29 frameworks.
- **CH025, a chained-comparison bug in the check itself** — the first
  real hit was litellm's `if "usage" in response_obj is not None:`,
  flagged as comparing a string literal with `is`. Wrong reason: `ast.
  Compare` bundles every operand and every op of a chained comparison
  into one node, and the initial implementation checked "does *any*
  operand look like a literal" and "does *any* op look like Is/IsNot"
  independently - true here, but the literal (`"usage"`) is the left
  side of `in`, and the `is not` is actually comparing `response_obj`
  against the allowed singleton `None`. Fixed by walking the chain as
  adjacent `(left, op, right)` triples, so each op is only checked
  against its own two operands.
- **CH027 and CH028, the same missing escape found twice** — both
  checks initially handled "returned" and "passed as an argument" but
  not "stored as any object's attribute," the exact escape CH009/CH016
  already needed. CH027's first real hit was dspy's `lm.process =
  process` (the `Popen` handed to a different object, reaped later
  through a separate `terminate_process(lm.process)` call). CH028's
  daemon-escape gap (missing entirely, not just the attribute case) was
  found the same way in weaviate-python-client's watchdog timer
  (`_timeout_timer.daemon = True` after construction). Both fixed by
  reusing the exact guards already proven for CH009/CH016.
- **CH028, the name-collision guard that existed but wasn't reused** —
  the first corpus scan came back with ~30 hits, almost entirely in
  agno, which turned out not to use `threading.Timer` anywhere: `from
  agno.utils.timer import Timer` is agno's own unrelated stopwatch
  class, called as `Timer()` with zero arguments (real `threading.
  Timer` requires `interval` and `function` and would raise `TypeError`
  immediately). CH018 and CH022 had already solved this exact class of
  problem - a bare name is only trusted when the real module actually
  imported it - minutes earlier in the same session; CH028 just didn't
  apply it the first time. Fixed by requiring `from threading import
  Timer` before trusting a bare `Timer(...)` call.
- **CH029, a real find that revealed a real precision gap** — the first
  corpus scan flagged letta's `_dispatch_callback`: `except Exception as
  e: result["error"] = str(e)` followed by `finally: return result`.
  Read the code before trusting the check: the comment right there says
  "callback failures should not affect job completion," and the handler
  genuinely never re-raises anywhere - by the time `finally` runs, the
  exception (if any) has already been fully absorbed, so the `return`
  isn't discarding anything live. Fixed by skipping a `try` whose
  `except` clauses never re-raise in their own scope (reusing the exact
  nested-handler-boundary walk built for CH020's `raise`-detection).
  Verified the guard doesn't over-suppress by checking a second letta
  hit that *does* re-raise (`except BaseException as e: <log>; raise
  self.llm_client.handle_llm_error(e, ...)` then `finally: if not
  stream_started: return`) - still flagged after the fix, though a
  closer read showed `stream_started` is unconditionally `True` with no
  other assignment in the function, making that specific `return`
  currently dead code rather than a live swallow. Recorded honestly
  rather than reported as an active bug - see "Real bugs found, not yet
  filed" below for the full letta story.

- **CH010's `def` extension, scoped to what was actually verified** —
  extending the check to nested `def`s (the same closure-capture bug as
  the lambda case, just a statement instead of an expression) reused the
  lambda logic's storage guard rather than a new one: a `def`'s *name*,
  not the `def` itself, has to show up in a storage position later in
  the loop body. Deliberately left narrower than it could be - only
  direct top-level statements of the loop body are checked, not a `def`
  nested inside an `if`/`try` inside the loop - rather than guess at a
  more general walk without a corpus hit to verify it against.
- **CH032, checked for the obvious "what if it's a factory" objection
  before shipping** — the concern with any "call as a default is
  suspicious" rule (this is bugbear B008's exact framing) is that a lot
  of call-as-default patterns are deliberate, cached-at-import-time
  configuration, not a bug. Restricting the curated function list to
  ones where "the same value forever" can never be intended (the current
  time, a random number, a fresh UUID) sidesteps that objection entirely
  - there's no legitimate reading of `def f(id=uuid.uuid4()):` where a
  fixed, shared UUID across every call is what the author wanted.
- **CH033's punctuation-only exclusion, added after the first corpus
  scan came back mostly false positives** — the first pass (any
  multi-character string argument, matching bugbear B005's own rule
  exactly) came back with 136 hits across ~29 frameworks; a full read
  showed the overwhelming majority - `.strip('\r\n')`, `.strip('[]')`,
  `.strip('\'"')`, `.lstrip('│ ├└─')` (box-drawing tree glyphs in
  marimo/agno) - are deliberate, correct uses of the character-*set*
  semantics, not a substring mistake. Every genuine mistake in that scan
  shared one trait the safe cases didn't: at least one letter or digit
  in the argument (`data:`, `/v1`, `THREAD#`, `json`). Added that filter
  plus a same-character-repeated exclusion (`.strip('```')` is just
  backtick, no ambiguity), which cut the hit count to 18 - all 18 read as
  genuine mistakes on inspection, including huggingface_hub's
  `line.lstrip("data:").rstrip("/n")`, where the second call is almost
  certainly a typo for the newline escape `"\n"`.

- **CH034, CH035, CH036 - verified in a REPL before any AST code was
  written, not just reasoned about.** `raise "x"`, `raise None`, `raise
  f"x"`, `raise (1, 2)`, and `raise {1: 2}` were each actually executed
  and confirmed to raise `TypeError: exceptions must derive from
  BaseException` - the same failure for every literal shape, which is
  why CH034 flags all of them with one check instead of one per shape.
  `except ():` was confirmed to let a real `ValueError` propagate past
  it untouched. `os.environ = {}` was confirmed, via a real
  `subprocess.run` call, to leave a variable set moments earlier still
  visible to a spawned child process even though `os.getenv` in the
  same process reports it gone - the two views genuinely disagree, not
  just in theory. Unlike CH032/CH033, none of the three needed a
  precision-narrowing pass after the first corpus scan (2 real hits,
  zero false positives, across ~29 frameworks) - there's no legitimate
  Python construct any of them could be mistaken for.
- **CH038's two container-literal false positives, both found by
  reading real corpus hits, both fixed with one rule.** The first pass
  matched bugbear's own B018 exactly - flag any `List`/`Set`/`Dict`/
  `Tuple` literal used as a bare statement, unconditionally. Two real
  corpus hits showed why that's wrong: HuggingFace `datasets`'
  `arrow_dataset.py` has `indices.pop(0), tasks.pop(0)` - a tuple of
  two calls, each mutating a list; the tuple result is discarded, but
  the pops are the entire point. scikit-learn's `_covtype.py` has
  `X, y` inside `try: ... except NameError:` - deliberately probing
  whether those two names are already bound in the enclosing scope,
  exploiting the `NameError` a bare name reference raises when it
  isn't. Neither is "forgot to assign, return, or assert" - both
  compute nothing themselves but still do something through their
  elements. Fixed with one rule that explains both: a container
  literal is only flagged if every element, recursively, is itself a
  constant - a `Name`, `Call`, or `Attribute` anywhere inside means the
  container might not be side-effect-free, so it's skipped rather than
  guessed at.
- **CH038's builtin-shadowing false positive, found in langgraph's
  CLI.** `with Progress(message="Pulling...") as set:` followed by
  `set("Building...")` a few lines later - `set` is a local variable
  bound by the `with ... as`, a status-setter callback, not the
  builtin `set` type. The curated "pure builtin" list this check
  matches against is exactly the kind of short, common identifier
  real code reuses. Fixed by scanning the whole file once for every
  name that's ever bound anywhere (assignment target, parameter,
  `with ... as`, `except ... as`, `def`/`class` name, import alias)
  and refusing to trust a "pure builtin" call whose name shows up in
  that set.
- **CH038's notebook-cell false positive - the single largest false-
  positive cluster found this session, and the reason the guard needed
  a second pass to actually work.** marimo's own `_smoke_tests/`
  directory accounted for over half of the very first corpus scan's 82
  hits: a bare literal/call as the last meaningful statement of an
  `@app.cell`-decorated function is marimo's own convention for the
  cell's displayed output, not a forgotten return. The first version of
  the guard (skip only the literal last statement of the function body)
  missed roughly a third of these, because marimo *always* closes a
  cell with a `return` - bare `return` when nothing is exported,
  `return x, y` when something is - so the display statement is
  usually the one right *before* that trailing `return`, not the
  actual last statement. Two real shapes proved this: `1\n    return`
  (nothing exported) and `refresh\n    ...\n    len(spans)\n    return
  file_path, spans` (both a display value and exported names in the
  same cell). Fixed by stripping a trailing `Return` before checking
  "is this the last statement." A *different* notebook convention -
  sphinx-gallery's plain `# %%`-comment-delimited scripts, found in
  optuna's tutorials - has no AST-visible marker at all, so those
  remain an accepted, undetected false positive.
- **CH038's one accepted, undetectable-via-AST limitation, shared with
  bugbear's own B018.** A call to a curated "pure" builtin used
  specifically to probe whether it raises - `try: repr(x) except
  Exception:` to check for a broken `__repr__`, the same idiom already
  excluded `int(s)` for (a validation call, discarding the result on
  purpose) - still gets flagged, because telling "used for its
  exception" apart from "result forgotten" needs tracing the enclosing
  `try`/`except`, which risks silently suppressing the exact "forgot to
  assign" bug this check exists to catch. Real instances found and left
  flagged: letta's `otel/tracing.py` (`str(value)`, probing for a
  broken `__str__`) and scikit-learn's `estimator_checks.py`
  (`repr(estimator)`, probing for a broken `__repr__`).
- **CH039, verified before any AST code was written, the same way
  CH034-CH036 were.** Five threads, each doing `with threading.Lock():`
  around an 0.01s `time.sleep`, finished in ~0.013s total when run
  under a per-call, never-shared lock - not the ~0.05s they'd take if
  the lock were actually serializing them. The "critical section" ran
  fully concurrently, proving the lock did nothing. Zero corpus hits
  across ~29 frameworks - an honest null in the same category as CH008
  and CH035, not evidence the check is wrong, just that well-maintained
  codebases don't happen to make this specific mistake.
- **CH040-CH044, CH048: five checks with zero false-positive risk,
  verified directly, that needed no narrowing pass.** `pytest.raises(Exception)`
  was confirmed to swallow a bare `assert False` from inside the block
  (CH040). `contextlib.suppress()` with no arguments was confirmed to
  let a real `ValueError` through untouched, the same shape as CH035
  one API up (CH041). A duplicate `except ValueError:` clause was
  confirmed to leave the second one dead - only the first handler ever
  runs (CH042). `float('nan') == float('nan')` was confirmed `False`,
  and so was every other NaN equality comparison tried (CH043). A
  nested function doing `count += 1` without `nonlocal count` was
  confirmed to raise `UnboundLocalError` on the very first call
  (CH044). `assert (x, "message")` was confirmed to always pass,
  matching the `SyntaxWarning: assertion is always true` CPython's own
  compiler already emits for it (CH048). All five came back with zero
  or single-digit corpus hits - CH040's 29 hits are the exception,
  entirely in test files using the exact `pytest.raises(Exception)`/
  `assertRaises(Exception)` anti-pattern the check describes.
- **CH045/CH046 compare AST literals by real Python equality, not
  `(type, value)` pairs - a precision decision made before any corpus
  scan, not after one.** `1`, `1.0`, and `True` genuinely collide as
  the same dict key or set element at runtime (verified directly:
  `{True: 1, 1: 2}` is `{True: 2}`); comparing by `(type(value), value)`
  instead would have missed exactly that collision. Both checks share
  one `literal_value()` helper in `core.py` for this reason, rather
  than duplicating the comparison logic per check.
- **CH047's design is deliberately narrow, matching the discipline of
  not guessing at partial protection.** It only recognizes a bare
  top-level `yield` in the function body, or one inside a `try` with no
  `finally`, with something else after it at that same block level -
  it doesn't try to reason about an `except` clause that partially
  protects the cleanup, or a `yield` nested inside an `if`/`for`. A
  generator with exactly one `yield` and nothing after it is
  unconditionally safe and untouched by this check, by construction.
- **CH049, three real false positives on the first corpus scan, all
  sharing one root cause, fixed with one rule.** vllm's `shm_broadcast.py`
  has `create_from_handle`, a `@staticmethod` factory that opens with
  `self = MessageQueue.__new__(MessageQueue)` - a well-known "manually
  build the instance" idiom, so every later `self.x = ...` is
  completely ordinary. litellm's `proxy/utils.py` has `cls = type(resolved)`
  partway through an unrelated static method, reusing the name for a
  plain local variable. agno's `bedrock.py` reads `cls` only inside
  `{cls.__module__... for cls in type(client).__mro__}` - a set
  comprehension's own `for cls in ...`, Python 3's own separate
  comprehension scope, unrelated to the enclosing method. All three
  bind the name to *something*, just not via a parameter - fixed by
  checking for *any* local `Store`-context binding of the name
  anywhere in the method's own scope (a plain assignment, a
  comprehension's generator target, anything short of a further-nested
  function), not just a parameter list. Zero hits after the fix.
- **CH049 again, a second scan across a wider set of frameworks found
  two more real false positives - both about scope in ways deeper than
  the first pass.** celery's `test_app.py` stacks
  `@staticmethod` / `@self.app.task(shared=False)` on the same
  function - `self` there is in the *decorator expression*, evaluated
  in the enclosing test method's scope before `@staticmethod` ever
  applies, not inside the static method's own body; the check was
  walking the whole `FunctionDef` node, decorator list included, not
  just the body. pytest's `pytester.py` defines a whole class - and a
  `@staticmethod` on it - *inside* another method, and that nested
  method's body reads `self`, which resolves via an ordinary closure
  to the *outer* method's `self` (verified directly: a class defined
  inside a method, with a `@staticmethod` reading `self`, correctly
  returns the outer instance's attribute - `@staticmethod` doesn't
  change how Python resolves free variables, only how the method is
  called). Fixed by scanning only `node.body` for suspect names, and
  by skipping entirely when the `@staticmethod`'s own class is itself
  nested inside a function - too much real closure ambiguity to guess
  at safely. Zero hits across the full combined corpus after both
  fixes.
- **CH050, 18 real hits collapsed to 1 by recognizing one specific,
  extremely common idiom.** The first pass (bugbear's actual B035
  scope: does the key reference any `for`-loop target) matched
  `{doc_hash: doc_id for doc_id, doc in items.items() if (doc_hash := doc.get("doc_hash"))}`
  in llama_index, vllm, agno, pydantic-ai, and litellm - all the exact
  same shape, filtering *and* deriving the key in the same walrus
  expression inside the generator's `if` clause. `doc_hash` never
  appears in the `for` target, but it's freshly bound on every
  iteration all the same. Fixed by also collecting walrus targets from
  every generator's `iter` and `ifs`, not just its `for` target, as
  names that "vary per iteration." The one hit that survived - AutoGPT's
  `execution.py`, a `{"payload": exec.input_data.get("payload") for exec
  in ... if <webhook-type filter>}` - is honestly ambiguous: the
  literal key is unusual, but sits right next to an identically-styled
  comprehension with a real per-item key, suggesting the author expects
  at most one matching item and is using the fixed key deliberately.
  Left flagged rather than special-cased away, since "expects at most
  one match" is exactly the kind of assumption worth a second look.

**Three checks built, corpus-scanned, and rejected outright this same
round - not shipped, not narrowed, deleted:**

- **`assignment-from-sort-or-reverse`** (`x = some_list.sort()` captures
  `None`, since `.sort()`/`.reverse()` mutate in place) came back with
  78 corpus hits, and reading through a broad sample found zero real
  `list.sort()` bugs - every single one was a *different* `.sort()`
  with a different contract: `np.sort(x)` (NumPy, returns a new array,
  takes the array as an argument rather than a receiver), PyMongo's
  `Cursor.sort()` (returns the cursor for chaining), HuggingFace
  `Dataset.sort()` (returns a new sorted Dataset), polars/pandas
  `DataFrame.sort()`, and several hand-written `SomeUtils.sort(items, key)`
  static helpers. There's no AST-only way to tell "this `.sort()` is
  really `list.sort()`" from all of these without type inference, so
  the premise itself doesn't hold at real-world scale - rejected, not
  narrowed.
- **`enum-duplicate-value`** (two `Enum` members sharing a value become
  silent aliases) came back with 6 hits, and every single real-code
  instance checked (AutoGPT's `AnthropicModelName`, letta's
  `PrimitiveType`, vllm's `Mxfp4MoeBackend`) was an explicitly
  commented, deliberate "rolling alias" or "legacy name during a
  rename" pattern - three for three, matching the exact "the first
  real hits checked turned out to be correct code" rejection criteria
  used for `cancelled-error-swallowed` earlier. Enum aliasing is a
  well-known, intentional technique, not an accident waiting to be
  caught.
- **`eq-without-hash`** (a class defining `__eq__` without `__hash__`
  becomes unhashable, even with a base class `__hash__`) came back with
  162 hits - every sample checked, across mlflow's entire `entities/`
  module and value-object classes in vllm, `datasets`, dspy, and
  langchain, was a hand-written value/result object that was never
  intended to be hashable in the first place, the exact same tradeoff
  `@dataclass` makes on purpose (already excluded from this check for
  that reason). Technically correct about Python's behavior on every
  single hit; practically indistinguishable from `@dataclass`'s own
  accepted default at the volume real code actually produces it.
  A follow-up replacement, `abstract-stub-missing-decorator` (an empty
  method on an ABC that isn't `@abstractmethod`, sitting next to real
  ones - flake8-bugbear's B027), was built, scanned, and rejected the
  same way: 142 hits, and both samples read in full (AutoGPT's
  `AppProcess.cleanup()`, mlflow's `RateLimiter.report_throttle()`)
  had a docstring literally saying "Implement this on a subclass" or
  "No-op by default" - the classic, intentional Template Method
  "optional hook" pattern, not a forgotten decorator.
- **CH011, a real precision gap found by scanning a wider corpus long
  after the check shipped - not a new check, a live one getting more
  scrutiny.** The original design trusted any decorator literally named
  `lru_cache`/`cache`, matched by bare attribute name only. Scanning
  SQLAlchemy (not part of the original ~29-framework corpus) turned up
  ~94 hits concentrated in its dialect classes (`PGDialect`,
  `MySQLDialect`, …), all using `@reflection.cache` on reflection
  methods (`has_table`, `get_columns`, …) - same bare attribute name as
  `functools.cache`, a completely different decorator. Read its actual
  implementation (`sqlalchemy/engine/reflection.py`): it only caches
  when the *caller* passes an explicit `info_cache` dict keyword
  argument, and that dict is the caller's own object, not anything
  attached to the function or retaining `self` the way
  `functools.lru_cache`'s real, persistent, function-attached cache
  does. Fixed by only trusting a bare `lru_cache`/`cache` name when
  `from functools import lru_cache`/`cache` was actually seen in the
  file (or the full `functools.lru_cache`/`functools.cache` attribute
  form) - the same "don't trust a bare name without seeing where it
  came from" discipline CH018/CH022/CH028/CH041 already use. Cut
  SQLAlchemy's hits from ~94 to the ones actually using real
  `functools.lru_cache` (still present, on long-lived per-engine
  dialect singletons - the same "leak is meaningless, the instance was
  always going to live for the process lifetime" category as mlflow's
  registry.py, not a new bug).
- **CH009/CH012/CH028, a missing escape shared by three checks that
  CH016/CH027/CH031 already had.** All six "floating primitive" checks
  are meant to treat a thread/process/timer/socket/subprocess/pool
  handed off - returned, stored as any object's attribute, or passed
  as an argument to another call - as intentional, not a leak. CH016
  (sockets) and CH027 (subprocesses) and CH031 (pools) already
  recognized "passed as an argument to any call" as an escape; CH009
  (threads), CH012 (processes), and CH028 (timers) only recognized
  direct attribute assignment (`self.x = handle`), missing the
  syntactically different "appended to a collection that's itself an
  attribute" shape (`self.processes.append(process)`). Found via a
  real false positive in uvicorn's multi-worker supervisor:
  `self.processes.append(process)` right after `.start()`, with a
  separate `join_all()` method elsewhere in the same class iterating
  `self.processes` and joining every one - confirmed by reading that
  method, not assumed. Fixed by porting the exact same "passed as an
  argument to any call" check into all three.
- **CH051, three real false-positive shapes fixed across three passes, all
  found by reading actual corpus hits.** The first pass flagged
  transformers' `configuration_utils.py::to_dict` - `for key, value in
  output.items(): ... output[key] = value` - re-assigning a key the loop
  is *already on* can never change the dict's size, so it can never
  trigger the `RuntimeError` this check exists to catch; verified
  directly. Fixed by tracking the loop's own current-key binding and
  skipping a `Store`-subscript keyed by exactly that name - which then
  surfaced a second, narrower shape in pydantic's `json_schema.py`:
  `if key == '$ref': schema['$ref'] = ...`, re-assigning the *same*
  key but spelled as the literal an enclosing `if` already proved it
  equals, not as the bound name directly - fixed by tracking literals an
  enclosing `if`/`elif` test proves equal to the loop's key, scoped to
  that branch's own body only. The second pass flagged transformers'
  mamba `load_hook` - `for k in state_dict: if "embedding." in k: ...;
  break` - verified directly that Python's dict iterator only raises on
  its *next* `__next__()` call, so a mutation immediately followed by an
  unconditional `break` never gets the chance; fixed by checking whether
  the very next statement in the same block is a `Break`. The third pass
  flagged langgraph's own subgraph-search loop -
  `for c in candidates: ... candidates.extend(c.steps)` - a deliberate,
  verified-safe growing-worklist pattern: appending to the *end* of a
  list mid-iteration doesn't raise and the loop correctly sees the new
  items, unlike a set's `.add()`, which still raises immediately (both
  verified directly) - fixed by dropping `append`/`extend` from the
  mutating-methods list entirely, keeping `insert`/`remove`/`pop` and the
  set-only methods.
- **CH052, the single largest false-positive count this project has ever
  had on a first pass - over 2,000 hits - fixed by requiring a second
  signal, then narrowed once more for a real idiom.** The original design
  flagged any bare `args`/`kwargs` name matching the enclosing function's
  own variadic parameters, passed anywhere as a plain positional argument.
  Reading real hits found the overwhelming majority were `len(args)`,
  `bool(kwargs)`, and similar - completely ordinary uses of the collection
  *itself* as a value, not a dropped star; `len`/`bool`/etc. don't accept
  `*args`, so there was never a star to drop. Fixed by only firing when
  the *same call* already correctly unpacks something else with a star -
  a call mixing real unpacking with a bare name of the same kind is a far
  stronger signal that a `*`/`**` fell out partway through writing it.
  That cut the count to 2, one of which was letta's own decorator helper:
  `dict(_kwargs, **kwargs)` - `dict()`'s constructor (and `.update()`) is
  explicitly designed to accept a mapping as its first positional
  argument, the one case where mixing a bare name with real unpacking in
  the same call is completely correct. Fixed by excluding `dict(...)`/
  `.update(...)` calls specifically.
- **CH053, a 58-hit false-positive cluster in transformers, all the same
  copy-pasted idiom, cut to zero by requiring proof of later mutation.**
  The first pass flagged `processed_grids[shape] = [[grid_t, grid_h,
  grid_w]] * batch_size`, repeated near-identically across dozens of
  model image processors (glm4v, qwen2_vl, lfm2_vl, and more) - a
  broadcast per-batch-item metadata literal that feeds straight into a
  dict or a tensor constructor and is never indexed into a second time.
  The aliasing is real but inert: nothing ever asks two of the "rows" to
  be independent. Fixed by only firing when the assigned name is *later*
  subscripted with a nested store (`name[i][j] = ...`) in the same block -
  the shape that actually exercises the aliasing - which also surfaced a
  detection gap in the check's own canonical example: `[[0] * cols] *
  rows` wasn't matched at all, since the inner element is a `BinOp`
  (`[0] * cols`), not a bare list literal; fixed by recognizing a
  list-repetition `BinOp` as "mutable" too.
- **CH054, a real false positive found in pydantic's own base
  `__repr_args__`, the textbook-correct way to handle it.**
  `Representation.__slots__ = ()`, and `__repr_args__` does `if not
  attrs_names and hasattr(self, '__dict__'): attrs_names =
  self.__dict__.keys()` - a `hasattr` guard immediately before the
  access, correctly handling subclasses that may or may not add
  `__dict__` back via their own, different `__slots__` (verified
  directly: a subclass without `__slots__` at all does get a real
  `__dict__`, despite the base declaring `__slots__ = ()`). Fixed by
  walking up from a found `self.__dict__` access to check whether it
  sits inside an `if hasattr(self, '__dict__'):`-guarded (optionally
  `and`-chained) block.
- **CH059, one very broad detection redesign after four different
  legitimate installation shapes were found, each on its own corpus
  pass.** The original design only recognized `return wrapper` verbatim.
  llama_index's own tracing decorator returns
  `async_wrapper if inspect.iscoroutinefunction(func) else wrapper` - a
  ternary choosing between two `@wraps`-decorated inners. agno's `hook`
  decorator assigns `wrapper = async_wrapper if ... else sync_wrapper`
  then `return wrapper` - the wrapped name reassigned to a different one
  before being returned. transformers' `wrap_init_to_accept_kwargs`
  does `cls.__init__ = __init__` - installed via attribute assignment,
  never `return`ed at all. dspy's own cache decorator has a
  `process_request` helper, *also* decorated with `@wraps(fn)`, called
  only from inside `sync_wrapper`/`async_wrapper` - never returned itself,
  but not orphaned either. Rather than keep enumerating installation
  shapes one at a time, redesigned around a strictly weaker, more
  defensible bar: is the wrapped name referenced *anywhere else at all*
  in the outer function, by any mechanism - a return, a reassignment, an
  attribute target, or a sibling helper's call? Only a name built with
  `@wraps` and never mentioned again anywhere still gets flagged. That one
  redesign resolved all four shapes at once and cut the corpus count from
  51 to 0.
- **CH069, all 7 first-pass hits turned out to be the correct, defensive
  pattern - independently, in four unrelated projects.** The original
  design flagged any `ContextVar(..., default=mutable_literal)`. Reading
  every real hit found the same idiom every time: letta's `log_context.py`
  and llama_index's `callbacks/base.py` both do `current =
  var.get().copy(); current[...] = ...; var.set(current)`; qdrant-client's
  `context_headers.py` does `merged = {**current, **extra_headers};
  var.set(merged)`; pydantic-ai's `function_signature.py` only ever reads
  via `var.get().get(name, name)`, a read-only dict lookup, never a
  mutation. None of the four ever mutate the shared default in place -
  they copy or spread first, then `.set()` the result back, which is
  exactly the safe pattern this check exists to tell apart from the
  broken one. Fixed by requiring proof of an actual in-place mutation on
  the un-copied `.get()` result (`var.get().append(...)`, `var.get()[k] =
  v`) anywhere else in the same module before flagging - cut the corpus
  count from 7 to 0, while the check still catches the genuinely unsafe
  shape directly (verified with a synthetic repro before and after).
- **CH075 (`repr-calls-str-recursion`), 6 first-pass hits, all the same
  base-class gap.** The check's premise - `str(self)` inside `__repr__`
  with no `__str__` defined recurses into `object`'s default `__str__`,
  which falls back to `__repr__` - is only true when nothing *else* in
  the MRO already provides a real `__str__`. pydantic's own
  `PlainRepr(str)` does `def __repr__(self): return str(self)` with no
  `__str__` of its own, and was flagged - but `PlainRepr` subclasses
  `str`, which already has its own non-recursive `__str__`, so
  `str(self)` there just returns the string's content directly and
  never touches `__repr__` at all. Verified directly with a synthetic
  `str`-subclass repro. Fixed by requiring the class to have *no* base
  classes at all (a pure `object` subclass) - any base, builtin or
  custom, might supply its own safe `__str__` that a single-file AST
  check can't see - cutting the corpus count from 6 to 0.
- **CH079, four separate dataclass field-ordering exemptions found
  across three corpus passes, cutting the count from 133 to 0.**
  `@dataclass(kw_only=True)` on the *class* (not just per-field) makes
  every field keyword-only - found in vllm's `ServeContext`, which the
  first pass missed entirely since it only checked `field(kw_only=True)`
  on individual fields. `field(init=False)` removes a field from
  `__init__`'s parameter list altogether, so the ordering rule never
  applies to it - found in huggingface_hub's `_BucketCopyFile`, where
  `mtime: int = field(init=False)` follows a defaulted field and was
  flagged even though it raises nothing (verified directly). A
  `ClassVar[...]`-annotated attribute isn't a dataclass field at all -
  `@dataclass` explicitly skips it when building `__init__` - found in
  vllm's tensorizer config, where `_fields: ClassVar[tuple[str, ...]]`
  with no value, sitting after several defaulted fields, was wrongly
  treated as a bare required field. And `dataclasses.KW_ONLY` (the
  sentinel form, `_: KW_ONLY`) switches every field declared *after* it
  to keyword-only mid-class, without needing `kw_only=True` anywhere -
  found in pydantic-ai's `BaseToolReturnPart` and two more classes in
  the same file. Each was verified directly (constructing the class and
  confirming no `TypeError`) before being added as a guard.
- **CH081/`slots-conflicts-class-variable`, pydantic's own `BaseModel`
  sidesteps the rule its own metaclass would otherwise trigger.**
  `BaseModel` declares `__slots__` containing `__pydantic_extra__` and
  also gives that name a class-level value (`= NoInitField(...)`), which
  under plain `type` construction is exactly CH081's target shape - but
  `BaseModel` is built with `metaclass=ModelMetaclass`, which rewrites
  the class namespace before `type.__new__` ever sees it, so the
  conflict never actually fires (confirmed: pydantic imports and works
  fine). A custom metaclass can do this kind of namespace rewriting for
  any class, so there's no way to know from the AST alone whether a
  given conflict is real. Fixed by excluding any class with a
  `metaclass=` keyword - cut the corpus count from 3 to 0.
- **CH085 (`decorator-missing-functools-wraps`), three rounds of
  narrowing, 210 → 182 → 118 → 102 hits, each round finding a distinct
  legitimate pattern the previous bar didn't rule out.** Round one: the
  call-detection walk descended into further-nested functions, so a
  three-level decorator-with-arguments pattern (litellm's
  `timeout(timeout_duration, exception_to_raise)` → `decorator(func)` →
  `wrapper(*a, **kw)`, where only `wrapper` actually has `@wraps` and
  needs it) misattributed `wrapper`'s own calls up to `decorator`, which
  is just a factory. Fixed by scoping the call-walk to each function's
  own top-level statements. Round one also missed two other legitimate
  identity-preservation mechanisms: agno's `make_bound_method` sets
  `bound.__name__`/`__doc__` by hand instead of decorating, and mlflow's
  autologging safety wrappers `return update_wrapper_extended(safe_function,
  function)` - a `functools.update_wrapper` call instead of the
  decorator form. Round two: "calls any outer parameter" was too broad
  - vllm's `env_list_with_choices(env_name, default, choices,
  case_sensitive)` has an inner function that calls `choices()`, a
  validator being invoked, not anything being wrapped; and
  llama_index's `get_function_tool(output_cls)` passes its inner
  `model_fn` as `fn=model_fn` into a `FunctionTool.from_defaults(...)`
  call that already takes `name=`/`description=` explicitly, so nothing
  about `model_fn`'s own identity is ever consulted. Fixed by requiring
  the wrapped parameter to be the outer function's *first* parameter
  (the idiomatic `def decorator(func):` convention) and requiring a
  *direct* return (`return wrapper`, not merely referenced somewhere
  inside a larger returned expression). Round three: litellm's own
  `_get_tiktoken_count_function(encode_length, chunk_size)` builds
  `count_tokens(text)`, which calls `encode_length(text[start:start +
  chunk_size])` - a real, differently-behaved function (chunking and
  summing) that merely *uses* `encode_length` as an ingredient, not a
  transparent stand-in for it; nothing about `count_tokens` losing
  `encode_length`'s `__name__` would even make sense, since
  `count_tokens` already has its own, deliberately chosen name. Fixed
  by requiring the call to forward at least one of the inner function's
  own parameters unchanged (`*args`/`**kwargs` unpacked straight
  through, or a same-named argument passed as-is) - the hallmark of a
  transparent pass-through wrapper, as opposed to a closure that merely
  calls the parameter as one ingredient among several. This narrowing
  is deliberately not airtight against every remaining edge case (a
  function with one fast-path branch that happens to be a bare
  pass-through, but different overall behavior elsewhere, can still
  slip through) - accepted as a reasonable stopping point after three
  rounds of real, verified fixes, rather than chasing diminishing
  returns on an increasingly fragile heuristic.

**Two checks this round independently rediscovered rejections already
documented above, using different real-world evidence, before this file
was re-read - itself worth recording as a sign the discipline holds up
without needing to be re-taught:**

- **`enum-implicit-alias`** (two `Enum` members sharing a literal value
  become a silent alias) came back with 6 corpus hits, and all three
  distinct real-code instances checked were explicitly documented,
  deliberate aliases: AutoGPT's `AnthropicModelName` has `CLAUDE_SONNET
  = "claude-sonnet-4-6"` under a `# Rolling aliases (point to latest)`
  comment, vllm's `Mxfp4MoeBackend` has `AITER = "AITER_MXFP4_BF16"`
  under `# Keep the legacy name as an alias while the ROCm split
  backend rename settles`, and letta's `PrimitiveType` has `FOLDER =
  "source"` / `SOURCE = "source"` under `# Note: folder IDs use "source"
  prefix for historical reasons`. Same conclusion, same discipline, as
  `enum-duplicate-value` above - rejected, not narrowed.
- **`bare-except-swallows-cancelled-error`** (a bare `except:`/`except
  BaseException:` around an `await`, with no `raise` anywhere in the
  handler, swallows `asyncio.CancelledError`) came back with 70 hits,
  and all four samples read were deliberate: AutoGPT's executor
  explicitly branches on exception type and marks status `TERMINATED`
  for the `else: # CancelledError or SystemExit` case rather than
  re-raising; agno's MCP cleanup code has `except BaseException: pass
  # Silently ignore (includes CancelledError)`, a textbook
  cleanup-must-not-mask-the-original-error pattern; litellm's
  `close_model_response` swallows any error while closing a resource
  during cleanup; and pydantic-ai's `_wrap_task.cancel(); try: await
  _wrap_task; except (asyncio.CancelledError, BaseException): pass` is
  the textbook-correct way to await a task's own self-initiated
  cancellation. Same conclusion as `cancelled-error-swallowed` above,
  reached independently from a "no `raise` in the handler" bar instead
  of that check's original unconditional one.

These are why the test suite asserts *both* directions: bad code flagged, good code
left alone.

## Real bugs found, not yet filed

CH026 (`mutable-class-attribute`) found four real, previously-unreported
bugs the first time it ran against the full corpus - all four the same
shape: a class-level mutable default (`items = []`) mutated in place via
`self.items.append(...)` or subscript assignment, with no per-instance
reassignment anywhere in the class, so every instance shares and
corrupts the same object.

- **vllm's `AXK1ForCausalLM`**: `self.packed_modules_mapping["qkv_proj"]
  = [...]` conditionally patches a routing table that's shared by every
  instance of the model class, not just the one being configured.
- **llama_index's `ZapierToolSpec`**: `self.spec_functions.append(action_name)`
  means a second tool-spec instance - a different Zapier API key, a
  different user - inherits every action name the *first* instance ever
  registered, since it's still appending to the same list object.
- **optuna's CLI `_Studies` command**: `self._study_list_header.append(("user_attrs", ""))`
  does the same to a table-header list, lower severity since the CLI is
  normally one-shot per process, but real if `_Studies` is ever
  instantiated more than once in a long-running embedding of the CLI.
- **HuggingFace transformers' `CodeGenTokenizer`**: `self.model_input_names.append("token_type_ids")`
  means constructing one tokenizer with `return_token_type_ids=True`
  silently changes what field every *other* `CodeGenTokenizer` instance
  in the same process expects, regardless of its own configuration -
  exactly the "spooky action at a distance" class of bug this project
  exists to catch.

llama_index's fix shipped as PR [run-llama/llama_index#23102](https://github.com/run-llama/llama_index/pull/23102)
(open). optuna's fix is committed and pushed to a fork branch, but PR
creation itself is currently blocked by GitHub (a 404/permission error,
not a rate limit - likely a one-open-PR-per-external-contributor policy,
since [optuna/optuna#6859](https://github.com/optuna/optuna/pull/6859)
from the CH011 batch is still open). vllm and transformers both require,
in their own contribution policy, that an AI-assisted PR carry an
explicit disclosure of AI assistance - something this project's own
standing policy (no AI authorship traces in anything shipped) doesn't
do, so those two are recorded here rather than filed until that's
resolved one way or the other.

Two more real bugs found the same way, in different checks:

- **CH013 (`discarded-future`) in langchain's `_run_batch_evaluators`**:
  `executor.submit(self.client.create_feedback, ...)` sits inside a
  `try:/except Exception: logger.exception(...)` block that looks like
  it already handles errors - but that `except` only ever sees
  exceptions from the *synchronous* code in the loop (running the
  evaluator, building the result dict). `create_feedback` actually runs
  later, on the executor's worker thread; if it raises, the exception is
  stored on the discarded `Future` and never reaches that `except` at
  all. Not filed: langchain's own `CLAUDE.md` requires "a brief
  disclaimer noting AI-agent involvement" in PR descriptions, the same
  conflict as vllm/transformers.
- **CH014 (`unprotected-lock-acquire`) in torchtune's
  `VLLMParameterServer._sync_weights_with_worker`**: `read_lock.acquire()`,
  several `torch.distributed`/NCCL broadcast calls and a
  `torch.cuda.synchronize()`, then `read_lock.release()` - no
  `try`/`finally` in between. Any exception during the broadcasts (a
  CUDA error, a shape mismatch, a network failure mid-sync) leaves the
  lock held forever; since this guards weight synchronization in an RL
  training loop, a stuck read lock deadlocks every future write-side
  weight update. The fix is a straightforward `with
  self.state_dict_lock.gen_rlock():` (the `readerwriterlock` library's
  lock objects support the context-manager protocol, used identically
  elsewhere in the same class), but this specific method is only
  exercised by the repo's own `@gpu_test`/`@rl_test`-marked integration
  tests, which need real GPUs, Ray, and vLLM to run - nothing this
  session's environment could exercise. Not filed, since the discipline
  this whole project holds itself to is verifying a fix before shipping
  it, not just reasoning that it's obviously correct.
- **CH029 (`finally-swallows-exception`) in letta - a mixed, honestly
  reported result.** The first corpus scan found 9 hits across 5 files.
  Two, in `letta_llm_stream_adapter.py` and `simple_llm_stream_adapter.py`,
  are byte-identical: `except BaseException as e: <log, then raise a
  typed error>` followed by `finally: if not stream_started: return`.
  The pattern is real and the concern is legitimate, but tracing
  `stream_started` shows it's assigned exactly once, unconditionally, to
  `True`, a few lines before the `try` - there's no other assignment
  anywhere in the function, so the `if not stream_started:` guard is
  currently always false and the `return` never actually executes. Not
  a live bug today, but exactly the kind of fragile code that becomes
  one the moment someone adds an early-return path before that
  assignment, without ever touching the `finally:` block that would
  then start silently eating errors. A third hit, in
  `letta_agent.py`'s step-processing loop (`finally: if step_progression
  == StepProgression.FINISHED and should_continue: continue`, right
  after an except block that logs an error stop reason and explicitly
  `raise`s it), looks like a real, live instance of the same class of
  bug, but confirming that requires understanding a large agent-loop
  state machine well enough to know whether that specific combination
  of flags is actually reachable while an exception is in flight - more
  than could be verified with confidence in the time available. None of
  the 9 filed as a PR: the two adapter hits aren't currently live, and
  the agent-loop hit needs more investigation than a quick read
  supports before claiming it's a bug rather than reasoning about a
  pattern - the same "verify before build" bar this project applies to
  its own checks now applied to using them.
- **CH034 (`raise-literal`) in llama_index's lilac reader.**
  `LilacReader.load_data`'s `except ImportError:` handler is
  `raise ("\`lilac\` package not found, please run \`pip install
  lilac\`")` - no comma inside the parens, so this parses as a
  parenthesized string, not a tuple, and is exactly `raise "..."`.
  Anyone missing the optional `lilac` dependency gets an unrelated
  `TypeError: exceptions must derive from BaseException` instead of the
  intended install instructions - the one case a helpful error message
  most needs to actually show up. Fixed, with a regression test
  verified to fail on pre-fix code and pass post-fix: filed as
  [run-llama/llama_index#23123](https://github.com/run-llama/llama_index/pull/23123).
- **CH036 (`environ-reassignment`) in HuggingFace `datasets`.**
  `Dataset.map`'s multiprocessing path does `os.environ = prev_env`
  immediately after opening `mp.Pool(num_proc)`, clearly intended to
  restore environment variables (likely ones temporarily overridden
  earlier in the same function) before spawning worker processes. Since
  a direct `os.environ` reassignment never reaches the real process
  environment, the spawned pool workers inherit whatever the actual
  environment still is, not the "restored" one - the fix silently
  doesn't do what its own code implies. Confirmed the general mechanism
  in a REPL (see "Notes on precision" below) rather than assuming it
  transfers to this exact call site; the fix itself
  (`os.environ.clear(); os.environ.update(prev_env)`) needs the
  surrounding function's full context read first to confirm `prev_env`
  is the right restore target, which hasn't been done yet - queued, not
  filed.
- **CH038 (`useless-expression-statement`) in mlflow and vllm - the
  same short-circuit bug, twice, independently.** mlflow's
  `transformers/__init__.py` validates a `List[Dict]` input with
  `all(_validate_input_dictionary_contains_only_strings_and_lists_of_strings(x)
  for x in input_data)`. Read the validator: it returns `None` on
  success (raises on failure, no explicit `return` otherwise) - so
  `all()` calls it on the first item, gets `None` back (falsy), and
  *stops right there*, returning `False` without ever validating any
  later item in the list. A list `[valid, invalid, invalid]` only ever
  checks the first entry; the other two invalid entries pass silently.
  vllm's `benchmarks/sweep/plot.py` and `plot_pareto.py` have the exact
  same shape with the exact same likely cause: `all(executor.map(partial(_plot_fig,
  ...), ...))` right under the comment "Resolve the iterable to ensure
  that the workers are run" - `_plot_fig` has no return statement, so
  it returns `None`, and `all()` stops consuming the mapped iterator
  after the first result, meaning only the first group of figures
  actually gets plotted across the worker pool despite the comment's
  stated intent to run all of them. Both would be trivially fixed
  (`list(...)` instead of `all(...)`, or a plain `for` loop), but
  neither was filed: mlflow's own `CLAUDE.md` requires a
  `Co-Authored-By: Claude` trailer "when Claude Code authors or
  co-authors changes," and vllm's `AGENTS.md` requires disclosing AI
  involvement in the PR body - both the direct opposite of this
  project's own no-AI-traces policy (see [`docs/FINDINGS.md`](#notes-on-precision)'s
  CH026 section for the same conflict against vllm/transformers
  earlier). Documented here instead of guessed at or filed against
  policy.
- **CH038 (`useless-expression-statement`) in letta - found, understood,
  not filed, for a different reason than the mlflow/vllm pair.**
  `summarizer_sliding_window.py` has, in order: a comment reading "Some
  arbitrary minimum value (10%) to avoid negatives from badly
  configured summarizer percentage," then a bare
  `max(1 - summarizer_config.sliding_window_percentage, 0.10)` whose
  result is never assigned to anything, then two lines later
  `goal_tokens = (1 - summarizer_config.sliding_window_percentage) *
  agent_llm_config.context_window` - using the *unclamped* expression
  directly. The clamp the comment describes was very likely meant to
  feed into that `goal_tokens` line and never got wired in. If
  `sliding_window_percentage` is configured close to `1.0`,
  `goal_tokens` collapses toward zero, and the eviction loop a few
  lines further down (`while approx_token_count >= goal_tokens and
  eviction_percentage < 1.0:`) would very plausibly run until it hits
  its own `eviction_percentage >= 1.0` escape hatch and raises
  `ValueError("No assistant message found for sliding window
  summarization")` - a real failure mode for an aggressive-but-legal
  configuration, not a hypothetical one. Understood well enough to
  write the fix (`goal_tokens = max(1 - summarizer_config.sliding_window_percentage,
  0.10) * agent_llm_config.context_window`, deleting the now-redundant
  bare `max(...)` line) - not filed anyway, because letta's own
  `AI_POLICY.md` requires disclosing "all AI usage in any form," a
  fourth repo hitting the same conflict as vllm/transformers/mlflow.
- **CH038 (`useless-expression-statement`) in pydantic - found, low
  confidence in the fix, not filed for that reason instead.**
  `_internal/_decorators.py`'s `_decorator_infos_for_class` has a chain
  of `elif isinstance(info, ...)` branches for each decorator-info
  type, ending in an `else:` branch with a bare
  `isinstance(var_value, ComputedFieldInfo)` right before the line that
  actually uses the result. Reads like a dropped `assert` - the keyword
  removed, the rest of the statement left behind - but the *correct*
  fix depends on whether pydantic actually wants a hard runtime
  assertion here or deliberately relies on the `else` branch being
  reached only when the type is already known some other way (by
  construction, from an earlier check this file wasn't fully traced
  through). Pydantic has no CLAUDE.md/AGENTS.md AI-disclosure conflict
  - the reason this one isn't filed is the same "don't ship a fix
  you're not confident is the *right* fix" bar applied to the
  `datasets`/CH036 finding above, not a policy conflict.
- **CH045 (`duplicate-dict-key`) in llama_index's Cortex LLM
  integration.** `base.py`'s payload builder has
  `{"url": self.cortex_complete_endpoint, "url": self.cortex_complete_endpoint, "headers": {...}, ...}`
  - the exact same key/value pair written twice, at two separate call
  sites in the same file (lines 258 and 411). Both values happen to be
  identical, so nothing crashes, but the duplication almost certainly
  means a different key/field was intended for the second line and got
  overwritten by a copy-paste - the request payload is missing
  whatever that field was meant to be. llama_index has no AI-disclosure
  conflict; not yet filed only because the *actual* missing field
  hasn't been identified - fixing the visible duplication without
  knowing what should replace it would just swap one incomplete
  payload for another.
- **CH046 (`duplicate-set-value`) in transformers' GPT-SW3 tokenizer -
  a genuinely hard-to-spot one.** `tokenization_gpt_sw3.py` builds
  `self.whitespaces = {" ", " ", " ", " ", " ", "　", " ", " ", " ", " ", "￼", ""}`
  for whitespace normalization - eight of those look like blank spaces
  to a human eye, and several of them are, byte-for-byte, the *same*
  Unicode whitespace character repeated, not eight distinct ones as
  the line's evident intent (normalize every kind of whitespace) would
  suggest. This is exactly the kind of bug this project exists for:
  it's invisible on a code review pass, because the whole point of the
  characters involved is that they render identically. Not filed -
  transformers' `CLAUDE.md` is a confirmed AI-disclosure-required repo
  (see the CH026 section above) - but pinning down exactly which
  Unicode code points are missing from the set (versus merely
  duplicated) needs a careful character-by-character audit this
  session didn't do, on top of the policy conflict.
- **CH047 (`contextmanager-yield-unprotected`) - four real, distinct
  hits, three of which have no AI-disclosure conflict and are ready to
  file.** litellm's `repositories/unit_of_work.py` has
  `spend_reset_unit_of_work`/`budget_cascade_unit_of_work`: both
  `yield SomeUnitOfWork(...)` then `await batch.commit()` with nothing
  in between - if the caller's code raises, the batch is never
  committed *and* never rolled back, left in an undefined state.
  peft's `tuners/boft/layer.py` (and two sibling files, `lora/model.py`,
  `road/model.py`) has a temporary-environment-variable context
  manager: sets `os.environ` values, `yield`s, restores them
  afterward - if the wrapped code raises, the restore never runs,
  leaking the overridden env vars for the rest of the process. agno's
  `os/app.py` has two FastAPI lifespan managers (`mcp_lifespan`,
  `http_client_lifespan`) that close MCP connections and an httpx
  client pool after `yield` - any startup/shutdown-time error skips
  that cleanup, leaking connections. litellm and peft have **no**
  AI-disclosure conflict (litellm's `CLAUDE.md` actually explicitly
  *forbids* AI attribution, matching this project's own policy exactly
  - the same repo PR #41582 was already filed to earlier this session);
  agno has no such policy either (matching every prior agno PR filed
  this session). mlflow's `utils/autologging_utils/__init__.py`
  (`batch_metrics_logger.flush()` after `yield`) has the same shape but
  **does** have the confirmed `CLAUDE.md` conflict. None of the four
  filed yet in this round - queued as the strongest, most policy-clean
  candidates for the next PR pass.
- **CH047, five more real hits, found by widening the corpus past the
  original ~29 frameworks specifically to look for more.** SQLAlchemy's
  `InvokeCreateDDLBase.with_ddl_events`/`InvokeDropDDLBase.with_ddl_events`
  (`sql/ddl.py`) both dispatch a `before_create`/`before_drop` event,
  `yield` (the actual DDL statement runs in the with-block body), then
  dispatch `after_create`/`after_drop` - if the DDL execution itself
  fails (a real, unremarkable possibility for any live database
  operation), the `after_*` event never fires, silently breaking
  anything relying on it for tracking or logging schema changes.
  Poetry's `FileConfigSource.secure()` (`config/file_config_source.py`)
  `yield`s a `TOMLDocument` for the caller to modify, then - the
  method's own name and comment ("Ensuring the file is only readable
  and writable by the current user") - writes it with `0o600`
  permissions; if the caller's modification raises before the
  with-block exits, the write (and the restrictive-permissions
  guarantee its own name promises) never happens at all, silently. A
  fifth, lower-confidence one: SQLAlchemy's `ToolCommandBase.run_program`
  (`util/tool_support.py`) sets flags, `yield`s the actual CLI work,
  then checks `if self.args.check and self.diffs_detected: sys.exit(1)`
  - real if something upstream swallows exceptions from the CLI run,
  not traced far enough to be certain. Two more real hits are lower
  severity by nature rather than by luck: Flask's own
  `FlaskClient.session_transaction` (`testing.py`) has the identical
  shape (`yield sess` then an unprotected session-save-back its own
  docstring promises always happens) but it's a *test* helper - a
  failing assertion inside the block already fails the test either
  way, so the skipped save-back rarely changes the outcome anyone
  observes. Celery's `t/unit/app/test_backends.py` test fixture starts
  a background worker thread, `yield`s it to the test, then
  `worker.stop()`/`t.join(10.0)` afterward - unprotected, so a failing
  assertion inside a test using this fixture leaks a running daemon
  thread for the rest of the pytest session, a real (if test-only)
  resource leak rather than a merely-cosmetic one. None of these five
  filed yet - found and read in full, but this round's effort went
  into fixing codehound's own checks (see "Notes on precision" above)
  rather than also filing PRs across five more repos in the same pass.
- **CH009, one plausible hit surfaced while re-scanning after the
  append-escape fix.** langgraph's CLI analytics decorator
  (`analytics.py`) does `background_thread = threading.Thread(target=log_data,
  args=(data,)); background_thread.start()` immediately before
  `return func(*args, **kwargs)` - a short-lived CLI command can
  plausibly exit before the background thread finishes sending its
  telemetry payload, silently dropping the event. The same shape as
  this project's very first self-found bug (agno's fire-and-forget
  `asyncio.create_task` for tracing, PR #8183) - a background
  reliability task racing the process it's attached to - just for a
  thread and a CLI process instead of a task and an event loop. Lower
  stakes (a missed analytics ping, not a lost trace in a running
  service) and not traced further this round.
- **CH051 (`mutation-during-iteration`), 4 real hits surviving three
  precision passes.** mlflow's `default.py` (also present, byte-identical,
  in a stray copy vendored under `accelerate/mlflow/`) does `for
  extra_metric in extra_metrics: ... extra_metrics.remove(extra_metric)` -
  a plain `list.remove()` inside the loop iterating that same list, so the
  element right after a removed latency metric can be silently skipped.
  litellm's `common_utils.py` does the JSON-schema equivalent:
  `for atype in anyof: ... anyof.remove(atype)`. transformers'
  `convert_suno_to_hf.py` does `for k in state_dict: ...
  state_dict[new_k] = state_dict.pop(k)` with no `break` after it (unlike
  a byte-identical-looking pattern in `modeling_mamba.py` that *does*
  `break` right after and was correctly excluded - see below) - the very
  next iteration's `__next__()` call raises `RuntimeError: dictionary
  changed size during iteration`. transformers' own `utils/check_inits.py`
  does `for folder in directories: ... directories.remove(folder)` while
  filtering `os.walk`'s own `dirnames` list - `os.walk`'s documented
  contract for pruning traversal is fine with `dirnames` being mutated in
  place, but doing it via `.remove()` from inside a `for` loop over that
  same list still skips checking whatever folder slides into the removed
  one's position, independent of `os.walk`'s own semantics. None filed
  yet - found in the same pass that built and precision-tuned the check
  itself (see "Notes on precision" below).
- **CH058 (`argparse-store-true-default`), 2 real hits.** litellm's
  `scripts/benchmark_chat_completions_perf.py` has
  `add_argument("--measure-full-stream", action="store_true",
  default=True, help="... (on by default).")` - the help text even
  documents the intended default, but `store_true` already returns that
  default when the flag is absent, so the flag itself does nothing;
  there's no way to pass it and get `False`. transformers'
  `convert_blt_weights_to_hf.py` has the identical shape for `--debug`.
  Neither filed yet - both are one-line, unambiguous fixes (drop the
  redundant `default=True`/`default=False`), found in the same pass as
  CH051 above.
- **CH067 (`namedtuple-mutable-default`), one real hit in optuna.**
  `visualization/_contour.py`'s `_SubContourInfo(NamedTuple)` has
  `constraints: list[bool] = []` - verified directly that `NamedTuple`
  field defaults are evaluated once at class-definition time and shared,
  the same mechanism as an ordinary function's default argument, not
  copied per instance the way a `pydantic.BaseModel` field default is
  (documented as a real, checked false positive for CH002 earlier in this
  file). Not filed yet - a one-line `default_factory`-style fix
  (`NamedTuple` doesn't have `default_factory`, so the real fix is
  restructuring to a `@dataclass` or accepting the shared default is safe
  here because nothing mutates `constraints` in place) needs a closer
  read of how `_SubContourInfo` instances are actually constructed first.
- **CH068 (`logging-extra-reserved-key`), one real hit in litellm, at
  `WARNING` level - the one severity most deployments don't filter out
  by default.** `guardrail_hooks/lasso/lasso.py`'s malformed-tool-call
  handler does `verbose_proxy_logger.warning("Skipping malformed
  tool_call", extra={"call_id": call_id, "name": name})` - `"name"` is a
  real `LogRecord` attribute, so this raises `KeyError: "Attempt to
  overwrite 'name' in LogRecord"` the moment a malformed tool call
  actually reaches this line, turning a diagnostic warning about bad
  input into an unhandled exception instead. Unlike this project's own
  earlier verification example (an `INFO`-level call, filtered out by
  the common `WARNING`-level default and therefore invisible until
  someone raises verbosity), `WARNING` is usually *not* filtered, so
  this one is live in ordinary operation, not just under debug settings.
  Not filed yet - straightforward one-line fix (rename the key), found
  in the same pass the check itself was built and corpus-scanned in.
- **CH076 (`duplicate-method-definition`), one real hit in mlflow.**
  `store/artifact/databricks_artifact_repo_resources.py`'s `_Trace`
  class defines `get_artifact_root(self) -> str:` twice, at two
  different line numbers in the same class body - the second silently
  replaces the first, making the earlier one dead code with no error or
  warning anywhere. Not filed yet - needs a read of both bodies to know
  which one (if either) is the intended implementation before proposing
  a fix.
- **CH077 (`abstractmethod-without-abc`), the batch's highest-volume
  real finding - 185 hits across 17 projects, and the check's own
  design makes every one of them airtight** (it only fires when a class
  has zero base classes and no `metaclass=` keyword, so there is no
  possible hidden `ABCMeta` coming from an invisible base - the corpus
  scan exists to gauge real-world frequency, not to hunt false
  positives that structurally can't occur here). Two representative
  examples, both genuinely unenforced: AutoGPT's `forge/speech/base.py`
  `VoiceBase` class uses `@abc.abstractmethod` on `_setup`/`_speech`
  with no base and no `ABCMeta`, so any of its five real subclasses
  (`ElevenLabsSpeech`, `MacOSTTS`, `GTTSVoice`, ...) that forgot to
  implement one would instantiate without error; mlflow's
  `store/model_registry/abstract_store.py` `AbstractStore` and
  `llm_api/llm_client_base.py`'s `LLMClientBase` in letta are the same
  shape - a class named "Abstract"/ending in "Base" that looks
  enforced but isn't. Not filed yet - 17 separate PRs (each adding
  either an `ABC` base or `metaclass=ABCMeta`, verifying nothing already
  relies on the current unenforced instantiability) is a batch too
  large to responsibly file without triaging project-by-project first.
- **CH084 (`defaultdict-read-creates-key`), one real hit in optuna.**
  `samplers/_nsgaiii/_elite_population_selection_strategy.py`'s
  NSGA-III elite-selection loop does `if
  reference_point_to_borderline_population[reference_point_idx]:` where
  `reference_point_to_borderline_population` is a
  `defaultdict(list)` - reading a reference point index that was never
  populated silently creates an empty-list entry for it as a side
  effect of the check itself, before the loop's own logic ever
  decides whether that reference point should exist. Not filed yet -
  the loop's surrounding logic needs tracing to confirm whether every
  index checked here is already guaranteed present (in which case this
  is a harmless but confusing read) or whether an absent one changes
  the sampler's actual output.
- **CH085 (`decorator-missing-functools-wraps`), 102 hits across 17
  projects after three rounds of narrowing (see "Notes on precision"
  below) - two representative real ones.** AutoGPT's
  `copilot/sdk/tool_adapter.py` builds `wrapper` inside
  `_make_truncating_wrapper(fn, tool_name, ...)`, forwarding `args`
  straight through to `await fn(args)` and returning `wrapper` directly
  - no `@functools.wraps(fn)`, so every MCP tool wrapped this way shows
  up in tracebacks and tool-introspection as `wrapper`, not its real
  name. vllm's `model_executor/models/transformers/utils.py` has the
  same shape in `patch_tensor_constructor(fn)`: `wrapper(*args,
  **kwargs)` adds one kwarg and forwards the rest straight to `fn`, with
  no wraps either. Not filed yet - same batch-size-vs.-triage tradeoff
  as CH077 above.

## Bugs the tool found on its own

The CH001 entry for the Discord client above is the project's original proof
point: it was **not** a bug I already knew about. I pointed `codehound` at
agno's source after building it, and CH001 surfaced two `requests.get()`
calls sitting inside the async `on_message` handler. Verified, fixed with
`await media.read()`, added a regression test, opened a PR. The tool earned
its keep on day one.

CH010 repeated that story on a much bigger stage: pointed at HuggingFace's
`accelerate` after fixing its two false positives, it surfaced a genuine
closure-capture bug in distributed-training parameter-sync callbacks - the
kind of thing that would silently corrupt which model chunk's gradients get
synced, in a library used across the entire PyTorch training ecosystem. Not
a bug I was looking for; the scan found it.

CH011 did it three times, in three unrelated projects, once the 20-check
corpus scan was used to hunt down real PR candidates rather than just to
sanity-check precision. In optuna, `_FanovaTree`'s node-lookup methods
leaked every random-forest tree ever built for a feature-importance
computation. In llama_index, `VectaraIndex._get_corpus_key` did the same
thing to the index itself - and because the class's own `__del__` exists
specifically to close its HTTP session on garbage collection, the leak also
silently broke that cleanup path, so the bug compounded into a second one
nobody had connected to the first. In litellm, `Router._cached_get_model_group_info`
leaked every `Router` that ever served a request, and survived even a
correctly-called `discard()` - the class's own documented cleanup method -
proving it was a real, independent bug rather than "the user forgot to
clean up." All three fixed the same way (move the `lru_cache` from class
scope to a per-instance wrapper built in `__init__`), all verified with a
regression test that fails pre-fix and passes post-fix, all opened as PRs
the same day the check itself shipped.
