# Alpha-Reader Toolkit

A pipeline for getting **honest** alpha-reader feedback on a fiction manuscript using LLM personas, before you spend $200 on professional editorial reads or weeks on human alpha-reader cycles.

The catch: LLM personas, by default, lie. They produce warm 4-star reviews on books that should get 2 stars, because RLHF training rewards politeness over accurate critique. This toolkit's whole reason for existing is to get past that — through structural anti-sycophancy bindings, two-pass design, multi-model dispatch, and reflexive Opus self-critique.

## What this is

A Python pipeline that runs a manuscript through 9 distinct reader personas (defined as KU/Kindle Unlimited subscribers in different reading lanes) and produces structured critique with:

- **Forced negative generation** — every persona must list 5 specific things that didn't work before they may praise anything
- **Rating discipline** — 5 stars is reserved; default to 3 unless evidence pushes higher; round 3.5 → 3, not 4
- **No conversion arcs** — the "I came in expecting X and ended up loving it" pattern is banned
- **One-star Goodreads review** — every persona must articulate the strongest legitimate one-star case for the book, even if they don't agree with it
- **Predicted star distribution** — each persona predicts the % of 1,000 readers in their cohort giving 1/2/3/4/5 stars (must sum to 100)
- **Goodreads DNF prediction** — explicit DNF rate prediction
- **Two-pass design** — clean read first, then V1-comparison read with the 11th binding (no improvement-narrative arc)
- **Reflexive Opus self-critique** — every persona's output is audited by Opus 4.7 against the anti-sycophancy bindings; downgrades are surfaced
- **Multi-model dispatch** — persona work distributed across Sonnet, Opus, with self-audit always on Opus

The output: a structured critique that tells you whether your manuscript is actually working, not whether the LLM thinks you'd like to hear it's working.

## What this isn't

- **Not a replacement for human alpha readers** — the toolkit produces structured critique that approximates human reader response with some reliability but isn't equivalent. Use it to triage; use humans for ground truth.
- **Not a replacement for professional editorial reads** — developmental editors do a different kind of work (structure, character arc, scene-level craft). The alpha-reader toolkit answers "would readers like this?" not "is the craft sound?"
- **Not a manuscript improvement tool** — the toolkit critiques; it doesn't rewrite. The author still does the work.
- **Not for non-fiction** — designed for fiction reader response. Could be adapted for non-fiction; not currently shaped that way.

## Quick start

### 1. Install dependencies

```bash
pip install anthropic pyyaml python-dotenv textstat
```

Plus pandoc for `.docx → .md` conversion (only needed if your manuscript is in Word format):
- macOS: `brew install pandoc`
- Linux: `apt install pandoc` or equivalent
- Windows: download from [pandoc.org](https://pandoc.org/installing.html)

### 2. Get an Anthropic API key

Sign up at https://console.anthropic.com/ and copy your key.

A full alpha-reader run on a complete novel (~80K-100K words, 9 personas across 2 passes plus reflexive audit) costs roughly **$8-25** depending on which models you route to which personas. Set it once, run it many times as you revise.

### 3. Scaffold a new project

```bash
python new-splinter.py \
    --slug my-author-book-001 \
    --manuscript ./path/to/book.docx \
    --pen-name "Your Pen Name" \
    --genre "thriller" \
    --output-dir ./my-author-book-001
```

In ~2 minutes the scaffolder will:
- Create `./my-author-book-001/`
- Convert manuscript (`.docx → .md` via pandoc + chapter normalization) or copy if already markdown
- Copy the orchestrator + analyzer + auth probe + personas snapshot
- Generate `book_config.yaml` from CLI args
- Generate a `CLAUDE.md` (project context for Claude Code)
- Generate a `kickoffs/<date>-alpha-reader.md` (chair-authorization document)
- Run the readability analyzer (textstat)
- Print next-steps

### 4. Verify auth and dry-run

```bash
cd my-author-book-001
python orchestrator/auth_probe.py
python orchestrator/run-alpha-reader.py --dry-run
```

The auth probe confirms your API key works. The dry-run shows what would execute without making API calls.

### 5. Fire the actual run

```bash
python orchestrator/run-alpha-reader.py
```

Each persona takes ~3-6 minutes (depending on model). 9 personas × 2 passes + reflexive audit = ~60-90 minutes total wall-clock. Outputs land in `runs/alpha-readers-v2/<persona-name>.md`.

### 6. Read the outputs

Open the files in `runs/`. Each persona produces a structured critique following the anti-sycophancy bindings. The reflexive Opus self-critique flags any persona output that drifted from the bindings.

## Repo structure

```
alpha-reader-toolkit/
├── README.md                              ← you are here
├── METHODOLOGY.md                         ← anti-sycophancy + two-pass + reflexive design
├── LICENSE                                ← MIT
├── CONTRIBUTING.md
├── CHANGELOG.md
│
├── new-splinter.py                        ← scaffolder: manuscript → ready-to-fire project
├── install-into-existing-splinter.sh      ← refresh toolkit files in an existing project
├── install-into-existing-splinter.ps1     ← PowerShell equivalent
│
├── orchestrator/
│   ├── run-alpha-reader.py                ← canonical orchestrator
│   ├── readability_analyzer.py            ← textstat metrics panel
│   └── auth_probe.py                      ← verify API key works before firing
│
├── references/
│   └── personas-snapshot-v0.4.md          ← 9-persona reference
│
├── templates/
│   ├── book_config.yaml.template
│   ├── splinter-CLAUDE.md.template
│   ├── splinter-kickoff.md.template
│   ├── .env.example
│   └── .gitignore.template
│
├── docs/
│   ├── anti-sycophancy-bindings.md        ← the 10 universal bindings explained
│   ├── two-pass-design.md                 ← clean read + V1-comparison
│   ├── reflexive-self-critique.md         ← the Opus audit pass
│   ├── persona-design.md                  ← why 9 personas, why these 9
│   └── multi-model-dispatch.md            ← which model handles which persona
│
└── examples/
    └── example-output.md                  ← what a persona output looks like (anonymized)
```

## Why the unusual name "splinter"

A *splinter* is a per-book project directory — one splinter per manuscript, scaffolded from this toolkit. The name comes from the original use case (splinters of a larger writing project). The scaffolder calls them splinters because they're small, focused, and disposable; the toolkit they fork from is the trunk.

You can rename your project anything. The toolkit just calls it a splinter by convention.

## Costs and time

For a typical novel (~80K-100K words):

- **Scaffolding time:** ~2 minutes (manuscript conversion + project setup)
- **Per-persona run time:** ~3-6 minutes
- **9 personas × 2 passes + reflexive audit:** ~60-90 minutes wall clock
- **API cost per full run:** ~$8-25 depending on model routing
- **Re-runs after revision:** same cost; you'll do this several times as you iterate

Most authors run the pipeline 3-5 times across a manuscript's revision cycle. Total budget: ~$30-125 over the life of a book.

## Methodology lineage

The pipeline emerged from running the v0.3 methodology on a real novel and discovering the output was sycophantic — 7/7 keep-reading verdicts, mean 4.0 stars, voice 9/10 universal, 0 DNFs against the author's stated 15% baseline. Honest reader response would not produce those numbers.

The v0.4 retrofit added:
- **10 universal anti-sycophancy bindings** (explicit prompt-level constraints overriding RLHF politeness training)
- **2 adversarial personas** (Veronica + Emma — readers who DNF books regularly)
- **Reflexive Opus self-critique** (every persona output audited against the bindings)
- **Multi-model dispatch** (most work on Sonnet, audit always on Opus)

The v0.4-Two-Pass evolution added:
- **Clean read pass** (Pass A) — persona reads the manuscript fresh, no comparison
- **V1-comparison pass** (Pass B) — persona is shown a previous version's critique and asked whether the revision addressed the concerns
- **11th binding for Pass B** — no improvement-narrative arc ("I see they fixed X" can't drive the new verdict; the new verdict must stand on its own evidence)

Empirical findings on whether this approach actually produces honest critique are still being gathered. Treat the methodology as v1 — refine as your usage develops.

## Honest limits

- **The personas are LLM-generated.** They can be more or less calibrated to actual reader response depending on how well their prompts are tuned. Validate periodically against actual human reader feedback.
- **Anti-sycophancy bindings reduce but don't eliminate sycophancy.** Strong RLHF training pushes back hard. Don't trust 5-star verdicts even with bindings on.
- **Two-pass design adds cost.** Pass B doubles the run cost for marginal additional signal. Skip if budget-constrained or running on smaller revisions.
- **Reflexive self-critique catches some drift but not all.** A persona that drifts confidently (consistent voice, no obvious bindings violations, but conclusions don't match the evidence) can pass the Opus audit. Spot-check manually.
- **The pipeline doesn't replace alphas or editors.** It's faster and cheaper triage. The slower, more expensive options remain necessary for ground truth.

## Author and license

Designed and built by **Ryan Gosnell** ([@LoFiGamerGuy](https://github.com/LoFiGamerGuy)).

Licensed under the [MIT License](./LICENSE) — use freely, attribute when you can, fork without asking.

## Related public repos

This toolkit is part of a small family of public reference material on agentic engineering. Each has both a source repo and a live site.

- **[share-ai-engineering-patterns](https://github.com/LoFiGamerGuy/share-ai-engineering-patterns)** &middot; [live catalogue →](https://lofigamerguy.github.io/share-ai-engineering-patterns/) — Practitioner's reference for building with AI agents. The multi-agent and reflection-loop patterns documented there are the foundation this toolkit builds on. CC BY 4.0.
- **[council-of-five](https://github.com/LoFiGamerGuy/council-of-five)** &middot; [live →](https://lofigamerguy.github.io/council-of-five/) — Multi-perspective decision framework. The persona-rotation pattern in this toolkit is a domain-specific application of council-style structured deliberation. CC BY 4.0.
- **[reference-library-methodology](https://github.com/LoFiGamerGuy/reference-library-methodology)** &middot; [live →](https://lofigamerguy.github.io/reference-library-methodology/) — System for building a queryable, AI-readable technical reference library. MIT.
- **[five-register-design-system](https://github.com/LoFiGamerGuy/five-register-design-system)** &middot; [live gallery →](https://lofigamerguy.github.io/five-register-design-system/) — Design system. MIT.
- **[terminal-stack](https://github.com/LoFiGamerGuy/terminal-stack)** — Opinionated terminal kit for Git Bash on Windows.
- **[dotfiles](https://github.com/LoFiGamerGuy/dotfiles)** — Personal dotfiles.

More repos in this family will be released over time.

---

*Alpha-Reader Toolkit · v1.0 · May 2026.*
