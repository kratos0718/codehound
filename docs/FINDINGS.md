# Findings in the wild

Every `codehound` rule was distilled from a bug found in a real, widely-used
open-source project — and in each case the fix was submitted as a pull request.
This is the provenance of the ruleset.

| Rule | Project | ⭐ | The bug | Fix |
|------|---------|----|---------|-----|
| CH001 `blocking-call-in-async` | agno | 25k+ | **Found by codehound itself:** `requests.get()` inside the async `on_message` Discord handler froze the event loop on every video/document attachment (and could 403 on authenticated URLs) | replaced with `await media.read()`; regression test via `inspect.getsource` |
| CH001 `blocking-call-in-async` | agno | 25k+ | `time.sleep(1)` inside `_async_create_collection_and_scope` froze the event loop during a Couchbase collection overwrite | replaced with `await asyncio.sleep(1)`; regression test via `inspect.getsource` |
| CH002 `mutable-default-argument` | agno | 25k+ | Mutable default args across toolkits (`searxng`, `mcp_toolbox`, `pdf_reader`, base `Toolkit`) | PR #8152 — 10 sites fixed, 6 regression tests |
| CH002 `mutable-default-argument` | mem0 | 35k+ | `Completions.create(messages=[])` and `BaseEmbedderConfig.__init__(azure_kwargs={})` | PR #5302 — `None`-default + body init, `inspect.signature` test |
| CH003 `deprecated-datetime-utcnow` | crewAI | 30k+ | 9 calls to `datetime.utcnow()` across the memory subsystem (removed in 3.14) | PR #5970 — `datetime.now(timezone.utc).replace(tzinfo=None)` |
| CH004 `deprecated-get-event-loop` | crewAI | 30k+ | `asyncio.get_event_loop()` in structured-tool / Snowflake search tool | PR #5969 — `get_running_loop()`; bot-approved |
| CH005 `unclosed-file-handle` | agno | 25k+ | `audio_file = open(audio_path, "rb")` never closed in `OpenAITools.transcribe_audio` | wrapped in `with open(...) as audio_file:` |

## Notes on precision

`codehound` is deliberately conservative. While building it, two AST "hits" were
investigated and **correctly rejected** as non-bugs — exactly the false positives
a naive grep would have reported:

- **dspy `syncify.run_async`** — a lingering `asyncio.get_event_loop()` sits inside
  a branch guarded by `loop.is_running()`, where it does *not* trigger the
  deprecation. CH004 flags the call but a human (correctly) decides it isn't worth
  a PR. The lesson — *a finding is a lead, not a verdict* — shaped the project's
  framing.
- **optuna `FileSystemArtifactStore.open_reader`** — returns the open handle to the
  caller (`-> BinaryIO`). CH005 suppresses this because the handle is `return`ed,
  so ownership passes to the caller. (Verified: no false positive emitted.)

These are why the test suite asserts *both* directions: bad code flagged, good code
left alone.

## A bug the tool found on its own

The CH001 entry for the Discord client above is the project's proof point: it was
**not** a bug I already knew about. I pointed `codehound` at agno's source after
building it, and CH001 surfaced two `requests.get()` calls sitting inside the
async `on_message` handler. Verified, fixed with `await media.read()`, added a
regression test, opened a PR. The tool earned its keep on day one.
