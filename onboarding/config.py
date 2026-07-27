"""
config.py — runtime configuration and secrets handling.

Two jobs:
  1. Load the OpenAI API key from a .env file (so the key lives on disk, never in
     code or git). python-dotenv reads .env into the process environment; the OpenAI
     SDK then picks up OPENAI_API_KEY automatically.
  2. Pin the runtime model in ONE place, so we never sprinkle "gpt-4o" across files.

Why a .env file and not just an environment variable: it's the standard way to keep
secrets out of source control while staying easy to set up. We ship a .env.example
(committed) showing the shape, and a real .env (gitignored) holding the actual key.
"""

from __future__ import annotations

import os

from dotenv import load_dotenv

# Reads .env from the project root into os.environ if present. Safe to call at import
# time; does nothing if there's no .env file.
load_dotenv()

# The runtime LLM. Locked in per CLAUDE.md (Microsoft/OpenAI strategic alignment).
# Defined here so swapping models is a one-line change.
MODEL = "gpt-4o"


def has_api_key() -> bool:
    """True if an OpenAI key is available. Used to skip live-LLM tests gracefully."""
    return bool(os.getenv("OPENAI_API_KEY"))


def ensure_api_key() -> None:
    """Fail with a clear, actionable message instead of a cryptic SDK error deep in a
    network call. The end user is non-technical — even developer-facing errors should
    say exactly what to do."""
    if not has_api_key():
        raise RuntimeError(
            "OPENAI_API_KEY is not set. Copy .env.example to .env and paste your key, "
            "or run: export OPENAI_API_KEY=sk-...  "
            "(The routing/unit tests do not need a key — only live agent runs do.)"
        )
