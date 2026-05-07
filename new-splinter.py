#!/usr/bin/env python3
"""new-splinter.py — Scaffold a new alpha-reader project.

One command from "I have a manuscript" → "ready for the orchestrator to fire."

Usage:
  python new-splinter.py \\
      --slug my-author-book-001 \\
      --manuscript ./path/to/book.docx \\
      --pen-name "Author Name" \\
      --genre "thriller" \\
      --output-dir ./projects/

Optional flags:
  --persona <id>            Default persona for kickoff (default: first persona in cohort)
  --partial                 Partial manuscript (changes Q4 framing)
  --next-book-teaser STR    Series teaser (used for Q4 reframe if --complete)
  --cost-cap FLOAT          Per-pass cost cap in USD (default: 10.00)
  --title STR               Book title (default: derived from manuscript filename)
  --output-dir DIR          Where to create the project dir (default: current dir)
  --copy-key-from PATH      Copy ANTHROPIC_API_KEY from another .env file
  --chapter-pattern REGEX   Override auto-detect (e.g., '^\\*\\*Chapter [A-Z]+\\*\\*')

What this script does:
  1. Validates target dir doesn't already exist
  2. Creates project dir structure
  3. Copies/converts manuscript:
     - .docx → pandoc → .md → chapter normalization
     - .md → copy + chapter normalization
  4. Copies toolkit orchestrator + analyzer + auth_probe + personas snapshot
  5. Generates book_config.yaml from CLI args
  6. Generates CLAUDE.md from template
  7. Generates kickoffs/<date>-alpha-reader.md from template
  8. Sources ANTHROPIC_API_KEY (from --copy-key-from, or prompts you to add it)
  9. Writes .env.example + .gitignore
 10. Runs readability analyzer on the new manuscript
 11. Prints next-steps (auth probe + dry-run + fire commands)
"""
from __future__ import annotations

import argparse
import re
import shutil
import subprocess
import sys
from datetime import date
from pathlib import Path

TOOLKIT_ROOT = Path(__file__).parent
TEMPLATES = TOOLKIT_ROOT / "templates"
ORCHESTRATOR_SRC = TOOLKIT_ROOT / "orchestrator"
PERSONAS_SRC = TOOLKIT_ROOT / "references" / "personas-snapshot-v0.4.md"

DEFAULT_TARGET = Path.cwd()
PANDOC = shutil.which("pandoc") or "pandoc"

CHAPTER_WORD_TO_NUM = {
    "One": 1, "Two": 2, "Three": 3, "Four": 4, "Five": 5, "Six": 6, "Seven": 7,
    "Eight": 8, "Nine": 9, "Ten": 10, "Eleven": 11, "Twelve": 12, "Thirteen": 13,
    "Fourteen": 14, "Fifteen": 15, "Sixteen": 16, "Seventeen": 17, "Eighteen": 18,
    "Nineteen": 19, "Twenty": 20, "Twenty-One": 21, "Twenty-Two": 22,
    "Twenty-Three": 23, "Twenty-Four": 24, "Twenty-Five": 25, "Twenty-Six": 26,
    "Twenty-Seven": 27, "Twenty-Eight": 28, "Twenty-Nine": 29, "Thirty": 30,
    "Thirty-One": 31, "Thirty-Two": 32, "Thirty-Three": 33, "Thirty-Four": 34,
    "Thirty-Five": 35, "Thirty-Six": 36, "Thirty-Seven": 37, "Thirty-Eight": 38,
    "Thirty-Nine": 39, "Forty": 40, "Forty-One": 41, "Forty-Two": 42,
    "Forty-Three": 43, "Forty-Four": 44, "Forty-Five": 45, "Forty-Six": 46,
    "Forty-Seven": 47, "Forty-Eight": 48, "Forty-Nine": 49, "Fifty": 50,
}


def fail(msg: str, code: int = 2) -> int:
    print(f"[FAIL] {msg}", file=sys.stderr)
    return code


def info(msg: str) -> None:
    print(f"[info] {msg}")


def convert_docx_to_md(docx_path: Path, md_path: Path) -> None:
    """pandoc .docx → .md (gfm)"""
    info(f"converting {docx_path.name} → {md_path.name} via pandoc")
    result = subprocess.run(
        [PANDOC, str(docx_path), "-f", "docx", "-t", "gfm", "--wrap=none", "-o", str(md_path)],
        capture_output=True, text=True,
    )
    if result.returncode != 0:
        raise RuntimeError(f"pandoc failed: {result.stderr}")


def detect_and_normalize_chapters(md_path: Path, override_pattern: str | None = None) -> int:
    """Detect chapter format in manuscript; normalize to '# Chapter N'.

    Common patterns handled:
      - **Chapter One** / **Chapter Twenty-Seven**  (bold paragraphs from .docx)
      - **Chapter 1** / **Chapter 27**              (bold + numeric)
      - Chapter One / Chapter 1                     (plain text headings)
      - # Chapter 1 / # Chapter One                 (already-markdown headings)

    Returns: chapter count detected.
    Raises: RuntimeError if no chapters detected.
    """
    text = md_path.read_text(encoding="utf-8")

    if override_pattern:
        patterns = [(override_pattern, "override")]
    else:
        patterns = [
            (r'^\*\*Chapter ([A-Za-z]+(?:-[A-Za-z]+)?)\*\*\s*$', "bold-word"),
            (r'^\*\*Chapter (\d+)\*\*\s*$', "bold-num"),
            (r'^# Chapter (\d+)\s*$', "already-md-num"),
            (r'^# Chapter ([A-Za-z]+(?:-[A-Za-z]+)?)\s*$', "already-md-word"),
            (r'^Chapter ([A-Za-z]+(?:-[A-Za-z]+)?)\s*$', "plain-word"),
            (r'^Chapter (\d+)\s*$', "plain-num"),
        ]

    for pattern, kind in patterns:
        matches = re.findall(pattern, text, re.MULTILINE)
        if len(matches) >= 3:  # need at least 3 matches to be confident
            info(f"detected chapter format: {kind} ({len(matches)} chapters)")

            def replace(m):
                token = m.group(1)
                if token.isdigit():
                    num = int(token)
                else:
                    num = CHAPTER_WORD_TO_NUM.get(token)
                    if num is None:
                        return m.group(0)  # unknown word; leave alone
                return f"# Chapter {num}"

            new_text, n = re.subn(pattern, replace, text, flags=re.MULTILINE)
            md_path.write_text(new_text, encoding="utf-8")

            # Verify final state
            final = re.findall(r'^# Chapter \d+', new_text, re.MULTILINE)
            info(f"normalized {n} chapter markers; final count: {len(final)}")
            return len(final)

    raise RuntimeError(
        f"no chapter format detected in {md_path.name}. "
        f"Tried: {[p[1] for p in patterns]}. "
        f"Provide --chapter-pattern to override, or normalize the manuscript manually."
    )


def extract_api_key(env_path: Path) -> str:
    """Extract ANTHROPIC_API_KEY value from a .env file."""
    if not env_path.exists():
        raise FileNotFoundError(f"--copy-key-from path does not exist: {env_path}")
    for line in env_path.read_text(encoding="utf-8").splitlines():
        m = re.match(r'^\s*ANTHROPIC_API_KEY\s*=\s*(.+?)\s*$', line)
        if m:
            return m.group(1).strip().strip('"').strip("'")
    raise ValueError(f"ANTHROPIC_API_KEY not found in {env_path}")


def render_template(template_path: Path, **params) -> str:
    """Simple {placeholder} substitution. Doubles up { and } that aren't placeholders."""
    text = template_path.read_text(encoding="utf-8")
    return text.format(**params)


def to_yaml_value(value) -> str:
    """Render a Python value as a YAML scalar."""
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, str):
        return f'"{value}"'
    return str(value)


def main() -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except (AttributeError, OSError):
        pass

    ap = argparse.ArgumentParser(
        description="Scaffold a new alpha-reader splinter project from the toolkit.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    ap.add_argument("--slug", required=True, help="Splinter directory name (e.g., splinter-author-book-001)")
    ap.add_argument("--manuscript", required=True, help="Path to manuscript (.docx or .md)")
    ap.add_argument("--pen-name", required=True, help="Pen name for the manuscript")
    ap.add_argument("--genre", required=True, help="Genre hint (e.g., 'thriller', 'hockey dark romance')")
    ap.add_argument("--copy-key-from", default=None, help="Optional: copy ANTHROPIC_API_KEY from another .env file. If omitted, you must add the key to .env in the new project manually.")
    ap.add_argument("--persona", default="kayla-hockey",
                    choices=["marisol-the-whale", "tessa-booktok", "nadia-dark-fantasy",
                             "aaliyah-romantasy", "brittany-erotica", "kayla-hockey",
                             "sienna-fae-court", "veronica-the-hatchet", "emma-the-surgeon"],
                    help="Default persona for kickoff (default: kayla-hockey)")
    ap.add_argument("--partial", action="store_true",
                    help="Partial manuscript (changes Q4 framing)")
    ap.add_argument("--next-book-teaser", default=None,
                    help="Series teaser (used for Q4 reframe if --complete)")
    ap.add_argument("--pass-b-v1-manuscript", default=None,
                    help="Path to v1 manuscript for Pass B comparison reads. "
                         "Must be paired with --pass-b-v1-response.")
    ap.add_argument("--pass-b-v1-response", default=None,
                    help="Path to v1 prior alpha-reader response for Pass B. "
                         "Must be paired with --pass-b-v1-manuscript.")
    ap.add_argument("--cost-cap", type=float, default=10.00, help="Per-pass cost cap USD (default: 10.00)")
    ap.add_argument("--title", default=None, help="Book title (default: derived from manuscript filename)")
    ap.add_argument("--target-dir", "--output-dir", default=str(DEFAULT_TARGET),
                    help="Where to create the project dir (default: current working dir)")
    ap.add_argument("--chapter-pattern", default=None,
                    help="Regex override for chapter detection (rare)")
    ap.add_argument("--context-role", default=None,
                    help="One-line book context (default: auto-generated)")
    args = ap.parse_args()

    # Resolve paths
    manuscript_src = Path(args.manuscript).resolve()
    target_dir = Path(args.target_dir).resolve() / args.slug
    key_src = Path(args.copy_key_from).resolve() if args.copy_key_from else None

    # Validate
    if not manuscript_src.exists():
        return fail(f"manuscript not found: {manuscript_src}")
    if manuscript_src.suffix.lower() not in (".docx", ".md"):
        return fail(f"manuscript must be .docx or .md (got {manuscript_src.suffix})")
    if target_dir.exists():
        return fail(f"target dir already exists: {target_dir}\n        delete it first or pick a different --slug")
    if not PERSONAS_SRC.exists():
        return fail(f"toolkit personas snapshot missing: {PERSONAS_SRC}")
    if not (ORCHESTRATOR_SRC / "run-alpha-reader.py").exists():
        return fail(f"toolkit orchestrator missing: {ORCHESTRATOR_SRC / 'run-alpha-reader.py'}")

    # Pass B flags must be paired (both or neither)
    if bool(args.pass_b_v1_manuscript) != bool(args.pass_b_v1_response):
        return fail("--pass-b-v1-manuscript and --pass-b-v1-response must be provided together (or neither)")
    pass_b_enabled = bool(args.pass_b_v1_manuscript)
    pass_b_v1_mss_src = Path(args.pass_b_v1_manuscript).resolve() if pass_b_enabled else None
    pass_b_v1_resp_src = Path(args.pass_b_v1_response).resolve() if pass_b_enabled else None
    if pass_b_enabled:
        if not pass_b_v1_mss_src.exists():
            return fail(f"--pass-b-v1-manuscript path does not exist: {pass_b_v1_mss_src}")
        if not pass_b_v1_resp_src.exists():
            return fail(f"--pass-b-v1-response path does not exist: {pass_b_v1_resp_src}")
        if pass_b_v1_mss_src.suffix.lower() != ".md":
            return fail(f"--pass-b-v1-manuscript must be .md (got {pass_b_v1_mss_src.suffix})")
        if pass_b_v1_resp_src.suffix.lower() != ".md":
            return fail(f"--pass-b-v1-response must be .md (got {pass_b_v1_resp_src.suffix})")

    api_key = None
    if key_src:
        try:
            api_key = extract_api_key(key_src)
            info(f"sourced ANTHROPIC_API_KEY from {key_src} (prefix={api_key[:14]}..., len={len(api_key)})")
        except Exception as e:
            return fail(str(e))
    else:
        info("no --copy-key-from passed; .env will be written with placeholder. Add your key manually before running the orchestrator.")

    # Title default
    title = args.title or manuscript_src.stem.replace("_", " ")
    is_complete = not args.partial
    next_book_teaser = args.next_book_teaser
    context_role = args.context_role or (
        f"Complete novel; pen name {args.pen_name}; genre {args.genre}."
        if is_complete else
        f"Partial manuscript; pen name {args.pen_name}; genre {args.genre}."
    )

    # Create dir structure
    info(f"creating splinter dir: {target_dir}")
    for sub in ("manuscript", "references", "orchestrator", "kickoffs", "runs"):
        (target_dir / sub).mkdir(parents=True, exist_ok=True)

    # Manuscript: copy + convert if .docx
    docx_dst = None
    md_dst = target_dir / "manuscript" / f"{manuscript_src.stem}.md"
    if manuscript_src.suffix.lower() == ".docx":
        docx_dst = target_dir / "manuscript" / manuscript_src.name
        shutil.copy2(manuscript_src, docx_dst)
        convert_docx_to_md(docx_dst, md_dst)
        info(f"both .docx and .md preserved in manuscript/")
    else:
        shutil.copy2(manuscript_src, md_dst)

    # Normalize chapter markers
    try:
        chapter_count = detect_and_normalize_chapters(md_dst, args.chapter_pattern)
    except RuntimeError as e:
        return fail(str(e))

    # Copy toolkit files
    info("copying orchestrator + analyzer + auth_probe + personas snapshot")
    for fname in ("run-alpha-reader.py", "readability_analyzer.py", "auth_probe.py"):
        shutil.copy2(ORCHESTRATOR_SRC / fname, target_dir / "orchestrator" / fname)
    shutil.copy2(PERSONAS_SRC, target_dir / "references" / "personas-snapshot-v0.4.md")

    # Pass B v1 reference files (if --pass-b-v1-* flags provided)
    pass_b_section_yaml = (
        "# Optional: Pass B references (V3-vs-V1 comparison reads)\n"
        "# Provide --pass-b-v1-manuscript and --pass-b-v1-response to scaffolder, "
        "or hand-edit and uncomment below.\n"
        "# pass_b:\n"
        '#   v1_manuscript_path: "manuscript/v1-draft.md"\n'
        '#   v1_prior_response_path: "references/persona-v1-prior-response.md"'
    )
    if pass_b_enabled:
        v1_mss_dst = target_dir / "manuscript" / pass_b_v1_mss_src.name
        v1_resp_dst = target_dir / "references" / pass_b_v1_resp_src.name
        info(f"copying Pass B v1 manuscript: {pass_b_v1_mss_src.name}")
        shutil.copy2(pass_b_v1_mss_src, v1_mss_dst)
        info(f"copying Pass B v1 prior response: {pass_b_v1_resp_src.name}")
        shutil.copy2(pass_b_v1_resp_src, v1_resp_dst)
        pass_b_section_yaml = (
            f"# Pass B references (V3-vs-V1 comparison reads) — auto-generated from --pass-b-v1-* flags\n"
            f"pass_b:\n"
            f'  v1_manuscript_path: "manuscript/{pass_b_v1_mss_src.name}"\n'
            f'  v1_prior_response_path: "references/{pass_b_v1_resp_src.name}"'
        )

    # Generate book_config.yaml
    info("generating book_config.yaml")
    book_slug = re.sub(r'[^a-z0-9-]', '-', f"{args.pen_name.lower().replace(' ', '-')}-{manuscript_src.stem.lower()}")[:60]
    config_text = render_template(
        TEMPLATES / "book_config.yaml.template",
        slug=args.slug,
        created_date=date.today().isoformat(),
        book_slug=book_slug,
        title=title,
        pen_name=args.pen_name,
        manuscript_filename=md_dst.name,
        genre=args.genre,
        context_role=context_role,
        is_complete=str(is_complete).lower(),
        next_book_teaser_yaml=to_yaml_value(next_book_teaser),
        q4_phrasing_yaml=to_yaml_value(None),  # auto-derived in orchestrator
        cost_cap=f"{args.cost_cap:.2f}",
        pass_b_section=pass_b_section_yaml,
    )
    (target_dir / "book_config.yaml").write_text(config_text, encoding="utf-8")

    # Generate CLAUDE.md
    info("generating splinter CLAUDE.md")
    complete_status = (
        f"Complete novel; {chapter_count} chapters" if is_complete
        else f"Partial manuscript; {chapter_count} chapters supplied"
    )
    claude_md = render_template(
        TEMPLATES / "splinter-CLAUDE.md.template",
        slug=args.slug,
        created_date=date.today().isoformat(),
        pen_name=args.pen_name,
        title=title,
        genre=args.genre,
        complete_status=complete_status,
        manuscript_filename=md_dst.name,
        cost_cap=f"{args.cost_cap:.2f}",
        default_persona=args.persona,
    )
    (target_dir / "CLAUDE.md").write_text(claude_md, encoding="utf-8")

    # Generate kickoff
    info("generating kickoff doc")
    kickoff = render_template(
        TEMPLATES / "splinter-kickoff.md.template",
        slug=args.slug,
        created_date=date.today().isoformat(),
        pen_name=args.pen_name,
        title=title,
        genre=args.genre,
        manuscript_filename=md_dst.name,
        cost_cap=f"{args.cost_cap:.2f}",
        default_persona=args.persona,
    )
    (target_dir / "kickoffs" / f"{date.today().isoformat()}-alpha-reader.md").write_text(
        kickoff, encoding="utf-8"
    )

    # Generate .env
    info("writing .env (gitignored)")
    if api_key:
        env_body = (
            f"# Project-local environment overrides\n"
            f"# Sourced {date.today().isoformat()} from {key_src}\n"
            f"# python-dotenv loads this automatically when orchestrator runs\n"
            f"ANTHROPIC_API_KEY={api_key}\n"
        )
    else:
        env_body = (
            f"# Project-local environment overrides\n"
            f"# Add your real ANTHROPIC_API_KEY below before running the orchestrator.\n"
            f"# Get one at https://console.anthropic.com/\n"
            f"ANTHROPIC_API_KEY=sk-ant-api03-your-key-here\n"
        )
    (target_dir / ".env").write_text(env_body, encoding="utf-8")

    # Copy templates: .env.example + .gitignore
    shutil.copy2(TEMPLATES / ".env.example", target_dir / ".env.example")
    shutil.copy2(TEMPLATES / ".gitignore.template", target_dir / ".gitignore")

    # Run readability analyzer
    info("running readability analyzer on new manuscript")
    result = subprocess.run(
        ["py", "-3.14", str(target_dir / "orchestrator" / "readability_analyzer.py")],
        cwd=str(target_dir),
        capture_output=True, text=True,
    )
    if result.returncode != 0:
        print(f"[WARN] readability analyzer failed: {result.stderr}", file=sys.stderr)
        print("       splinter scaffolded but readability snapshot missing — run manually:")
        print(f"       cd {target_dir} && py -3.14 orchestrator/readability_analyzer.py")
    else:
        # Print last few lines of analyzer output (the headline metrics)
        for line in result.stderr.strip().splitlines()[-3:]:
            info(f"  analyzer: {line}")

    # Print next steps
    print()
    print("=" * 70)
    print(f"SCAFFOLD COMPLETE: {target_dir}")
    print("=" * 70)
    print()
    print(f"  Slug:          {args.slug}")
    print(f"  Pen name:      {args.pen_name}")
    print(f"  Title:         {title}")
    print(f"  Genre:         {args.genre}")
    print(f"  Manuscript:    {md_dst.relative_to(target_dir)}")
    print(f"  Chapters:      {chapter_count}")
    print(f"  Status:        {complete_status}")
    print(f"  Default persona: {args.persona}")
    print(f"  Cost cap:      ${args.cost_cap:.2f}/pass")
    if pass_b_enabled:
        print(f"  Pass B ready:  yes (v1 manuscript + v1 response loaded)")
    print()
    print("Next steps:")
    print()
    print(f"  cd {target_dir}")
    print(f"  py -3.14 orchestrator/auth_probe.py")
    print(f"  py -3.14 orchestrator/run-alpha-reader.py --pass a --persona {args.persona} --dry-run")
    print()
    print(f"  # if dry-run looks good:")
    print(f"  py -3.14 orchestrator/run-alpha-reader.py --pass a --persona {args.persona}")
    if pass_b_enabled:
        print()
        print(f"  # then Pass B (V1 comparison):")
        print(f"  py -3.14 orchestrator/run-alpha-reader.py --pass b --persona {args.persona}")
    print()
    print(f"Kickoff doc: {target_dir / 'kickoffs' / (date.today().isoformat() + '-alpha-reader.md')}")
    print()
    return 0


if __name__ == "__main__":
    sys.exit(main())
