# Day 20 — The receipts: each check → its real merged bug

> This is what makes codehound more than a toy linter: **every check is reverse-engineered from a real bug that a maintainer merged a fix for.** Today you memorize the receipts, because "show me proof" is the question that ends the conversation in your favor.

---

## 1. The map (check → real-world fix)
| Check | Bug class | Where it was found & fixed |
|-------|-----------|----------------------------|
| **CH001** blocking-call-in-async | sync call freezes the event loop | **unsloth #6135** (30s freeze, merged), **agno #8158/#8186** (merged) |
| **CH002** mutable-default-argument | shared mutable default leaks state | **mem0 #5302** (merged), **agno** toolkits |
| **CH003** deprecated `utcnow()` | naive UTC datetime | **crewAI** memory subsystem (9 sites, 4 files) |
| **CH004** deprecated `get_event_loop()` | deprecated asyncio API | **crewAI** structured-tool / Snowflake tool |
| **CH005** unclosed-file-handle | leaked file descriptor | **agno #8161** `transcribe_audio` (merged) |
| **CH006** floating-task | fire-and-forget task GC'd | **under review: vLLM #45249, autogen #7825, OpenAI #3553** |

## 2. The methodology (this is the *real* story)
The order matters and you should tell it correctly:
1. I was **fixing real bugs by hand** in AI frameworks (the agno/crewAI/mem0 PRs).
2. I noticed they fell into **recurring classes** — the same async/correctness mistakes everywhere.
3. So I **encoded each class as a check** — codehound is the *distillation* of bugs I'd already proven were real.
4. Then I **ran the tool back at the ecosystem** and it found *more* of the same (vLLM, autogen, OpenAI) — closing the loop.

> So codehound isn't "I built a linter and hoped it found things." It's "I fixed real bugs, saw the pattern, automated it, and the automation found more real bugs." That arc is the whole pitch.

## 3. Why "merged" is the killer word
A merged PR is **ground truth**: a maintainer of a 40k-star project looked at the fix and accepted it. That's external validation no amount of self-assessment matches. In the paper, merged PRs are literally the **validation method** — they're how you prove the flags are real bugs and not style opinions.

## 4. The one rejection (tell it on purpose)
CH004 produced a PR a maintainer **rejected** (the get_event_loop-in-a-running-loop false positive, Day 16). Volunteer this. It proves: (a) you submit real PRs and get real review, (b) you understand precision limits, (c) you turn a "loss" into paper material (RQ4). Candidates who only tell wins sound rehearsed; one honest miss makes the wins credible.

## 5. 🔧 Exercise — be able to recite the table
Cover the right column and name, for each check, *one* place it was merged. Then cover the left and, given "unsloth, 30-second freeze," name the check (CH001) and the fix (`await asyncio.sleep`).

## 6. 💬 Interview Q&A
**Q: Did you build the tool first or fix the bugs first?**
A: Bugs first. I was fixing real async/correctness bugs by hand, noticed they recurred as classes, then encoded each class as a check. The tool is the distillation, then I ran it back at the ecosystem and it found more.

**Q: How do you know the bugs it finds are *real*?**
A: Maintainers merged the fixes — unsloth, agno, mem0. A merge is external ground truth. That's also the validation method in my paper.

**Q: Has anything it flagged turned out *not* to be a bug?**
A: Yes — one `get_event_loop` PR was rejected because the call was inside a running loop, where it's valid. That's CH004's known precision limit, and it became a discussion point in my paper.

**Q: Which check are you proudest of?**
A: CH001 — it's the highest-impact (a 30-second production freeze in unsloth) and shows the most context-sensitivity (await-aware, async-only).

## ✅ Say this out loud
> *"Every check comes from a real bug I fixed by hand first — CH001 from a 30-second freeze in unsloth, CH002 from mem0, CH005 from agno's audio code. I noticed these were recurring classes, encoded each as a check, then ran codehound back at the ecosystem and it found more of the same, now under review at vLLM, Microsoft, and OpenAI. The validation is that maintainers merged the fixes — that's ground truth, and it's the validation method in my paper. One CH004 PR was rejected, which is exactly the precision limit I write about."*

That's Week 3 — **you now own all six checks and the proof behind them.** Next week: the CLI, tests, packaging, and writing your own seventh check.
