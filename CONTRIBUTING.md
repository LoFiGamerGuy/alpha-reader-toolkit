# Contributing

This toolkit is opinionated. Contributions that align with the methodology are welcome; contributions that fundamentally rework it will likely be declined unless they argue convincingly for the change.

## What's most welcome

In rough priority order:

1. **Bug fixes.** Orchestrator crashes, parser errors, edge cases in the readability analyzer.
2. **Persona refinements.** If you've used the pipeline extensively and discovered a persona's prompt is producing inconsistent or off-target output, propose the refinement.
3. **Multi-model adapters.** The current orchestrator targets Anthropic's Claude API. Adapters for OpenAI, Gemini, or other providers are welcome.
4. **Genre-specific persona packs.** The default 9-persona cohort is calibrated to general KU readers. Genre-specific cohorts (literary fiction, poetry, middle-grade, YA) would extend reach.
5. **Tooling improvements.** Better progress reporting, partial-run resume, parallelization within rate limits.
6. **Empirical findings.** "I ran the pipeline on N books and here's what I learned about its accuracy" is high-value content for the docs.

## What will likely be declined

- **Removing the anti-sycophancy bindings.** They're load-bearing. The whole point of the pipeline is the bindings.
- **Replacing the personas with a single "general reader."** Multi-persona is the design.
- **Adding "constructive feedback mode" or other softening modes.** The pipeline produces the critique it was designed to produce. Softening defeats the purpose.
- **Adding a manuscript-rewrite tool.** Critique only. Rewriting is a different problem.
- **Hardcoding specific authors / book titles in the methodology.** The pipeline is generic; specific examples belong in your project's `book_config.yaml`.

## How to contribute

### For bug fixes:
1. Open a PR with the fix
2. Note which persona / model / Pass triggered the bug
3. Include a minimal reproduction if possible

### For persona refinements:
1. Open an issue first describing the persona, the observed inconsistency, and your proposed fix
2. We'll discuss whether it's a persona-prompt issue, an orchestrator issue, or something else
3. Then PR the change

### For multi-model adapters:
1. Open an issue describing which provider you want to add and the rough shape
2. Discuss the interface (the orchestrator currently assumes Anthropic Messages API; abstracting for other providers needs design)
3. PR the adapter

### For empirical findings:
1. Run the pipeline on N manuscripts
2. Compare outputs to actual human reader response (alpha readers, real Goodreads reviews, beta reader feedback)
3. Write up findings: where the pipeline agreed, where it diverged, what calibration adjustments would close the gap
4. PR a new doc in `docs/empirical-findings/<your-findings>.md`

## Style conventions

### Python

- **Standard library + minimal dependencies.** Current deps: `anthropic`, `pyyaml`, `python-dotenv`, `textstat`. Adding new top-level dependencies requires a strong case.
- **Type hints on function signatures.** Python 3.10+ syntax (`list[str]`, `dict | None`).
- **Docstrings at top of file.** Multi-line, describe what it does, usage, env vars.
- **Explicit `--help`.** All scripts accept `--help` and produce useful output.

### Markdown

- **Short sentences.**
- **Concrete over abstract.** Specific examples beat general claims.
- **No hype.** "Game-changing," "revolutionary" — banned.
- **Cite when borrowing.** RLHF behavior research, KU reader data — credit sources.

## Format expectations

- **MIT license** applies to all contributions
- **Internal links use relative paths**
- **Test against a real manuscript before PRing.** "It compiles" is not the bar; "it produces useful output on a real book" is.

## Maintainer

Ryan Gosnell — [GitHub @LoFiGamerGuy](https://github.com/LoFiGamerGuy)

---

*This file is MIT licensed, same as the rest of the repo.*
