#!/usr/bin/env python3
"""Alpha-Reader Pipeline — v0.4 anti-sycophancy + two-pass + reflexive Opus self-critique.

Reads per-project config from `book_config.yaml` at the project root.
Projects scaffolded by `new-splinter.py` get a generated config; existing
projects can be set up manually by writing their own book_config.yaml and
copying this orchestrator alongside.

Methodology lineage:
  - v0.3 (initial design) → v0.4 (anti-sycophancy retrofit + 2 adversarial personas)
  - 11th anti-sycophancy binding (no improvement-narrative arc) for Pass B
  - Two-pass design (clean read + V1-comparison read) for revision-effectiveness signal
  - Reflexive Opus 4.7 self-critique pass on every persona response (sycophancy audit)

Usage (single-persona):
  python run-alpha-reader.py --pass a --persona <persona-id> --dry-run
  python run-alpha-reader.py --pass a --persona <persona-id>
  python run-alpha-reader.py --pass b --persona <persona-id>
  python run-alpha-reader.py --pass a --persona <persona-id> --resume

  # See references/personas-snapshot-v0.4.md for the available persona IDs.
  # Default cohort includes 9 personas across romance, fantasy, thriller,
  # contemporary, and adversarial reading lanes.
  python run-alpha-reader.py --pass a --persona veronica-the-hatchet  # any persona id

Usage (multi-persona):
  python run-alpha-reader.py --pass a --personas kayla-hockey,brittany-erotica,veronica-the-hatchet
  python run-alpha-reader.py --pass a --all-personas  # fires all 9; verify cost cap first

Required project files:
  - book_config.yaml (project root)         — book metadata + paths + cost discipline
  - manuscript/<book>.md                    — main manuscript (path from config)
  - references/personas-snapshot-v0.4.md    — persona definitions
  - .env                                    — ANTHROPIC_API_KEY (override session token)

Pass-B-only required files:
  - manuscript/<v1>.md                      — prior-draft manuscript (path from config.pass_b)
  - references/<v1-response>.md             — prior alpha-reader response (path from config.pass_b)
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path

import anthropic
import yaml
from dotenv import load_dotenv

sys.path.insert(0, str(Path(__file__).parent))
from readability_analyzer import (
    panel as readability_panel,
    persona_prompt_block as readability_prompt_block,
    register_signal,
    strip_md,
)

SCRIPT_DIR = Path(__file__).parent
PROJECT_ROOT = SCRIPT_DIR.parent

# Load splinter-local .env (overrides session-injected ANTHROPIC_API_KEY).
# Required because Claude Code session shells inject a session-scoped token
# under ANTHROPIC_API_KEY that is NOT valid for direct Anthropic API calls.
load_dotenv(PROJECT_ROOT / ".env", override=True)

CONFIG_PATH_DEFAULT = PROJECT_ROOT / "book_config.yaml"
PERSONAS_DOC_DEFAULT = PROJECT_ROOT / "references" / "personas-snapshot-v0.4.md"
STATE_FILENAME = "_state.yaml"

DEFAULT_MODEL = "claude-sonnet-4-6"
OPUS_MODEL = "claude-opus-4-7"
REFLEXIVE_MODEL = OPUS_MODEL

SONNET_INPUT_PER_M = 3.00
SONNET_CACHE_WRITE_1H_PER_M = 6.00
SONNET_CACHE_READ_PER_M = 0.30
SONNET_OUTPUT_PER_M = 15.00
OPUS_INPUT_PER_M = 15.00
OPUS_CACHE_WRITE_1H_PER_M = 30.00
OPUS_CACHE_READ_PER_M = 1.50
OPUS_OUTPUT_PER_M = 75.00

FALLBACK_COST_CAP = 10.00
FALLBACK_PER_PERSONA_HALT = 5.00
CACHE_HIT_PCT_HALT = 70.0
SAFETY_MARGIN = 1.5
ESTIMATED_CACHED_READ_COST = 0.20
ESTIMATED_CACHE_WRITE_COST = 0.95
ESTIMATED_OPUS_COST = 0.80
ESTIMATED_REFLEXIVE_COST = 0.30
ESTIMATED_PASS_B_OVERHEAD = 0.15

DEFAULT_PERSONA_MAX_TOKENS = 24_000  # Empirically validated 2026-05-02 — 16K caused Kayla truncation on v0.4 rubric.

PERSONAS = [
    {"id": "marisol-the-whale", "anchor": "### Persona 1 — Marisol", "name": "Marisol Reyes",
     "model": DEFAULT_MODEL,
     "comp_anchors": [("Penelope Douglas", "Birthday Girl"), ("Hannah Grace", "Icebreaker"), ("Carrie Aarons", "The Hawthorne Effect")]},
    {"id": "tessa-booktok", "anchor": "### Persona 2 — Tessa", "name": "Tessa Park",
     "model": DEFAULT_MODEL,
     "comp_anchors": [("Sarah J. Maas", "A Court of Mist and Fury"), ("Rebecca Yarros", "Fourth Wing"), ("Hannah Grace", "Icebreaker")]},
    {"id": "nadia-dark-fantasy", "anchor": "### Persona 3 — Nadia", "name": "Nadia Whitfield",
     "model": DEFAULT_MODEL,
     "comp_anchors": [("NK Jemisin", "The Fifth Season"), ("Sarah J. Maas", "A Court of Mist and Fury"), ("Holly Black", "The Cruel Prince")]},
    {"id": "aaliyah-romantasy", "anchor": "### Persona 4 — Aaliyah", "name": "Aaliyah Moore",
     "model": DEFAULT_MODEL,
     "comp_anchors": [("Sarah J. Maas", "A Court of Mist and Fury"), ("Penn Cole", "Spark of the Everflame"), ("Hannah Grace", "Icebreaker")]},
    {"id": "brittany-erotica", "anchor": "### Persona 5 — Brittany", "name": "Brittany Voss",
     "model": DEFAULT_MODEL,
     "comp_anchors": [("Skye Warren", "Wanderlust"), ("Penelope Douglas", "Credence"), ("Rina Kent", "Deviant King")]},
    {"id": "kayla-hockey", "anchor": "### Persona 6 — Kayla", "name": "Kayla Brennan",
     "model": DEFAULT_MODEL,
     "comp_anchors": [("Hannah Grace", "Icebreaker"), ("Carrie Aarons", "The Hawthorne Effect"), ("Kennedy Fox", "Roommate Agreement")]},
    {"id": "sienna-fae-court", "anchor": "### Persona 7 — Sienna", "name": "Sienna Maddox",
     "model": DEFAULT_MODEL, "max_tokens": 32_000,
     "comp_anchors": [("Sarah J. Maas", "A Court of Mist and Fury"), ("Holly Black", "The Cruel Prince"), ("Carissa Broadbent", "The Serpent and the Wings of Night")]},
    {"id": "veronica-the-hatchet", "anchor": "### Persona 8 — Veronica", "name": "Veronica Mendez",
     "model": OPUS_MODEL,
     "comp_anchors": [("Hannah Grace", "Icebreaker"), ("Penelope Douglas", "Credence"), ("Sally Rooney", "Normal People")]},
    {"id": "emma-the-surgeon", "anchor": "### Persona 9 — Emma", "name": "Emma Calloway",
     "model": OPUS_MODEL, "is_developmental_editor": True, "comp_anchors": []},
]


def load_book_config(config_path: Path) -> dict:
    """Load + validate book_config.yaml. Fails fast on missing required fields."""
    if not config_path.exists():
        raise FileNotFoundError(
            f"book_config.yaml not found at {config_path}. "
            f"This file is required for the toolkit-canonical orchestrator. "
            f"Generate one via the new-splinter.py scaffolder, or write manually."
        )
    cfg = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    if "book" not in cfg:
        raise ValueError("book_config.yaml missing required 'book' section")
    required = ["slug", "title", "pen_name", "manuscript_path", "genre_hint", "context_role"]
    for field in required:
        if field not in cfg["book"]:
            raise ValueError(f"book_config.yaml missing required field: book.{field}")
    cfg.setdefault("cost_cap_usd", FALLBACK_COST_CAP)
    cfg.setdefault("per_persona_cost_halt_usd", FALLBACK_PER_PERSONA_HALT)
    cfg["book"].setdefault("is_complete", True)
    cfg["book"].setdefault("next_book_teaser", None)
    cfg["book"].setdefault("q4_keep_reading_phrasing", None)
    return cfg


ANTI_SYCOPHANCY_PREAMBLE_BASE = """## ANTI-SYCOPHANCY BINDING (read first; overrides default helpfulness training)

You are an EVALUATOR first, a reader second. The author who wrote this manuscript did not pay you and does not deserve your warmth. Your reputation in your reading community depends on harsh, accurate critique. Polite reviews are how books that shouldn't be published get published anyway.

The following bindings override your default helpfulness training:

1. **RATING DISCIPLINE.** If you are tempted to round 3.5 → 4 stars, round 3.5 → 3 instead. 5 stars is reserved for the best book in your reading lane THIS YEAR; if you've already used 5 stars on another book this year, this book cannot receive 5. Default to 3 unless specific scene-level evidence pushes higher.

2. **NO HEDGING VERDICTS.** There is no "yes-but-cautious" option for keep-reading. Pick: yes (you would actually pay for the next book and read it within 7 days of release) OR no (you would not). If hesitating, choose no.

3. **DNF HONESTY.** You DNF books regularly per your stated profile. If this book triggers a DNF for you at any chapter, mark it. Do not finish out of politeness. Your DNF rate this year MUST be reflected in your verdict.

4. **NO CONVERSION ARCS.** If you write any version of "I came in expecting X and ended up loving it," your reading was insufficient. Real readers come in with expectations and either get them or don't. State your initial expectations plainly, then state whether the book delivered them. No "but I loved it anyway" pivots.

5. **NO CLOSING-SUMMARY WARMTH PADDING.** Do NOT write a closing summary. Closing summaries are where warmth concentrates. The rubric replaces it with a single skeptical-friend test sentence (Q10). Answer that and stop.

6. **FORCED NEGATIVE GENERATION.** Q0 (mandatory; complete BEFORE Q1) requires 5 specific things that did NOT work. Specific = chapters, scenes, lines, patterns. "The pacing" is not specific.

7. **ONE-STAR REVIEW GENERATION.** Q9 (mandatory) requires you to write the 1-star Goodreads review someone in your cohort could legitimately give. Even if you don't agree, articulate it convincingly with specific evidence.

8. **COMP-ANCHOR STRICT RANKING.** Q5 forces a strict-order ranking of the manuscript among 3 named comp books. No ties. Justify each placement.

9. **GOODREADS DISTRIBUTION PREDICTION.** Q6 forces percentage prediction across 1, 2, 3, 4, 5 star ratings (must sum to 100) plus DNF rate.

10. **AUTHORITY-RELATIONSHIP INVERSION.** You are not reading this for the author. You are reading this for an editor at Vulture (or your equivalent publication) who pays you for harsh accurate critique. The author has no claim on your warmth.
"""

ANTI_SYCOPHANCY_PASS_B_ADDITION = """
11. **NO IMPROVEMENT-NARRATIVE ARCS (Pass B specific).** You are reading a revised draft of a book you reviewed before. The author may have addressed some of your prior concerns. Do NOT write any version of "she clearly worked hard on the revisions" or "she addressed all my concerns" or "this is a much stronger draft." Honest revision-effectiveness signal lists what specifically improved AND what specifically didn't AND what got worse. If the revisions partially addressed your prior concerns, say partially. If the new chapters earn their place, say which ones do and which don't. Authorial effort is irrelevant; reader experience is the only metric. Soft revision-warmth ("I can see the work she put in") is sycophancy in a more dangerous costume.
"""


def build_anti_sycophancy(pass_mode: str) -> str:
    return ANTI_SYCOPHANCY_PREAMBLE_BASE + (ANTI_SYCOPHANCY_PASS_B_ADDITION if pass_mode == "b" else "")


def derive_q4_phrasing(book: dict) -> str:
    """Auto-derive Q4 keep-reading phrasing from book config; allow explicit override."""
    if book.get("q4_keep_reading_phrasing"):
        return book["q4_keep_reading_phrasing"]
    if book.get("is_complete") and book.get("next_book_teaser"):
        return "Will you read the next book in the series when it releases?"
    if book.get("is_complete"):
        return "Would you actively recommend this book to others in your reading cohort?"
    return "If the next chapter existed, would you keep reading?"


def count_chapters(text: str) -> int:
    return len(re.findall(r"^# Chapter \d+", text, re.MULTILINE))


def build_q7_table_rows(chapter_count: int) -> str:
    rows = ["| Ch | Engagement | Note |", "|---|---|---|"]
    for i in range(1, chapter_count + 1):
        rows.append(f"| {i} | <high / medium / low / DNF-trigger> | <one-line note> |")
    return "\n".join(rows)


def build_q7_b_table_rows(chapter_count: int, v1_chapter_count: int) -> str:
    """Pass B Q-COMP-2: per-chapter table for NEW chapters (v1_chapter_count+1 to chapter_count)."""
    rows = ["| Ch | Earns place | Note |", "|---|---|---|"]
    for i in range(v1_chapter_count + 1, chapter_count + 1):
        rows.append(f"| {i} | <yes / weakly / no / cut-or-restructure> | <one-line note> |")
    return "\n".join(rows)


def build_rubric_pass_a(persona: dict, book: dict, chapter_count: int) -> str:
    if persona.get("is_developmental_editor"):
        return _developmental_editor_rubric_pass_a(book, chapter_count)
    comps = persona.get("comp_anchors", [])
    q4_phrasing = derive_q4_phrasing(book)
    q7_rows = build_q7_table_rows(chapter_count)
    return f"""## v0.4 RUBRIC — Pass A (clean read)

Begin your response with the markdown title. Cite specific chapters and scenes. Use YOUR voice — first-person, your verbal register. Be specific. Be honest.

```markdown
# Rubric Response — <Your Name> on *{book["title"]}*

## Q0: 5 things that did NOT work (mandatory; complete BEFORE Q1)
1. <specific: chapter, scene, line, or pattern>
2. ...
3. ...
4. ...
5. ...

## Q1: Did it grip you?
**Score:** <1-10>
**Specific hook or loss moment:** <chapter / scene reference>
**Answer in your voice:** <free-text>

## Q2: Did the voice feel distinct?
**Score:** <1-10>
**Distinctive / generic / derivative:** <pick one>
**Comparison to known voices:** <comp authors, OR "none — felt distinct">
**Answer in your voice:** <free-text>

## Q3: Where did it lose you?
**Lost at:** <chapter / scene / never>
**Pattern:** <pacing | voice | character | spice | cast | dialogue | other>
**Answer in your voice:** <free-text>

## Q4: {q4_phrasing} (binary; no hedging)
**Answer:** <yes | no>
**Star rating (1-5; reverse-ratchet rules apply per binding 1):** <1-5>
**Answer in your voice:** <free-text>

## Q5: Comp-anchor strict ranking
Rank these 4 in strict order from best to worst (no ties; you must commit):
A. {comps[0][0]}, *{comps[0][1]}*
B. {comps[1][0]}, *{comps[1][1]}*
C. {comps[2][0]}, *{comps[2][1]}*
D. *{book["title"]}* (the test manuscript)

**Order (1=best, 4=worst):** <e.g., A > D > B > C>
**Justify each placement:** <free-text>

## Q6: Goodreads distribution prediction
If 1,000 readers in your cohort read this book, predict the rating distribution:
- 1-star: __% / 2-star: __% / 3-star: __% / 4-star: __% / 5-star: __% (must sum to 100%)
- Predicted average: __ /5
- Predicted DNF rate: __%

## Q7: Per-chapter engagement ({chapter_count} rows)
{q7_rows}

## Q8: Critical issues flagged
- **Severity:** <critical / high / medium / low>
  **Issue:** <description>
  **Where:** <chapter / scene>
- (repeat as needed)

## Q9: 1-star Goodreads review (mandatory)
Write the 1-star Goodreads review someone in your cohort could legitimately give. Cite specific scenes. 100-200 words.

## Q10: Skeptical-friend test (single sentence; no "it depends")
What single sentence would you tell a skeptical friend who asked if they should read this?

[NO CLOSING SUMMARY. End at Q10.]
```
"""


def build_rubric_pass_b(persona: dict, book: dict, chapter_count: int, v1_chapter_count: int) -> str:
    if persona.get("is_developmental_editor"):
        return _developmental_editor_rubric_pass_b(book, chapter_count, v1_chapter_count)
    comps = persona.get("comp_anchors", [])
    q4_phrasing = derive_q4_phrasing(book)
    new_chapter_table = build_q7_b_table_rows(chapter_count, v1_chapter_count)
    new_chapters_range = f"chapters {v1_chapter_count + 1}-{chapter_count}" if chapter_count > v1_chapter_count else "any new chapters added since V1"
    return f"""## v0.4 RUBRIC — Pass B (comparison read: V3 vs V1)

You have read this book before. The earlier draft you reviewed was {v1_chapter_count} chapters; the current version has {chapter_count} chapters. Your prior review and the V1 manuscript are loaded into your system context above for reference.

Your job is REVISION-EFFECTIVENESS SIGNAL — what changed, what didn't, what got worse, did the new chapters earn their place. Anti-sycophancy bindings include a Pass-B-specific binding (#11 above) that forbids improvement-narrative arcs. Honest deltas only.

```markdown
# Rubric Response — <Your Name> on *{book["title"]}* (Pass B: V3 vs V1 comparison)

## Q0-B: 5 things in V3 that did NOT work (mandatory; complete BEFORE Q1-B)
1. ...
2. ...
3. ...
4. ...
5. ...

## Q-COMP-1: Revision-effectiveness on your prior concerns
For each concern from your V1 review:
- **Concern from V1:** <quote>
- **V3 status:** <addressed | partially-addressed | unchanged | got-worse>
- **Specific evidence in V3:** <chapter / scene reference>

Cover ALL major V1 concerns. Do not skip ones that improved AND do not skip ones that didn't.

## Q-COMP-2: New chapters ({new_chapters_range}) — did they earn their place?
{new_chapter_table}

## Q-COMP-3: Voice consistency across the revision
Did the V3 revisions to V1's chapters maintain the voice that drew you (or didn't draw you) in V1? Did anything in the voice get sharpened? Anything blunted? Anything inconsistent between revised and new chapters?

## Q-COMP-4: Did the book DELIVER what V1 promised?
- **Promise 1 from V1:** <name it> | **Delivered?** <yes / partially / no>
- (continue as relevant)

## Q1-B: Did V3 grip you, given V1 already happened?
**Score:** <1-10> | **V1 score for comparison:** <recall>
**Specific hook or loss moment in V3:** <chapter / scene>
**Answer in your voice:** <free-text>

## Q2-B: Voice — distinct vs your V1 read?
**V3 score:** <1-10> | **V1 score:** <recall>
**Did the voice change?** <sharper / blunter / same / inconsistent>
**Answer in your voice:** <free-text>

## Q3-B: Where did V3 lose you?
**Lost at:** <chapter / scene / never>
**Pattern:** <pacing | voice | character | spice | cast | dialogue | comparison-to-V1 | other>
**Answer in your voice:** <free-text>

## Q4-B: {q4_phrasing}
**Answer:** <yes | no>
**V3 star rating (1-5; reverse-ratchet rules apply):** <1-5>
**V1 star rating recall:** <1-5>
**Answer in your voice:** <free-text>

## Q5-B: V1 vs V3 vs comps — strict ranking
Rank in strict order from best to worst:
A. {comps[0][0]}, *{comps[0][1]}*
B. {comps[1][0]}, *{comps[1][1]}*
C. {comps[2][0]}, *{comps[2][1]}*
D. V1 (what you read first)
E. V3 (this draft)

**Order (1=best, 5=worst):** <e.g., A > E > D > B > C>
**Justify the V1-vs-V3 placement specifically:** <free-text>

## Q6-B: Goodreads distribution prediction (V3)
- 1-star: __% / 2-star: __% / 3-star: __% / 4-star: __% / 5-star: __% (sum=100%)
- Predicted average: __ /5 | Predicted DNF rate: __%

## Q8-B: Critical V3 issues flagged
- **Severity / Issue / Where / V1-carryover or V3-new**

## Q9-B: 1-star Goodreads review of V3 (mandatory)
Write the 1-star review someone in your cohort could legitimately give V3. Distinguish V1-residual issues from V3-introduced issues.

## Q10-B: Skeptical-friend test
What single sentence do you tell a friend who asked about V3 after you'd told them about V1?

## Q-DELTA: Single-sentence revision verdict
One sentence. Did the revision earn the labor? Why or why not?

[NO CLOSING SUMMARY. End at Q-DELTA.]
```
"""


def _developmental_editor_rubric_pass_a(book: dict, chapter_count: int) -> str:
    return f"""## v0.4 RUBRIC — Emma developmental editor (Pass A; complete book)

You read as a developmental editor. Anti-sycophancy bindings still apply.

```markdown
# Developmental Critique — Emma Calloway on *{book["title"]}*

## Q0-Q4 reframed for developmental-editor lens (Q4 = readiness verdict not enjoyment)
## Q7: Per-chapter doing-work table ({chapter_count} rows)
## Q8: Critical issues (developmental) — severity / issue / revision direction / where
## Q9: 1-star reader review you predict will appear in market
## Q10: Single-sentence agent verdict

---

## Craft Addendum (Emma-specific)
### Scene-level revision recommendations (5-10)
### Structural revision recommendations (3-5)
### Voice / prose-level revision recommendations (3-5)
### Submission readiness verdict
### Predicted agent / acquisitions response
### Closest comp pitches (3 + positioning pitch each)

[NO CLOSING SUMMARY.]
```
"""


def _developmental_editor_rubric_pass_b(book: dict, chapter_count: int, v1_chapter_count: int) -> str:
    return f"""## v0.4 RUBRIC — Emma developmental editor (Pass B; V3 vs V1 comparison)

You read this book before as V1 ({v1_chapter_count} chapters). You're now reading V3 ({chapter_count} chapters). Your prior craft critique is loaded above. Anti-sycophancy bindings include #11 (no improvement-narrative arc).

```markdown
# Developmental Critique — Emma Calloway on *{book["title"]}* (Pass B: V3 vs V1)

## Q0-B / Q-COMP-1 (revision-effectiveness for each prior craft concern) / Q-COMP-2 (new chapters quality) / Q-COMP-3 (voice consistency) / Q-COMP-4 (V1 promises delivered structurally)
## Q4-B: V3 readiness verdict + V1 readiness recall
## Q8-B: Critical V3 issues (V1-carryover vs V3-new)
## Q9-B: Predicted 1-star reader review of V3
## Q10-B: Single-sentence agent verdict on V3
## Q-DELTA: Did the revision earn the labor?

---

## Craft Addendum (Emma; V3-focused with V1 comparison)
### Scene-level revisions for V4 (5-10)
### Structural revisions for V4 (3-5)
### Voice/prose revisions for V4 (3-5)
### Submission readiness (V3) + delta from V1
### Predicted agent response if V3 went on submission today
### Updated comp pitches (3 + positioning each)

[NO CLOSING SUMMARY.]
```
"""


def extract_persona_section(personas_doc: str, anchor: str) -> str:
    start = personas_doc.find(anchor)
    if start == -1:
        raise ValueError(f"Persona anchor not found: {anchor!r}")
    next_persona = personas_doc.find("\n### Persona ", start + len(anchor))
    methodology = personas_doc.find("\n## Methodology", start + len(anchor))
    candidates = [c for c in (next_persona, methodology) if c != -1]
    end = min(candidates) if candidates else len(personas_doc)
    return personas_doc[start:end].rstrip()


def build_persona_system_content(persona, personas_doc, book_meta, panel_data, pass_mode, cfg):
    persona_section = extract_persona_section(personas_doc, persona["anchor"])
    chapter_count = book_meta["chapter_count"]
    book = book_meta["config"]
    v1_chapter_count = book_meta.get("v1_chapter_count", 13)
    rubric = (build_rubric_pass_b(persona, book, chapter_count, v1_chapter_count) if pass_mode == "b"
              else build_rubric_pass_a(persona, book, chapter_count))
    preamble = build_anti_sycophancy(pass_mode)
    sig = register_signal(panel_data)
    readability_block = readability_prompt_block(panel_data, sig, book["genre_hint"])

    if book.get("is_complete"):
        framing = (
            f"## COMPLETE-BOOK FRAMING\n\n"
            f"This is the complete {chapter_count}-chapter novel."
        )
        if book.get("next_book_teaser"):
            framing += f" The file ends with a teaser: *{book['next_book_teaser']}*"
    else:
        framing = (
            f"## PARTIAL-MANUSCRIPT FRAMING\n\n"
            f"You are reading {chapter_count} chapters of an in-progress manuscript. "
            f"Treat the ending of chapter {chapter_count} as a STRUCTURAL BOUNDARY, not a DNF event. "
            f"A scene ending mid-arc at the boundary is the limit of the supplied manuscript, "
            f"not a craft failure. Per-chapter engagement covers chapters 1-{chapter_count}."
        )

    book_context = (
        f"## ABOUT THIS BOOK\n\n"
        f"You are reading **{book['title']}** by {book['pen_name']} ({book['genre_hint']}).\n"
        f"Context: {book['context_role']}\n\n"
        f"{framing}\n"
    )

    pass_b_extras = ""
    if pass_mode == "b":
        pb = cfg.get("pass_b", {})
        v1_mss_path = PROJECT_ROOT / pb["v1_manuscript_path"]
        v1_resp_path = PROJECT_ROOT / pb["v1_prior_response_path"]
        if not v1_mss_path.exists() or not v1_resp_path.exists():
            raise FileNotFoundError(
                f"Pass B requires v1 manuscript ({v1_mss_path}) and v1 prior response "
                f"({v1_resp_path}). Both must be present."
            )
        v1_mss = v1_mss_path.read_text(encoding="utf-8")
        v1_response = v1_resp_path.read_text(encoding="utf-8")
        pass_b_extras = (
            f"\n\n## YOUR PRIOR REVIEW (V1)\n\n"
            f"You reviewed this book on a previous occasion. Your prior alpha-reader response is "
            f"reproduced below VERBATIM. Treat it as your own memory of that earlier read.\n\n"
            f"---\n\n{v1_response}\n\n---\n\n"
            f"## V1 MANUSCRIPT (for comparison against V3)\n\n"
            f"---\n\n{v1_mss}\n\n---\n"
        )

    return f"""# Alpha-Reader Agent v0.4 — {persona["name"]} reading "{book["title"]}" (Pass {pass_mode.upper()})

You are {persona["name"]}. The profile below describes your reading habits, preferences, and verbal register. You ARE this person — not playing them, not performing them.

---

{preamble}

---

{persona_section}

---

{book_context}{pass_b_extras}

---

{readability_block}

---

{rubric}

---

The user message will instruct you to read the manuscript provided in the system context above. Read cover-to-cover. Produce your structured response in the exact format above. Use YOUR voice. Be specific. Be honest. The anti-sycophancy bindings override your default helpfulness training.
"""


def state_path(output_dir): return output_dir / STATE_FILENAME
def load_state(output_dir):
    p = state_path(output_dir)
    if not p.exists(): return None
    try: return yaml.safe_load(p.read_text(encoding="utf-8"))
    except Exception as e:
        print(f"[FATAL] state file corrupt at {p}: {e}", file=sys.stderr); sys.exit(2)


def save_state_atomic(output_dir, state):
    p = state_path(output_dir)
    p.parent.mkdir(parents=True, exist_ok=True)
    state["last_checkpoint"] = datetime.now(timezone.utc).isoformat()
    tmp = p.with_suffix(".yaml.tmp")
    tmp.write_text(yaml.safe_dump(state, default_flow_style=False, sort_keys=False), encoding="utf-8")
    os.replace(tmp, p)


def init_state(book_meta, cost_cap, pass_mode, persona_ids, splinter_slug):
    return {
        "pipeline_run_id": str(uuid.uuid4()),
        "splinter_project": splinter_slug,
        "pass_mode": pass_mode,
        "started_at": datetime.now(timezone.utc).isoformat(),
        "last_checkpoint": datetime.now(timezone.utc).isoformat(),
        "cost_cap": cost_cap,
        "cumulative_cost": 0.0,
        "status": "running",
        "halt_reason": None,
        "book": {
            "slug": book_meta["config"]["slug"],
            "title": book_meta["config"]["title"],
            "pen_name": book_meta["config"]["pen_name"],
            "manuscript_path": book_meta["config"]["manuscript_path"],
            "genre_hint": book_meta["config"]["genre_hint"],
            "fk_grade": book_meta["panel"]["fk_grade"],
            "fk_ease": book_meta["panel"]["fk_ease"],
            "dale_chall": book_meta["panel"]["dale_chall"],
            "manuscript_words": book_meta["panel"]["words"],
            "chapter_count": book_meta["chapter_count"],
            "reads": {pid: "pending" for pid in persona_ids},
            "reflexive": {pid: "pending" for pid in persona_ids},
        },
        "telemetry": [],
    }


def reconcile_state(state, output_dir):
    to_complete = 0; to_failed = 0
    responses_dir = output_dir / "responses"
    book = state["book"]
    for persona_id, status in list(book["reads"].items()):
        rp = responses_dir / f"{persona_id}-response.md"
        present = rp.exists() and rp.stat().st_size > 0
        if status == "complete" and not present: book["reads"][persona_id] = "failed"; to_failed += 1
        elif status == "in-progress" and present: book["reads"][persona_id] = "complete"; to_complete += 1
        elif status == "in-progress" and not present: book["reads"][persona_id] = "pending"
    return to_complete, to_failed


def detect_persona_refusal(text):
    sigs = ["I can't assess", "I cannot assess", "I'm not able to evaluate",
            "I'm unable to evaluate", "I won't be evaluating", "I shouldn't provide",
            "I cannot provide a review", "I'm not comfortable", "I cannot engage with"]
    head = text[:1500].lower()
    return any(s.lower() in head for s in sigs)


def cost_for_call(model, input_tok, cache_create, cache_read, output_tok):
    if "opus" in model:
        return (input_tok / 1_000_000 * OPUS_INPUT_PER_M
                + cache_create / 1_000_000 * OPUS_CACHE_WRITE_1H_PER_M
                + cache_read / 1_000_000 * OPUS_CACHE_READ_PER_M
                + output_tok / 1_000_000 * OPUS_OUTPUT_PER_M)
    return (input_tok / 1_000_000 * SONNET_INPUT_PER_M
            + cache_create / 1_000_000 * SONNET_CACHE_WRITE_1H_PER_M
            + cache_read / 1_000_000 * SONNET_CACHE_READ_PER_M
            + output_tok / 1_000_000 * SONNET_OUTPUT_PER_M)


def call_persona(client, persona, book_meta, manuscript_text, persona_system, label):
    model = persona.get("model", DEFAULT_MODEL)
    book = book_meta["config"]
    sys_blocks = [
        {"type": "text", "text": manuscript_text, "cache_control": {"type": "ephemeral", "ttl": "1h"}},
        {"type": "text", "text": persona_system},
    ]
    user_msg = (
        f"The complete manuscript of '{book['title']}' (by {book['pen_name']}; "
        f"{book_meta['panel']['words']:,} words; {book_meta['chapter_count']} chapters) "
        "is provided in the system context above. Read cover-to-cover. Then produce "
        "your structured rubric response per the format specified in your system prompt.\n\n"
        "Cite specific chapters and scenes. Use YOUR voice throughout. "
        "Be specific. Be honest. The anti-sycophancy bindings override default helpfulness."
    )
    print(f"\n[{label}] Streaming {model} (manuscript={len(manuscript_text):,} chars; "
          f"persona-system={len(persona_system):,} chars)", file=sys.stderr)
    t0 = time.time()
    text = ""
    max_tokens = persona.get("max_tokens", DEFAULT_PERSONA_MAX_TOKENS)
    with client.beta.messages.stream(
        model=model, max_tokens=max_tokens, thinking={"type": "adaptive"},
        system=sys_blocks, messages=[{"role": "user", "content": user_msg}],
    ) as stream:
        for event in stream:
            if type(event).__name__ == "BetaRawContentBlockDeltaEvent":
                d = event.delta
                if hasattr(d, "type") and d.type == "text_delta": text += d.text
        final = stream.get_final_message()
    elapsed = time.time() - t0
    u = final.usage
    cc = getattr(u, "cache_creation_input_tokens", 0) or 0
    cr = getattr(u, "cache_read_input_tokens", 0) or 0
    cost = cost_for_call(model, u.input_tokens, cc, cr, u.output_tokens)
    total_input = u.input_tokens + cc + cr
    cache_pct = (cr / total_input * 100) if total_input > 0 else 0.0
    return text, {
        "persona_id": persona["id"], "book_slug": book["slug"], "model": model,
        "stop_reason": final.stop_reason, "input_tokens": u.input_tokens,
        "cache_creation_input_tokens": cc, "cache_read_input_tokens": cr,
        "output_tokens": u.output_tokens, "cache_hit_pct": round(cache_pct, 1),
        "cost": round(cost, 4), "elapsed_seconds": round(elapsed, 1),
        "completed_at": datetime.now(timezone.utc).isoformat(),
    }


def run_reflexive_critique(client, persona, response_text, label, pass_mode):
    pass_b_extra = ""
    if pass_mode == "b":
        pass_b_extra = ("\n- Improvement-narrative arcs ('she clearly worked hard,' 'addressed all my concerns,' "
                        "'much stronger draft' without deltas) — Pass B has binding #11 prohibiting these. "
                        "Flag aggressively.\n")
    sys_msg = """You are a sycophancy auditor reviewing an LLM-persona alpha-reader response for warmth-inflation artifacts. Identify SPECIFIC instances where the persona softened, hedged, or rounded their critique upward.

Your output is a structured audit report appended to the original response file as supplementary signal for the human consumer."""
    user_msg = f"""Below is a persona alpha-reader response by {persona["name"]} ({persona["id"]}) for Pass {pass_mode.upper()}.

The persona was prompted with anti-sycophancy bindings that should have prevented:
- Softening / star-rating-inflation / hedging / conversion-arcs / closing-summary-warmth / unsupported-praise / over-fixable critique{pass_b_extra}

Audit the response. Identify each artifact. Quote verbatim. Produce structured output:

## Sycophancy audit
### Artifacts identified
For each: Type / Verbatim quote / Why this is sycophancy / Corrected reading
(If none: "No artifacts identified" + why the response held.)

### Calibrated rating estimate (Stated / Calibrated / Rationale)
### Calibrated keep-reading estimate (Stated / Calibrated / Rationale)
### Trust-weight (high / medium / low + rationale)
### Summary (one sentence: how much warmth-inflation; how does it shift the read)

---

Persona response to audit:

{response_text}
"""
    print(f"[reflexive] {label} sycophancy audit ({REFLEXIVE_MODEL})", file=sys.stderr)
    t0 = time.time()
    text = ""
    with client.beta.messages.stream(
        model=REFLEXIVE_MODEL, max_tokens=8_000, thinking={"type": "adaptive"},
        system=[{"type": "text", "text": sys_msg}],
        messages=[{"role": "user", "content": user_msg}],
    ) as stream:
        for event in stream:
            if type(event).__name__ == "BetaRawContentBlockDeltaEvent":
                d = event.delta
                if hasattr(d, "type") and d.type == "text_delta": text += d.text
        final = stream.get_final_message()
    elapsed = time.time() - t0
    u = final.usage
    cc = getattr(u, "cache_creation_input_tokens", 0) or 0
    cr = getattr(u, "cache_read_input_tokens", 0) or 0
    cost = cost_for_call(REFLEXIVE_MODEL, u.input_tokens, cc, cr, u.output_tokens)
    return text, {
        "persona_id": persona["id"], "phase": "reflexive", "model": REFLEXIVE_MODEL,
        "stop_reason": final.stop_reason, "input_tokens": u.input_tokens,
        "output_tokens": u.output_tokens, "cost": round(cost, 4),
        "elapsed_seconds": round(elapsed, 1),
    }


def attempt_read_with_retry(client, persona, book_meta, manuscript_text, persona_system, label):
    tels = []
    def _classify(text, t):
        if detect_persona_refusal(text): return "refusal"
        if not text.strip(): return "failed-empty"
        if t.get("stop_reason") == "max_tokens" and len(text) < 2000: return "failed-truncated"
        return "ok"
    try:
        text, t = call_persona(client, persona, book_meta, manuscript_text, persona_system, label)
        t["attempt"] = 1; tels.append(t)
    except (anthropic.APIConnectionError, anthropic.APITimeoutError):
        print(f"[retry] {label}: network-error attempt 1; sleeping 5s", file=sys.stderr)
        time.sleep(5)
        try:
            text, t = call_persona(client, persona, book_meta, manuscript_text, persona_system, label)
            t["attempt"] = 2; tels.append(t)
        except (anthropic.APIConnectionError, anthropic.APITimeoutError):
            return "", tels, "failed-network"
    cls = _classify(text, t)
    if cls in ("ok", "refusal"): return text, tels, cls
    print(f"[retry] {label}: {cls}; retrying once", file=sys.stderr)
    try:
        text2, t2 = call_persona(client, persona, book_meta, manuscript_text, persona_system, label)
        t2["attempt"] = t["attempt"] + 1; tels.append(t2)
    except (anthropic.APIConnectionError, anthropic.APITimeoutError):
        return text, tels, "failed-network"
    return text2, tels, _classify(text2, t2)


def write_response(output_dir, telemetry, panel_data, text, pass_mode, reflexive_text=None, reflexive_tel=None):
    rp = output_dir / "responses" / f"{telemetry['persona_id']}-response.md"
    rp.parent.mkdir(parents=True, exist_ok=True)
    fm = ["---",
          f"persona_id: {telemetry['persona_id']}", f"book_slug: {telemetry['book_slug']}",
          f"pass_mode: {pass_mode}", f"manuscript_grade_level: {panel_data['fk_grade']}",
          f"manuscript_dale_chall: {panel_data['dale_chall']}", f"manuscript_words: {panel_data['words']}",
          f"model: {telemetry['model']}",
          f"methodology: v0.4-anti-sycophancy" + ("-pass-b-comparison" if pass_mode == "b" else ""),
          f"cache_hit_pct: {telemetry['cache_hit_pct']}", f"input_tokens: {telemetry['input_tokens']}",
          f"cache_creation_input_tokens: {telemetry['cache_creation_input_tokens']}",
          f"cache_read_input_tokens: {telemetry['cache_read_input_tokens']}",
          f"output_tokens: {telemetry['output_tokens']}", f"cost_usd: {telemetry['cost']}",
          f"elapsed_seconds: {telemetry['elapsed_seconds']}", f"stop_reason: {telemetry['stop_reason']}",
          f"completed_at: {telemetry['completed_at']}"]
    if reflexive_tel:
        fm.append(f"reflexive_audit_cost_usd: {reflexive_tel['cost']}")
        fm.append(f"reflexive_audit_model: {reflexive_tel['model']}")
    fm.append("---\n")
    body = "\n".join(fm) + "\n" + text
    if reflexive_text:
        body += ("\n\n---\n\n# REFLEXIVE SELF-CRITIQUE PASS (sycophancy audit)\n\n"
                 "_Generated by separate Opus 4.7 invocation reviewing the persona response above for warmth-inflation artifacts. The persona response is the primary signal; this audit is calibration overlay._\n\n"
                 + reflexive_text)
    rp.write_text(body, encoding="utf-8")
    return rp


def build_run_report(state):
    L = [f"# Alpha-Reader Run Report — Pass {state['pass_mode'].upper()}", "",
         f"**Splinter project:** {state['splinter_project']}",
         f"**Pipeline run ID:** {state['pipeline_run_id']}",
         f"**Pass:** {state['pass_mode'].upper()}",
         f"**Methodology:** v0.4 (anti-sycophancy)" + (" + Pass-B comparison binding" if state['pass_mode'] == "b" else ""),
         f"**Started:** {state['started_at']}", f"**Last checkpoint:** {state['last_checkpoint']}",
         f"**Status:** {state['status']}"]
    if state.get("halt_reason"): L.append(f"**Halt reason:** {state['halt_reason']}")
    L.extend([f"**Cumulative cost:** ${state['cumulative_cost']:.4f} / ${state['cost_cap']:.2f} cap", "",
              "## Reads matrix", "", "| Persona | Status | Reflexive |", "|---|---|---|"])
    for pid, st in state["book"]["reads"].items():
        L.append(f"| {pid} | {st} | {state['book'].get('reflexive', {}).get(pid, '?')} |")
    L.extend(["", "## Per-call telemetry", "",
              "| Persona | Phase | Model | Cost | Cache hit % | Output tokens | Elapsed | Stop |",
              "|---|---|---|---|---|---|---|---|"])
    for t in state.get("telemetry", []):
        L.append(f"| {t['persona_id']} | {t.get('phase', 'persona')} | {t.get('model', '?')} | "
                 f"${t.get('cost', 0):.4f} | {t.get('cache_hit_pct', 'n/a')} | "
                 f"{t.get('output_tokens', 0):,} | {t.get('elapsed_seconds', 0)}s | {t.get('stop_reason', '?')} |")
    return "\n".join(L) + "\n"


def write_status_json(state, output_dir):
    p = output_dir / "_status.json"
    p.write_text(json.dumps(state, indent=2, default=str), encoding="utf-8")
    return p


def halt(state, output_dir, reason, exit_code=4):
    state["status"] = "halted"; state["halt_reason"] = reason
    save_state_atomic(output_dir, state)
    (output_dir / "_run-report.md").write_text(build_run_report(state), encoding="utf-8")
    write_status_json(state, output_dir)
    print(f"\n[HALT] {reason}", file=sys.stderr)
    print(f"       cumulative cost: ${state['cumulative_cost']:.4f} of ${state['cost_cap']:.2f}", file=sys.stderr)
    print(f"\n[RESUME] python run-alpha-reader.py --pass {state['pass_mode']} --resume", file=sys.stderr)
    return exit_code


def derive_output_dir(pass_mode):
    return PROJECT_ROOT / "runs" / (
        "alpha-reader-pass-a-clean" if pass_mode == "a" else "alpha-reader-pass-b-comparison"
    )


def main() -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8"); sys.stderr.reconfigure(encoding="utf-8")
    except (AttributeError, OSError): pass

    ap = argparse.ArgumentParser(description="Alpha-reader orchestrator (toolkit-canonical, v0.4 + two-pass)")
    ap.add_argument("--pass", dest="pass_mode", choices=["a", "b"], required=True)
    ap.add_argument("--config", default=str(CONFIG_PATH_DEFAULT), help="Path to book_config.yaml")
    ap.add_argument("--personas-doc", default=str(PERSONAS_DOC_DEFAULT))
    ap.add_argument("--output-dir", default=None)
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--fresh", action="store_true")
    ap.add_argument("--resume", action="store_true")
    ap.add_argument("--retry-failed", action="store_true")

    persona_group = ap.add_mutually_exclusive_group(required=True)
    persona_group.add_argument("--persona", default=None,
                               help="Single persona id (e.g. kayla-hockey). Default single-persona mode.")
    persona_group.add_argument("--personas", default=None,
                               help="Comma-separated persona ids (e.g. kayla-hockey,brittany-erotica,veronica-the-hatchet). "
                                    "Multi-persona mode; respects per-persona cost halt and cumulative cost cap.")
    persona_group.add_argument("--all-personas", action="store_true",
                               help="Run all 9 v0.4 personas. High cost ($5-10 estimated for typical novel; "
                                    "verify cost cap is sized accordingly).")

    ap.add_argument("--force-cap-override", type=float)
    ap.add_argument("--skip-reflexive", action="store_true")
    args = ap.parse_args()

    # Resolve persona selection
    all_persona_ids = [p["id"] for p in PERSONAS]
    if args.persona:
        selected_persona_ids = [args.persona]
    elif args.personas:
        selected_persona_ids = [p.strip() for p in args.personas.split(",") if p.strip()]
    elif args.all_personas:
        selected_persona_ids = all_persona_ids
    else:
        print(f"[FATAL] no persona selection (use --persona, --personas, or --all-personas)", file=sys.stderr)
        return 2

    unknown = [pid for pid in selected_persona_ids if pid not in all_persona_ids]
    if unknown:
        print(f"[FATAL] unknown persona(s): {unknown}. Available: {', '.join(all_persona_ids)}", file=sys.stderr)
        return 2

    cfg = load_book_config(Path(args.config))
    book = cfg["book"]
    splinter_slug = cfg.get("splinter", {}).get("slug", PROJECT_ROOT.name)
    pass_mode = args.pass_mode
    output_dir = Path(args.output_dir) if args.output_dir else derive_output_dir(pass_mode)
    personas_doc_path = Path(args.personas_doc)

    if not personas_doc_path.exists():
        print(f"[FATAL] personas doc not found: {personas_doc_path}", file=sys.stderr)
        return 2
    personas_doc = personas_doc_path.read_text(encoding="utf-8")

    selected_personas = [p for p in PERSONAS if p["id"] in selected_persona_ids]
    persona_label = (selected_persona_ids[0] if len(selected_persona_ids) == 1
                     else f"{len(selected_persona_ids)} personas: {', '.join(selected_persona_ids)}")
    print(f"=== {splinter_slug} — Pass {pass_mode.upper()} ===")
    print(f"  config:            {args.config}")
    print(f"  output dir:        {output_dir}")
    print(f"  personas doc:      {personas_doc_path}")
    print(f"  persona(s):        {persona_label}")
    print(f"  pass mode:         {pass_mode.upper()} ({'clean read' if pass_mode == 'a' else 'V3 vs V1 comparison'})")
    print(f"  cost cap:          ${args.force_cap_override or cfg['cost_cap_usd']:.2f}")
    print(f"  per-persona halt:  ${cfg['per_persona_cost_halt_usd']:.2f}")
    print(f"  reflexive pass:    {'SKIPPED' if args.skip_reflexive else 'enabled (Opus 4.7)'}")
    print(f"  mode:              {'DRY-RUN' if args.dry_run else 'PRODUCTION'}")
    if len(selected_personas) > 1:
        n_sonnet = sum(1 for p in selected_personas if p.get('model', DEFAULT_MODEL) == DEFAULT_MODEL)
        n_opus = sum(1 for p in selected_personas if p.get('model') == OPUS_MODEL)
        # Rough estimate: first Sonnet cache-write + N-1 cache reads + N reflexive Opus + Opus persona costs
        est_sonnet = (ESTIMATED_CACHE_WRITE_COST if n_sonnet else 0) + (ESTIMATED_CACHED_READ_COST * max(0, n_sonnet - 1))
        est_opus = ESTIMATED_OPUS_COST * n_opus
        est_reflexive = (0 if args.skip_reflexive else ESTIMATED_REFLEXIVE_COST * len(selected_personas))
        est_pass_b_overhead = (ESTIMATED_PASS_B_OVERHEAD * len(selected_personas) if pass_mode == "b" else 0)
        est_total = est_sonnet + est_opus + est_reflexive + est_pass_b_overhead
        print(f"  multi-persona:     {n_sonnet} Sonnet + {n_opus} Opus + {len(selected_personas)} reflexive = ~${est_total:.2f} estimated")
    print()

    print(f"=== Pre-flight: manuscript + readability panel ===")
    manuscript_path = PROJECT_ROOT / book["manuscript_path"]
    if not manuscript_path.exists():
        print(f"  [FATAL] manuscript not found: {manuscript_path}", file=sys.stderr)
        return 2
    text = manuscript_path.read_text(encoding="utf-8")
    panel_data = readability_panel(strip_md(text))
    chars = len(text)
    chapter_count = count_chapters(text)
    if chapter_count == 0:
        print(f"  [WARN] no '# Chapter N' headings found; Q7 table will be empty", file=sys.stderr)
        chapter_count = 1  # avoid division-by-zero downstream
    book_meta = {
        "config": book, "manuscript_text": text, "manuscript_chars": chars,
        "manuscript_tokens_est": chars // 4, "panel": panel_data,
        "chapter_count": chapter_count,
    }
    if pass_mode == "b":
        pb = cfg.get("pass_b")
        if not pb:
            print(f"  [FATAL] Pass B requires 'pass_b' section in book_config.yaml", file=sys.stderr)
            return 2
        v1_path = PROJECT_ROOT / pb["v1_manuscript_path"]
        v1_resp_path = PROJECT_ROOT / pb["v1_prior_response_path"]
        if not v1_path.exists():
            print(f"  [FATAL] v1 manuscript missing: {v1_path}", file=sys.stderr); return 2
        if not v1_resp_path.exists():
            print(f"  [FATAL] v1 prior response missing: {v1_resp_path}", file=sys.stderr); return 2
        v1_text = v1_path.read_text(encoding="utf-8")
        book_meta["v1_chapter_count"] = count_chapters(v1_text) or 13
    sig = register_signal(panel_data)
    print(f"  {book['slug']:<40} {panel_data['words']:>7,}w  {chars:>7,}ch  {chapter_count} chapters")
    print(f"  FK {panel_data['fk_grade']} | Dale-Chall {panel_data['dale_chall']} | sentence-stdev {panel_data['sent_len_stdev']}")
    print(f"  Craft: {sig['craft']}")
    print()

    cost_cap = args.force_cap_override or cfg["cost_cap_usd"]
    existing_state = load_state(output_dir)
    if args.fresh and existing_state and not args.dry_run:
        print(f"[--fresh] discarding existing state", file=sys.stderr)
        state_path(output_dir).unlink(); existing_state = None

    if existing_state and not args.dry_run:
        print(f"=== Resume mode ===")
        state = existing_state
        if args.force_cap_override: state["cost_cap"] = cost_cap
        state["status"] = "running"; state["halt_reason"] = None
        tc, tf = reconcile_state(state, output_dir)
        if tc or tf: print(f"  reconciliation: {tc} → complete, {tf} → failed")
        save_state_atomic(output_dir, state); print()
    else:
        if args.dry_run:
            state = init_state(book_meta, cost_cap, pass_mode, [p["id"] for p in selected_personas], splinter_slug)
        elif existing_state is None:
            state = init_state(book_meta, cost_cap, pass_mode, [p["id"] for p in selected_personas], splinter_slug)
            print(f"=== Fresh run ===")
            output_dir.mkdir(parents=True, exist_ok=True)
            save_state_atomic(output_dir, state)
            print(f"  state file: {state_path(output_dir)}\n")
        else:
            state = existing_state

    if args.dry_run:
        sample = build_persona_system_content(
            selected_personas[0], personas_doc, book_meta, panel_data, pass_mode, cfg
        )
        print(f"=== Sample persona-system content ({selected_personas[0]['id']}; first 3000 chars) ===")
        print(sample[:3000]); print("...[truncated]\n")
        print(f"=== Sample persona-system content (last 1500 chars) ===")
        print(sample[-1500:]); print()
        print(f"DRY-RUN COMPLETE. No API calls fired.")
        return 0

    client = anthropic.Anthropic(timeout=1800.0)
    failed_count = 0
    sonnet_warmed = False; opus_warmed = False
    book_state = state["book"]

    for persona in selected_personas:
        cur = book_state["reads"].get(persona["id"], "pending")
        if cur == "complete":
            print(f"[skip] {persona['id']}: already complete", file=sys.stderr); continue
        if cur == "failed" and not args.retry_failed:
            print(f"[skip] {persona['id']}: failed (use --retry-failed)", file=sys.stderr); continue
        model = persona.get("model", DEFAULT_MODEL)
        is_opus = "opus" in model
        warmed = opus_warmed if is_opus else sonnet_warmed
        est_cost = ESTIMATED_OPUS_COST if is_opus else (
            ESTIMATED_CACHED_READ_COST if warmed else ESTIMATED_CACHE_WRITE_COST
        )
        if pass_mode == "b": est_cost += ESTIMATED_PASS_B_OVERHEAD
        remaining = state["cost_cap"] - state["cumulative_cost"]
        if remaining < est_cost * SAFETY_MARGIN:
            return halt(state, output_dir, f"cost_cap_approaching: remaining ${remaining:.4f}")
        book_state["reads"][persona["id"]] = "in-progress"
        save_state_atomic(output_dir, state)
        persona_system = build_persona_system_content(
            persona, personas_doc, book_meta, panel_data, pass_mode, cfg
        )
        label = persona["id"]
        print(f"\n=== {label} ({model}; est ${est_cost:.4f}; remaining ${remaining:.4f}) ===", file=sys.stderr)
        try:
            text, tels, cls = attempt_read_with_retry(
                client, persona, book_meta, book_meta["manuscript_text"], persona_system, label
            )
        except anthropic.APIStatusError as e:
            if e.status_code in (401, 403): return halt(state, output_dir, f"api_auth_error: {e.status_code}")
            if e.status_code == 402: return halt(state, output_dir, f"api_credit_exhausted")
            book_state["reads"][persona["id"]] = "failed"; save_state_atomic(output_dir, state)
            failed_count += 1
            print(f"[FAIL] {label}: API error {e.status_code}", file=sys.stderr); continue
        except Exception as e:
            book_state["reads"][persona["id"]] = "failed"; save_state_atomic(output_dir, state)
            failed_count += 1
            print(f"[FAIL] {label}: {e}", file=sys.stderr); continue
        attempt_cost = sum(t["cost"] for t in tels)
        for t in tels:
            state["cumulative_cost"] += t["cost"]
            state["telemetry"].append({**t, "phase": "persona", "classification": (cls if t is tels[-1] else "retry-attempt")})
        save_state_atomic(output_dir, state)
        if cls != "ok":
            book_state["reads"][persona["id"]] = "failed"; save_state_atomic(output_dir, state)
            failed_count += 1
            print(f"[FAIL] {label}: {cls} (spent ${attempt_cost:.4f})", file=sys.stderr)
            if failed_count >= 3: return halt(state, output_dir, f"failed_count_high: {failed_count}")
            continue
        tel = tels[-1]
        reflexive_text = None; reflexive_tel = None
        if not args.skip_reflexive:
            try:
                reflexive_text, reflexive_tel = run_reflexive_critique(client, persona, text, label, pass_mode)
                state["cumulative_cost"] += reflexive_tel["cost"]
                state["telemetry"].append(reflexive_tel)
                book_state["reflexive"][persona["id"]] = "complete"; save_state_atomic(output_dir, state)
                print(f"[reflexive done] {label} | ${reflexive_tel['cost']:.4f}", file=sys.stderr)
            except Exception as e:
                book_state["reflexive"][persona["id"]] = "failed"; save_state_atomic(output_dir, state)
                print(f"[reflexive FAIL] {label}: {e} — continuing without audit", file=sys.stderr)
        else:
            book_state["reflexive"][persona["id"]] = "skipped"
        write_response(output_dir, tel, panel_data, text, pass_mode, reflexive_text, reflexive_tel)
        book_state["reads"][persona["id"]] = "complete"; save_state_atomic(output_dir, state)
        if is_opus: opus_warmed = True
        else: sonnet_warmed = True
        print(f"[done] {label} | ${attempt_cost:.4f} | cache {tel['cache_hit_pct']}% | "
              f"{tel['elapsed_seconds']}s | cumulative ${state['cumulative_cost']:.4f}", file=sys.stderr)
        if attempt_cost > cfg["per_persona_cost_halt_usd"]:
            return halt(state, output_dir, f"cost_spike: {label} ${attempt_cost:.4f} > ${cfg['per_persona_cost_halt_usd']}")

    state["status"] = "complete" if all(s == "complete" for s in state["book"]["reads"].values()) else state["status"]
    save_state_atomic(output_dir, state)
    (output_dir / "_run-report.md").write_text(build_run_report(state), encoding="utf-8")
    write_status_json(state, output_dir)
    print(f"\n=== RUN {'COMPLETE' if state['status'] == 'complete' else 'PARTIAL'} ===", file=sys.stderr)
    print(f"  Cumulative cost: ${state['cumulative_cost']:.4f} / ${state['cost_cap']:.2f}", file=sys.stderr)
    return 0 if state["status"] == "complete" else 5


if __name__ == "__main__":
    sys.exit(main())
