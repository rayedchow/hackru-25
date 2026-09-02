"""Fail when added lines contain common credential formats without printing values."""

from __future__ import annotations

import argparse
import re
import subprocess
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Pattern:
    name: str
    expression: re.Pattern[str]


PATTERNS = (
    Pattern("private-key", re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----")),
    Pattern("github-token", re.compile(r"\b(?:ghp|github_pat)_[A-Za-z0-9_]{20,}\b")),
    Pattern("aws-access-key", re.compile(r"\bAKIA[0-9A-Z]{16}\b")),
    Pattern("google-api-key", re.compile(r"\bAIza[0-9A-Za-z_-]{30,}\b")),
    Pattern("slack-token", re.compile(r"\bxox[baprs]-[0-9A-Za-z-]{20,}\b")),
    Pattern("api-secret", re.compile(r"\b(?:sk|rk)_(?:live|prod)_[0-9A-Za-z]{16,}\b")),
    Pattern(
        "assigned-secret",
        re.compile(
            r"(?i)\b(?:api[_-]?key|client[_-]?secret|password|access[_-]?token)\b"
            r"\s*[:=]\s*['\"][^'\"]{12,}['\"]"
        ),
    ),
)

PLACEHOLDER_MARKERS = (
    "example",
    "invalid",
    "placeholder",
    "replace_",
    "synthetic",
    "invented",
    "redacted",
    "$(",
)


def _git(*arguments: str) -> str:
    completed = subprocess.run(
        ["git", *arguments],
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    return completed.stdout


def _added_lines(base: str) -> list[tuple[str, int, str]]:
    diff = _git("diff", "--no-ext-diff", "--unified=0", "--diff-filter=ACMR", base, "--")
    findings: list[tuple[str, int, str]] = []
    current_path = "unknown"
    new_line = 0
    for line in diff.splitlines():
        if line.startswith("+++ b/"):
            current_path = line[6:]
        elif line.startswith("@@"):
            match = re.search(r"\+(\d+)", line)
            new_line = int(match.group(1)) if match else 0
        elif line.startswith("+") and not line.startswith("+++"):
            findings.append((current_path, new_line, line[1:]))
            new_line += 1
        elif not line.startswith("-"):
            new_line += 1
    return findings


def _untracked_lines() -> list[tuple[str, int, str]]:
    values: list[tuple[str, int, str]] = []
    for relative in _git("ls-files", "--others", "--exclude-standard").splitlines():
        path = Path(relative)
        try:
            if path.stat().st_size > 1_000_000:
                continue
            text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeError):
            continue
        values.extend((relative, index, line) for index, line in enumerate(text.splitlines(), 1))
    return values


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base", default="HEAD^")
    arguments = parser.parse_args()
    failures: list[tuple[str, int, str]] = []
    for path, line_number, line in [*_added_lines(arguments.base), *_untracked_lines()]:
        folded = line.casefold()
        if any(marker.casefold() in folded for marker in PLACEHOLDER_MARKERS):
            continue
        for pattern in PATTERNS:
            if pattern.expression.search(line):
                failures.append((path, line_number, pattern.name))

    if failures:
        for path, line_number, name in failures:
            print(f"{path}:{line_number}: possible {name}")
        return 1
    print("Secret scan passed: no credential patterns found in added lines.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
