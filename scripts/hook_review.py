"""Auto-commit hook review script.

Calls the Anthropic API to review code changes before/after commits.
Replicates the intent of:
  - everything-claude-code:code-review (pre-commit gate)
  - superpowers:code-reviewer (post-commit validation)

Usage:
  python scripts/hook_review.py pre   # Review staged changes, exit 0=pass 1=fail
  python scripts/hook_review.py post  # Review latest commit, exit 0=pass 1=fail

Uses claude-haiku-4-5 for speed. Change REVIEW_MODEL for deeper reviews.
"""

import subprocess
import sys
from pathlib import Path

REVIEW_MODEL = "claude-haiku-4-5-20251001"
MAX_DIFF_CHARS = 15000
VALID_MODES = {"pre", "post"}


def _load_env():
    env_path = Path(__file__).resolve().parent.parent / ".env"
    if env_path.exists():
        from dotenv import load_dotenv

        load_dotenv(env_path)


def _get_diff(mode: str) -> str:
    if mode == "pre":
        result = subprocess.run(["git", "diff", "--cached"], capture_output=True, text=True)
    else:
        result = subprocess.run(
            ["git", "diff", "HEAD~1", "HEAD"], capture_output=True, text=True
        )
    if result.returncode != 0:
        print(f"git diff failed (exit {result.returncode}): {result.stderr.strip()}", file=sys.stderr)
        return ""
    diff = result.stdout
    if len(diff) > MAX_DIFF_CHARS:
        print(f"Warning: diff truncated to {MAX_DIFF_CHARS} chars (full diff: {len(diff)} chars)", file=sys.stderr)
        diff = diff[:MAX_DIFF_CHARS]
    return diff


def _review(diff: str, mode: str) -> str:
    import anthropic

    client = anthropic.Anthropic()

    if mode == "pre":
        prompt = f"""Review these staged code changes for critical issues.

Focus on: bugs, security vulnerabilities, breaking changes, incorrect error handling.
Ignore: style, docs, minor improvements, naming preferences.

```diff
{diff}
```

Respond EXACTLY: "PASS" or "FAIL: <one-line reason>"."""
    else:
        prompt = f"""Review this commit against coding standards and project conventions.

Focus on: correctness, test coverage gaps, security, architectural consistency.
Ignore: style nitpicks, doc gaps, minor naming preferences.

```diff
{diff}
```

Respond EXACTLY: "PASS" or "FAIL: <one-line reason>"."""

    response = client.messages.create(
        model=REVIEW_MODEL,
        max_tokens=100,
        messages=[{"role": "user", "content": prompt}],
    )
    return response.content[0].text.strip()


def main():
    mode = sys.argv[1] if len(sys.argv) > 1 else "pre"
    if mode not in VALID_MODES:
        print(f"Unknown mode '{mode}'. Use: pre | post", file=sys.stderr)
        sys.exit(0)  # fail-open to avoid blocking commits

    _load_env()

    diff = _get_diff(mode)
    if not diff.strip():
        sys.exit(0)

    try:
        result = _review(diff, mode)
        print(f"Review ({mode}): {result}")
        sys.exit(0 if result.upper().startswith("PASS") else 1)
    except Exception as e:
        print(f"Review skipped: {e}")
        sys.exit(0)


if __name__ == "__main__":
    main()
