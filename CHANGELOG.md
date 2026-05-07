# Changelog

All notable changes to the Alpha-Reader Toolkit.

## [1.0.0] — 2026-05-07

### Added — initial public release
- `README.md` — what the toolkit is, what it isn't, quick start
- `METHODOLOGY.md` — the four mechanisms (anti-sycophancy bindings, two-pass, reflexive self-critique, multi-model dispatch), the limits, when to use it
- `LICENSE` — MIT
- `CONTRIBUTING.md`
- `new-splinter.py` — scaffolder for new projects
- `install-into-existing-splinter.sh` / `.ps1` — refresh toolkit files in existing projects
- `orchestrator/` — three Python scripts: `run-alpha-reader.py` (canonical orchestrator), `readability_analyzer.py` (textstat metrics panel), `auth_probe.py` (verify API key)
- `references/personas-snapshot-v0.4.md` — 9-persona cohort with anti-sycophancy bindings
- `templates/` — book_config schema, project CLAUDE.md template, kickoff template, .env.example, .gitignore template
- `docs/` — anti-sycophancy bindings explained, two-pass design, reflexive self-critique, persona design, multi-model dispatch
- `examples/example-output.md` — anonymized example of what a persona output looks like

### Notes on this release
- The methodology is distilled from running the pipeline on a real novel. The empirical findings on whether anti-sycophancy bindings reduce vs eliminate sycophancy continue to develop.
- The 9 personas are constructed approximations of KU reader behavior. They approximate cohort response patterns; they don't perfectly replicate them. Validate against actual readers periodically.
- The pipeline produces critique, not rewriting. Authors still do the work.
