"""Minimal Anthropic auth probe. Confirms ANTHROPIC_API_KEY authenticates.

Loads splinter-local .env (override=True) so the session-injected Claude Code
token doesn't shadow the real API key.

Cost: ~$0.0001 (5 input tokens, ~10 output tokens, claude-sonnet-4-6).
Use before re-firing alpha-reader pipeline after auth halt.
"""
from __future__ import annotations
import os
import sys
from pathlib import Path

import anthropic
from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).parent.parent
load_dotenv(PROJECT_ROOT / ".env", override=True)

MODEL = "claude-sonnet-4-6"


def main() -> int:
    key = os.environ.get("ANTHROPIC_API_KEY", "")
    if not key:
        print("[FAIL] ANTHROPIC_API_KEY not set (and no .env loaded it)", file=sys.stderr)
        return 2
    print(f"Probing with key prefix={key[:14]}... length={len(key)}")

    try:
        client = anthropic.Anthropic(timeout=30.0)
        resp = client.messages.create(
            model=MODEL,
            max_tokens=10,
            messages=[{"role": "user", "content": "Say OK and nothing else."}],
        )
        text = resp.content[0].text if resp.content else "(empty)"
        in_tok = resp.usage.input_tokens
        out_tok = resp.usage.output_tokens
        cost = in_tok / 1_000_000 * 3.00 + out_tok / 1_000_000 * 15.00
        print(f"[OK] auth valid")
        print(f"     model:        {MODEL}")
        print(f"     response:     {text!r}")
        print(f"     input tokens: {in_tok}")
        print(f"     output tokens:{out_tok}")
        print(f"     cost:         ${cost:.6f}")
        return 0
    except anthropic.AuthenticationError as e:
        print(f"[FAIL] authentication error: {e}", file=sys.stderr)
        return 3
    except anthropic.PermissionDeniedError as e:
        print(f"[FAIL] permission denied (key valid but lacks access): {e}", file=sys.stderr)
        return 4
    except anthropic.APIStatusError as e:
        print(f"[FAIL] API error {e.status_code}: {e.message}", file=sys.stderr)
        return 5
    except Exception as e:
        print(f"[FAIL] unexpected error: {type(e).__name__}: {e}", file=sys.stderr)
        return 6


if __name__ == "__main__":
    sys.exit(main())
