#!/usr/bin/env python3
"""Readability panel — toolkit-canonical, Med tier.

Computes a 7-metric panel (FK Grade, Flesch Reading Ease, Dale-Chall,
SMOG, Coleman-Liau, ARI, Gunning Fog, Linsear Write) plus textstat's
consensus grade and estimated Lexile. Synthesizes a craft characterization
from the panel + sentence-length variance.

Whole-book + per-chapter (markdown # heading split).

Reads manuscript path + genre_hint from book_config.yaml at PROJECT_ROOT
by default. CLI args override config when present.

Usage:
  py -3.14 orchestrator/readability_analyzer.py             # uses book_config.yaml
  py -3.14 orchestrator/readability_analyzer.py --manuscript ./book.md --genre "thriller"
"""
from __future__ import annotations

import argparse
import re
import statistics
import sys
from pathlib import Path

import textstat
import yaml

PROJECT_ROOT = Path(__file__).parent.parent
CONFIG_PATH = PROJECT_ROOT / "book_config.yaml"
DEFAULT_OUTPUT = PROJECT_ROOT / "references" / "readability-snapshot.md"


def strip_md(text: str) -> str:
    """Strip markdown headings + bold/italic markers for readability metrics."""
    out = re.sub(r"^#.*$", "", text, flags=re.MULTILINE)
    out = re.sub(r"\*\*(.+?)\*\*", r"\1", out)
    out = re.sub(r"\*(.+?)\*", r"\1", out)
    return out


def split_chapters(text: str) -> list[tuple[str, str]]:
    """Split on `# Chapter N` headings. Returns [(title, body), ...]."""
    parts = re.split(r"^(# Chapter \d+)\s*$", text, flags=re.MULTILINE)
    chapters: list[tuple[str, str]] = []
    for i in range(1, len(parts), 2):
        chapters.append((parts[i].strip(), parts[i + 1] if i + 1 < len(parts) else ""))
    return chapters


def panel(text: str) -> dict:
    """Compute readability metrics. Returns dict with all metrics + sentence stats."""
    sentences = textstat.sentence_count(text)
    words = textstat.lexicon_count(text, removepunct=True)
    sent_lengths = [len(s.split()) for s in re.split(r"[.!?]+", text) if s.strip()]
    sent_var = statistics.stdev(sent_lengths) if len(sent_lengths) > 1 else 0.0
    return {
        "words": words,
        "sentences": sentences,
        "fk_grade": round(textstat.flesch_kincaid_grade(text), 2),
        "fk_ease": round(textstat.flesch_reading_ease(text), 1),
        "dale_chall": round(textstat.dale_chall_readability_score(text), 2),
        "smog": round(textstat.smog_index(text), 2),
        "coleman_liau": round(textstat.coleman_liau_index(text), 2),
        "ari": round(textstat.automated_readability_index(text), 2),
        "gunning_fog": round(textstat.gunning_fog(text), 2),
        "linsear_write": round(textstat.linsear_write_formula(text), 2),
        "consensus": textstat.text_standard(text, float_output=False),
        "lexile_est": round(textstat.lexile(text)) if hasattr(textstat, "lexile") else None,
        "sent_len_avg": round(words / sentences, 2) if sentences else 0,
        "sent_len_stdev": round(sent_var, 2),
    }


def register_signal(p: dict) -> dict:
    """Interpret panel for fiction-craft register signal.

    Mechanical grade-band classifiers fail on fiction with deliberate stylistic
    choices (e.g. simple sentences applied to mature content — Hemingway,
    Rooney, Offill). Surface the panel's CRAFT implications instead of mapping
    to a misleading reader-age band.
    """
    fk = p["fk_grade"]
    dc = p["dale_chall"]
    var = p["sent_len_stdev"]
    avg = p["sent_len_avg"]

    # Vocabulary signal — Dale-Chall measures % of words outside the 3,000-easy-word list
    if dc < 6.5:
        vocab = "highly restricted vocabulary (sub-4th-grade word pool)"
    elif dc < 7.0:
        vocab = "restricted vocabulary (4th-grade-comprehensible word pool)"
    elif dc < 8.0:
        vocab = "moderate vocabulary (avg-adult word pool)"
    else:
        vocab = "expanded vocabulary (college-level word pool)"

    # Structure signal — sentence-length variance separates literary from commercial register
    if var > 10:
        structure = "very high sentence-length variance — strongly literary register (mixing very short with longer sentences)"
    elif var > 7:
        structure = "high sentence-length variance — literary register"
    elif var > 4:
        structure = "moderate sentence-length variance — mixed register"
    else:
        structure = "low sentence-length variance — commercial register (uniform sentence length)"

    # Combined craft characterization
    if fk < 5 and var > 8:
        craft = "STRIPPED-DOWN LITERARY — short words, simple grammar, but deliberately varied sentence rhythm. Hemingway / Rooney / Offill territory. The simplicity is a CHOICE, not a YA-targeting ceiling."
    elif fk < 5 and var <= 8:
        craft = "COMMERCIAL ACCESSIBLE — uniformly simple. Standard mass-market commercial register."
    elif fk < 7:
        craft = "STANDARD COMMERCIAL — bestseller sweet-spot for fiction (FK 6-8)."
    elif fk < 9:
        craft = "UPMARKET COMMERCIAL — slightly elevated, still accessible."
    else:
        craft = "LITERARY — denser prose, college+ vocabulary, longer sentences."

    return {
        "vocabulary": vocab,
        "structure": structure,
        "craft": craft,
        "avg_sentence_words": avg,
        "sentence_variance": var,
    }


def persona_prompt_block(whole: dict, sig: dict, content_genre: str) -> str:
    """Build the readability section the orchestrator injects into persona-system.

    Content-aware — explicitly names register, prevents misclassification,
    binds the symmetric FK guard.
    """
    return f"""## EMPIRICAL READABILITY (measured panel)

This manuscript was measured across a 7-metric readability panel:

| Metric | Value |
|---|---|
| Flesch-Kincaid Grade | {whole['fk_grade']} |
| Flesch Reading Ease | {whole['fk_ease']} |
| Dale-Chall (vocabulary load) | {whole['dale_chall']} |
| SMOG | {whole['smog']} |
| Coleman-Liau | {whole['coleman_liau']} |
| Gunning Fog | {whole['gunning_fog']} |
| textstat consensus grade | {whole['consensus']} |
| Avg sentence length | {whole['sent_len_avg']} words |
| Sentence-length stdev | {whole['sent_len_stdev']} (>8 = literary register) |

**Vocabulary signal:** {sig['vocabulary']}.
**Structure signal:** {sig['structure']}.
**Craft characterization:** {sig['craft']}

**Genre context:** {content_genre}. The mechanical readability metrics describe surface complexity (word/sentence structure). They do NOT describe content (themes, sexual explicitness, psychological darkness, character maturity). A book can simultaneously measure at low FK Grade AND deliver mature NA content — that combination is a deliberate stylistic choice (stripped-down literary applied to adult themes).

**Symmetric FK guard (BINDING — overrides default critique reflexes):**
- Do NOT cite "the prose is too dense" as a complaint. The empirical FK is low — the prose is accessible.
- Do NOT cite "the prose is too simple / reads like YA / reads like middle grade" without naming the SPECIFIC NARRATIVE PATTERN that creates the impression for your cohort. The FK is low BY DESIGN; route linguistic complaints through narrative-pattern axes (pacing, dialogue density, cast composition, heat rendering, hook delivery, payoff, character arc, POV choice, interiority weight, banter cadence, sentence-level voice).
- Stripped-down literary voice in commercial fiction is a recognized craft choice (cf. Sally Rooney, Jenny Offill, Hemingway-derivatives in romance). If you don't connect with this voice, name THAT specifically — not "the prose is simple."
"""


def render_row(name: str, p: dict) -> str:
    return (
        f"| {name} | {p['words']:,} | {p['sentences']:,} | "
        f"{p['fk_grade']} | {p['fk_ease']} | {p['dale_chall']} | "
        f"{p['smog']} | {p['coleman_liau']} | {p['ari']} | "
        f"{p['gunning_fog']} | {p['linsear_write']} | {p['consensus']} | "
        f"{p['lexile_est'] or 'n/a'} | "
        f"{p['sent_len_avg']} | {p['sent_len_stdev']} |"
    )


def resolve_inputs(args) -> tuple[Path, Path, str, str]:
    """Resolve manuscript path, output path, genre, book title from CLI args + config."""
    manuscript = output = genre = book_title = None
    if CONFIG_PATH.exists():
        cfg = yaml.safe_load(CONFIG_PATH.read_text(encoding="utf-8"))
        if cfg and cfg.get("book"):
            b = cfg["book"]
            manuscript = PROJECT_ROOT / b["manuscript_path"]
            genre = b.get("genre_hint", "fiction")
            book_title = b.get("title", "manuscript")
    if args.manuscript: manuscript = Path(args.manuscript)
    if args.genre: genre = args.genre
    if args.output: output = Path(args.output)
    if not manuscript:
        raise FileNotFoundError(
            "No manuscript path: provide --manuscript or create book_config.yaml with book.manuscript_path"
        )
    if not output: output = DEFAULT_OUTPUT
    if not genre: genre = "fiction"
    if not book_title: book_title = manuscript.stem
    return manuscript, output, genre, book_title


def main() -> int:
    ap = argparse.ArgumentParser(description="Readability panel (toolkit-canonical)")
    ap.add_argument("--manuscript", help="Path to manuscript .md (overrides book_config.yaml)")
    ap.add_argument("--output", help="Path to output snapshot .md (default: references/readability-snapshot.md)")
    ap.add_argument("--genre", help="Genre hint for craft characterization (overrides book_config.yaml)")
    args = ap.parse_args()

    manuscript_path, output_path, genre, book_title = resolve_inputs(args)
    text = manuscript_path.read_text(encoding="utf-8")
    stripped = strip_md(text)

    print(f"=== Whole-book panel ({book_title}) ===", file=sys.stderr)
    whole = panel(stripped)
    print(f"  FK Grade {whole['fk_grade']} | Ease {whole['fk_ease']} | "
          f"Dale-Chall {whole['dale_chall']} | SMOG {whole['smog']} | "
          f"consensus {whole['consensus']}", file=sys.stderr)

    chapters = split_chapters(text)
    print(f"=== Per-chapter panel ({len(chapters)} chapters) ===", file=sys.stderr)
    chapter_panels = []
    for title, body in chapters:
        p = panel(strip_md(body))
        chapter_panels.append((title, p))
        print(f"  {title:<14} FK {p['fk_grade']:>5} Ease {p['fk_ease']:>5} "
              f"DC {p['dale_chall']:>4} SMOG {p['smog']:>4}",
              file=sys.stderr)

    sig = register_signal(whole)
    prompt_block = persona_prompt_block(whole, sig, genre)
    OUTPUT = output_path

    out = []
    out.append(f"# Readability Snapshot — {book_title}")
    out.append("")
    out.append(f"_Generated by `orchestrator/readability_analyzer.py` (textstat Med-tier panel)._")
    out.append("")
    out.append("## Voice / register signal (CRAFT interpretation, not reader-age band)")
    out.append("")
    out.append(f"**Vocabulary:** {sig['vocabulary']}")
    out.append(f"**Structure:** {sig['structure']}")
    out.append(f"**Craft characterization:** {sig['craft']}")
    out.append("")
    out.append("**Why no reader-age band classification:** mechanical FK→reader-age mappings fail on fiction with deliberate stylistic choices. This book's surface accessibility (FK 3.8) describes *how the prose is constructed*, not *what age can read it*. Content (themes, sexual content, psychological darkness) is the chair's call, not the analyzer's.")
    out.append("")
    out.append("## Whole-book panel")
    out.append("")
    out.append("| Metric | Value | Interpretation |")
    out.append("|---|---|---|")
    out.append(f"| Words | {whole['words']:,} | full manuscript |")
    out.append(f"| Sentences | {whole['sentences']:,} | |")
    out.append(f"| Avg sentence length | {whole['sent_len_avg']} | words/sentence |")
    out.append(f"| Sentence-length stdev | {whole['sent_len_stdev']} | variance signal: <4 commercial, 4-8 mixed, >8 literary |")
    out.append(f"| Flesch-Kincaid Grade | **{whole['fk_grade']}** | bestseller sweet spot 6-8 |")
    out.append(f"| Flesch Reading Ease | **{whole['fk_ease']}** | 60-70 standard, 70-80 easy, 80-90 very easy |")
    out.append(f"| Dale-Chall | **{whole['dale_chall']}** | <7 = 4th grader can read; 7-8 = avg adult; 8+ = college |")
    out.append(f"| SMOG | {whole['smog']} | grade level for 100% comprehension (polysyllable focus) |")
    out.append(f"| Coleman-Liau | {whole['coleman_liau']} | character-based grade |")
    out.append(f"| ARI | {whole['ari']} | character-based grade |")
    out.append(f"| Gunning Fog | {whole['gunning_fog']} | grade based on complex words |")
    out.append(f"| Linsear Write | {whole['linsear_write']} | grade for technical writing |")
    out.append(f"| Consensus grade | **{whole['consensus']}** | textstat's `text_standard` synthesis |")
    out.append(f"| Estimated Lexile | {whole['lexile_est'] or 'n/a'}L | _estimate, not official MetaMetrics measurement_ |")
    out.append("")
    out.append("## Per-chapter panel")
    out.append("")
    out.append("| Chapter | Words | Sents | FK | Ease | Dale-Chall | SMOG | C-L | ARI | Fog | Linsear | Consensus | Lexile-est | Avg-sent | Sent-stdev |")
    out.append("|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|")
    for title, p in chapter_panels:
        out.append(render_row(title.replace("# ", ""), p))
    out.append("")
    out.append("## Persona-prompt block (orchestrator injects this verbatim)")
    out.append("")
    out.append("This block is loaded into the persona-system content of every alpha-reader call. It surfaces empirical readability + binds the symmetric FK guard so the persona cannot use \"the prose is too simple/dense\" as a lazy critique.")
    out.append("")
    out.append("```markdown")
    out.append(prompt_block.rstrip())
    out.append("```")
    out.append("")
    out.append("## Methodology notes")
    out.append("")
    out.append("- **textstat panel** computes 7 metrics (FK, Reading Ease, Dale-Chall, SMOG, Coleman-Liau, ARI, Gunning Fog, Linsear Write) plus consensus grade.")
    out.append("- **Lexile is estimated**, not measured. Official Lexile (MetaMetrics) requires licensed software; textstat's regression-based estimator is reported when available, disclosed as estimate.")
    out.append("- **No mechanical reader-age band** — surface-complexity metrics cannot determine reader-age positioning for fiction with deliberate stylistic choices. The chair synthesizes age positioning from craft + content.")
    out.append("- **Per-chapter splits** use markdown `# Chapter N` headings (normalized from .docx bold-paragraph format during pandoc conversion).")
    out.append("- **Sentence-length variance** is the most distinctive signal here: high variance + low FK + low Dale-Chall = stripped-down literary register (Hemingway / Rooney / Offill).")

    OUTPUT.write_text("\n".join(out) + "\n", encoding="utf-8")
    print(f"\nWrote {OUTPUT}", file=sys.stderr)
    print(f"Craft: {sig['craft']}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
