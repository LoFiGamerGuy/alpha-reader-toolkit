# Methodology

The principles behind the toolkit. Read this before adopting the tooling so you understand what the pipeline does and why it does it that way.

## The problem

LLM personas, asked to read and critique a fiction manuscript, produce warm reviews. This is a structural property of RLHF training, not a bug — the models are trained to be helpful, polite, and constructive, and they apply those priors to creative work whether or not the work merits them.

Specifically, the failure mode looks like:

- 7/7 personas vote keep-reading
- Mean star rating clusters at 4.0
- "Voice" praised as 9/10 universally regardless of how generic the voice actually is
- 0 DNFs against the author's stated 10-20% reader DNF baseline
- Closing-summary warmth: every review concludes with "this is a strong manuscript with [minor concerns]"

The author who reads these critiques learns nothing useful. They feel validated, ship, and discover at launch that the actual reader response is much harsher.

The pipeline exists to produce something closer to honest critique despite the structural pull toward sycophancy.

## The four mechanisms

The toolkit uses four overlapping mechanisms to push past sycophancy. Each one alone is partial; together they produce noticeably more honest output.

### 1. Anti-sycophancy bindings

The personas' system prompts include 10 explicit bindings that override default RLHF politeness. Examples:

- **Forced negative generation:** every persona must list 5 specific things that didn't work *before* they may praise anything
- **Rating discipline:** round 3.5 → 3, not 4; default to 3 unless evidence pushes higher; 5 stars is reserved
- **No conversion arcs:** the "I came in expecting X and ended up loving it" pattern is banned
- **No closing warmth padding:** can't write a friendly summary; must answer "what sentence would you tell a skeptical friend?"
- **One-star review generation:** every persona must articulate the strongest legitimate one-star case
- **Authority-relationship inversion:** the persona is reading for a critic-publication editor, not for the author

See [`docs/anti-sycophancy-bindings.md`](./docs/anti-sycophancy-bindings.md) for the full 10 with rationale.

These bindings work because they're *structural* — the persona can't comply with the prompt format without producing the harsh content. They can still hedge in interpretation; they can't skip the negative-generation step entirely.

### 2. Two-pass design

For revision cycles, the pipeline supports a two-pass design:

- **Pass A — Clean read:** the persona reads the current manuscript fresh, no awareness of prior versions or critiques. Standard 10-binding output.
- **Pass B — V1-comparison read:** the persona is shown the previous version's critique and asked whether the revision addressed the concerns. Adds an **11th binding for Pass B**: no improvement-narrative arc — the new verdict must stand on its own evidence, not on "I see they tried to fix X."

Why two passes:

- Pass A gives you the unbiased reader response to the current state
- Pass B gives you the revision-effectiveness signal — did the changes actually land?
- Without Pass B, you can't tell whether your revisions are working
- Without the 11th binding in Pass B, the persona will narrate an improvement arc whether one exists or not (RLHF politeness applied to revisions specifically)

Pass B doubles the run cost. Skip for early-revision rounds; use for later rounds where you specifically want revision-effectiveness signal.

### 3. Reflexive Opus self-critique

After every persona produces output, that output is audited by Opus 4.7 against the anti-sycophancy bindings. The audit checks:

- Did the persona actually generate 5 negative items, or did they substitute "neutral observations"?
- Is the rating consistent with the evidence cited, or did the persona round up?
- Did the persona write a conversion arc despite the binding?
- Does the closing answer the "skeptical friend" question or revert to a warmth summary?

If the audit detects drift, it produces a downgrade recommendation. The orchestrator surfaces these in the run output so you can see which personas drifted and how.

The audit is always on Opus 4.7 even when the persona work was on Sonnet — Opus is more reliable at meta-evaluation.

### 4. Multi-model dispatch

The pipeline routes different personas to different models:

- **Sonnet 4.6** for most personas — fast, cheap, sufficient for the bulk of the work
- **Opus 4.7** for personas where reasoning depth genuinely changes the output — typically the adversarial personas (Veronica, Emma) where the strongest negative case is the load-bearing output
- **Opus 4.7** always for the reflexive self-critique pass

Routing is configured in `book_config.yaml` per project. Defaults are reasonable; tune if your specific use case warrants.

## The 9 personas

The cohort is calibrated to Kindle Unlimited (KU) reader behavior — high-volume readers (5+ books/month) who DNF freely and rate quickly. KU readers are roughly the harshest mainstream-reader cohort; building the personas to that baseline gives you a conservative signal.

The 9 personas span:

- 7 lane-specific readers (romance, thriller, sci-fi, fantasy, etc.) — adapted to your manuscript's lane
- 2 adversarial personas (Veronica, Emma) — readers who DNF books regularly and aren't shy about it

See [`docs/persona-design.md`](./docs/persona-design.md) for the full rationale and [`references/personas-snapshot-v0.4.md`](./references/personas-snapshot-v0.4.md) for the persona profiles.

## What the pipeline produces

For each persona × pass × manuscript:

- Cited evidence for verdicts (chapter-level or scene-level specifics)
- Rating with predicted Goodreads distribution (% of 1,000 cohort readers giving 1/2/3/4/5 stars)
- DNF prediction with the chapter-or-percentage where DNF would occur
- One-star review (the strongest legitimate negative case)
- Comp-anchor ranking (how the manuscript ranks against 3 named comps in the lane)
- The "skeptical friend" sentence — what would you tell someone asking if they should read this?
- Reflexive audit: drift flags, downgrade recommendations

Aggregated across all 9 personas × 2 passes:

- Cohort verdict distribution (how many keep-reading, how many DNF)
- Star rating distribution (mean and shape)
- Recurring concerns (what multiple personas independently flag)
- Recurring strengths (what multiple personas independently praise)
- Lane-specific signal (which reading lanes the manuscript serves vs misses)
- Revision effectiveness signal (Pass B vs Pass A delta)

## What the pipeline does NOT do

- **Doesn't rewrite the manuscript.** Critique only.
- **Doesn't replace human alpha readers.** Approximate triage, not ground truth.
- **Doesn't replace developmental editors.** Reader response, not craft analysis.
- **Doesn't fix sycophancy 100%.** Reduces it substantially; doesn't eliminate it. Spot-check 5-star verdicts manually.
- **Doesn't work for non-fiction.** Built for fiction reader response specifically.

## Honest limits and unsolved problems

These are real and you should know them:

- **Sycophancy reduction isn't sycophancy elimination.** Even with all 10 bindings, RLHF training pushes back. The output is more honest than naive prompting; it's not as honest as a real cohort of harsh readers.
- **The personas are constructed, not real.** They approximate cohort response patterns but don't perfectly replicate them. Validate periodically against actual reader feedback.
- **Anti-sycophancy can produce false negatives.** Books that genuinely deserve 4.5 might get 3.5 because the bindings pushed everything down. The intentional bias is conservative — better to underrate than overrate — but it is a bias.
- **Reflexive audit catches obvious drift, not subtle drift.** A persona that drifts confidently (consistent voice, no obvious bindings violations, but conclusions don't match the evidence) can pass the audit.
- **Two-pass design assumes a meaningful V1.** If your prior version is too similar to current or too dissimilar, Pass B's signal degrades.
- **Cost adds up across revision cycles.** A novel revised 5 times = ~$50-125 total. Worth it for serious work; budget conscious for hobby projects.

## When to use this

Good fits:

- You're a writer working on a novel and want triage feedback before paying alphas or editors
- You're a writing coach or developmental editor wanting to scale a first-pass critique
- You're studying reader response patterns and want a controlled environment to experiment
- You have a backlog of manuscripts and want to triage which ones get more investment

Bad fits:

- You want validation, not honest critique. The pipeline is designed to give you the latter; if you want the former, find different tooling.
- You want craft critique (prose mechanics, scene structure, character arc). The pipeline gives reader response, not craft analysis.
- You're working on non-fiction. Pipeline is fiction-shaped.
- You can't afford ~$10-25 per run. The pipeline runs cost real money.

## How to actually adopt this

In rough order:

1. **Read this file plus [docs/anti-sycophancy-bindings.md](./docs/anti-sycophancy-bindings.md)** — understand what the pipeline is doing
2. **Set up a test project with a manuscript you've already gotten human feedback on** — gives you ground truth to calibrate against
3. **Run Pass A only first** — see what the pipeline produces vs what your humans said
4. **Tune persona prompts if needed** — your specific use case (genre, audience) may need adjustments to the personas
5. **Add Pass B for your next revision** — see whether the revision-effectiveness signal matches your reader feedback
6. **Iterate persona tuning across runs** — the pipeline gets more useful as the personas get more calibrated to your specific context

The methodology emerged from doing exactly this on a real novel. The patterns documented work; they're not theoretical. They're also not finished — refinements continue as more authors validate against more manuscripts.
