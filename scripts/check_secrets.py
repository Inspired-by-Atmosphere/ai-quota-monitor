#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Dependency-free secret / privacy scanner.

Run before every push:

    python scripts/check_secrets.py .

Exit code 0 = clean, 1 = findings. Findings are printed as
``path:line: <rule> -> <masked hit>``; matched values are masked so the scanner
itself never leaks the secret it found.
"""
import argparse
import os
import re
import sys

SKIP_DIRS = {".git", "__pycache__", ".venv", "venv", "node_modules", ".mypy_cache"}
SKIP_EXTS = {".pdf", ".png", ".jpg", ".jpeg", ".gif", ".zip", ".tar", ".gz", ".ico", ".pyc"}

RULES = [
    ("github-token", re.compile(r"\bgh[pousr]_[A-Za-z0-9]{20,}")),
    ("github-pat", re.compile(r"\bgithub_pat_[A-Za-z0-9_]{20,}")),
    ("aws-key-id", re.compile(r"\bAKIA[0-9A-Z]{16}\b")),
    ("volc-ak", re.compile(r"\bAKLT[A-Za-z0-9]{16,}\b")),
    ("private-key-block", re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----")),
    ("bearer-literal", re.compile(r"[Bb]earer\s+[A-Za-z0-9\-._~+/]{20,}={0,2}")),
    ("assigned-secret", re.compile(
        r"(?i)\b(api[_-]?key|apikey|secret|token|passwd|password|access[_-]?key)\b\s*[:=]\s*"
        r"[\"']?([A-Za-z0-9\-._~+/]{16,})[\"']?")),
    ("private-ip", re.compile(r"\b(?:10\.\d{1,3}|192\.168|172\.(?:1[6-9]|2\d|3[01]))\.\d{1,3}\.\d{1,3}\b")),
    ("mac-address", re.compile(r"\b(?:[0-9A-Fa-f]{2}:){5}[0-9A-Fa-f]{2}\b")),
    ("email", re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b")),
    ("cn-mobile", re.compile(r"\b1[3-9]\d{9}\b")),
    ("absolute-user-path", re.compile(r"(?i)(?:[A-Z]:\\+Users\\+[A-Za-z0-9._-]+|/c/Users/[A-Za-z0-9._-]+|/home/[A-Za-z0-9._-]+)")),
    ("todo-secret", re.compile(r"(?i)(password|passwd|pwd)\s*=\s*\S{3,}")),
]

# Values that are obviously placeholders, not secrets.
ALLOW = re.compile(r"(?i)(your[-_]?|example|placeholder|xxx+|aaaa+|dummy|test|redacted|\.\.\.|\$\{|\$[A-Z_]+|%s|none|null)")

ALLOWED_FILES = {"check_secrets.py"}


def mask(value):
    if len(value) <= 8:
        return "*" * len(value)
    return value[:4] + "*" * (len(value) - 8) + value[-4:]


def scan_file(path):
    findings = []
    try:
        with open(path, encoding="utf-8", errors="replace") as fh:
            for lineno, line in enumerate(fh, 1):
                if len(line) > 4000:
                    continue
                for name, pattern in RULES:
                    for match in pattern.finditer(line):
                        hit = match.group(0)
                        if ALLOW.search(hit):
                            continue
                        findings.append((lineno, name, mask(hit)))
    except OSError:
        pass
    return findings


def main():
    parser = argparse.ArgumentParser(description="Scan a tree for secrets and private data")
    parser.add_argument("root", nargs="?", default=".", help="directory to scan")
    args = parser.parse_args()

    total = 0
    for dirpath, dirnames, filenames in os.walk(args.root):
        dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS]
        for filename in filenames:
            if filename in ALLOWED_FILES or os.path.splitext(filename)[1].lower() in SKIP_EXTS:
                continue
            full = os.path.join(dirpath, filename)
            for lineno, name, hit in scan_file(full):
                print(f"{os.path.relpath(full, args.root)}:{lineno}: {name} -> {hit}")
                total += 1

    if total:
        print(f"\n❌ {total} finding(s). Fix or allow-list them before pushing.")
        return 1
    print("✅ clean: no secrets, credentials, private IPs or personal data found.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
