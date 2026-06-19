# arXiv submission — copy-paste pack for the codehound paper

Upload bundle: **`~/Downloads/arxiv_codehound_submission.tar.gz`** (contains `paper.tex` + `figures/fig1_defects_by_class.png`). arXiv compiles LaTeX server-side; IEEEtran.cls is already in arXiv's TeX Live, so you don't need to include it.

---

## 1. Fields to paste into the arXiv form

**Title:**
> Async Landmines in the AI Stack: An AST-Based Empirical Study of Concurrency and Resource-Management Defects in Popular Python AI/ML Frameworks

**Authors:**
> Abhinav Tarigoppula

**Primary category:** `cs.SE` (Software Engineering)
**Cross-list (secondary):** `cs.PL` (Programming Languages)  *(optional; add `cs.LG` only if you want ML-audience reach)*

**Comments field:**
> 6 pages, 1 figure, 2 tables. codehound analyzer and full corpus scan results are open-source.

**Abstract (plain text — paste this, NOT the LaTeX version):**
> Modern AI and machine-learning systems are overwhelmingly implemented in Python and depend heavily on the asyncio event loop for high-throughput model serving, agent orchestration, and tool execution. Asynchronous Python, however, is susceptible to a family of subtle, hard-to-debug defects — synchronous calls that block the event loop, fire-and-forget tasks that may be garbage-collected before completion, leaked file descriptors, mutable default arguments, and deprecated event-loop APIs — that routinely pass unit tests and code review while degrading reliability in production. We present codehound, a zero-dependency, AST-based static analyzer (approximately 750 lines of code, standard-library ast only) that detects six such defect classes, and we apply it in a systematic empirical study across 29 widely-used open-source Python AI/ML frameworks (combined over 1.28 million GitHub stars, 6.4 million lines of Python). We identify 1,377 defect instances in 24 of the 29 frameworks, dominated by mutable default arguments (53.9%), deprecated event-loop usage (20.8%), and fire-and-forget tasks (19.0%), with rarer but higher-severity event-loop-blocking calls clustered in HTTP serving routes and agent loops. Crucially, we validate a sample of detections by submitting upstream fixes: five pull requests were merged by maintainers, providing real-world ground truth that these are genuine, accepted defects rather than stylistic preferences — and we analyze the false positives (e.g., get_event_loop() invoked inside an already-running loop) that a precise detector must avoid. Our results indicate that async-safety and resource-management anti-patterns are prevalent even in mature, heavily-used AI infrastructure, and that lightweight AST analysis surfaces them at high practical precision.

**License (recommendation):** choose **"arXiv.org perpetual, non-exclusive license"** — it's the safest if you might later submit this to a conference/journal (CC BY 4.0 is more open but can complicate later publication). 

---

## 2. ⚠️ The real hurdle: ENDORSEMENT — and the GITAM email fix
arXiv requires first-time submitters in `cs.*` to be **endorsed**. With a gmail address you are likely **NOT** auto-endorsed. **Use your GITAM email — it's the easy path.**

**Your worry ("I'll lose access when I graduate") is based on a misconception — here's the truth:**
- An **arXiv account is permanent.** Your papers and account are **never** deleted if your college email later stops working. Once a paper is up, it's public and citable forever.
- You do **NOT** need to log in with the GITAM email. Keep your **gmail as the account login + recovery**, and just **ADD the GITAM email as a secondary/verified email** on the same account (arXiv account settings → add email → verify). That verified academic affiliation is what can trigger **auto-endorsement** — without ever risking your access.
- So: gmail = how you keep the account forever; GITAM email = the key that unlocks endorsement. Best of both, zero downside.

**Steps:**
1. Log into your existing arXiv account (gmail).
2. Account settings → add your **GITAM email** (e.g. `...@gitam.in` / `gitam.edu`) → verify it from your college inbox.
3. Try the `cs.SE` submission. If arXiv auto-endorses you (common from academic domains), you're through.
4. If it still asks for endorsement, request the **endorsement code** from a professor/senior who has an arXiv `cs.SE` paper (Dr. Mahanty or any cs-publishing contact) — endorsement is per-category and takes them one click.

Do this **before** you start the submission — it's the #1 thing that stalls first-timers.

## 3. Step-by-step
1. Create/verify your arXiv account (✅ you've done this) and confirm the email.
2. Start a new submission → category `cs.SE`.
3. If prompted, handle **endorsement** (see §2).
4. Upload `arxiv_codehound_submission.tar.gz`. Let arXiv compile it; **check the generated PDF** looks right (figure, tables, no missing refs).
5. Paste Title / Authors / Abstract / Comments / category from §1.
6. Pick the license (§1).
7. Submit. It goes to moderation (usually a day or two) → then it's a citable preprint with an arXiv ID + DOI.

## 4. Optional polish before you submit (strengthens it)
- **Add 2–3 real related-work references** (line 142 has a `%% TODO`). Only add papers you've actually found on Google Scholar — never invent citation details. Search terms: "empirical study Python concurrency bugs", "asyncio misuse detection", "static analysis machine learning systems reliability". Adding 2–3 real ones makes the Related Work section look complete.
- Re-read it once in your own voice (see the AI note below).
