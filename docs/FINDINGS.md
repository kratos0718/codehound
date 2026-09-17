# Findings in the wild

Seven of the twenty `codehound` rules were distilled from a bug found in a
real, widely-used open-source project, with the fix submitted as a pull
request. The rest (CH007-CH009, CH011-CH020) are hardening rules verified
through real false positives against a ~20-framework validation corpus
instead of a found-and-merged bug - see "Notes on precision" below for
why, and what that absence itself says.

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

These are why the test suite asserts *both* directions: bad code flagged, good code
left alone.

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
