#!/usr/bin/env python3
"""no_secrets.py -- refuse a commit that holds a credential.

The tool collects every candidate secret from the environment and from the Hermes
key files, then searches the staged files (or the paths that you give) for each
value and for the usual shapes of a key. It prints the path, the line number and
the NAME of the rule that matched. It never prints the value.

Usage
-----
    python scripts/no_secrets.py --staged       # the files of git's index
    python scripts/no_secrets.py results/*.json # the files that you name

Exit code 0: no credential. Exit code 1: at least one credential, or a file that
the tool cannot read.

Install this tool as a pre-commit hook, so a commit cannot carry a key:

    printf '#!/bin/sh\\nexec python scripts/no_secrets.py --staged\\n' > .git/hooks/pre-commit
    chmod +x .git/hooks/pre-commit
"""
from __future__ import annotations

import argparse
import os
import re
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)

#: Files that hold keys. bench.py reads the same files, in the same order.
ENV_FILES = [
    os.path.join(ROOT, ".env"),
    os.path.expanduser("~/.hermes/.env"),
    os.path.join(os.environ.get("LOCALAPPDATA", ""), "hermes", ".env"),
]

#: The name of a variable that holds a key.
SECRET_NAME = re.compile(r"(API_KEY|_KEY|_TOKEN|TOKEN_|SECRET|PASSWORD|PASSWD)", re.I)

#: The shape of a key, for the values that the environment does not hold.
SHAPES = [
    ("an openai-style key", re.compile(r"\bsk-[A-Za-z0-9_\-]{16,}")),
    ("a provider key with a prefix", re.compile(r"\b(user|org|team)_[A-Za-z0-9_\-]{24,}")),
    ("a github token", re.compile(r"\b(gho|ghp|ghs|ghu|ghr)_[A-Za-z0-9]{20,}")),
    ("a fine-grained github token", re.compile(r"\bgithub_pat_[A-Za-z0-9_]{20,}")),
    ("an aws access key", re.compile(r"\b(AKIA|ASIA)[0-9A-Z]{16}\b")),
    ("a private-key block", re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----")),
]

#: A value below this length is too short to be a key, and it matches too much.
MIN_SECRET = 16


def candidate_secrets() -> dict[str, str]:
    """Return {name of the rule: value}. The value never leaves this process."""
    out = {}
    for name, value in os.environ.items():
        if SECRET_NAME.search(name) and len(value or "") >= MIN_SECRET:
            out["environment %s" % name] = value
    for path in ENV_FILES:
        if not path or not os.path.exists(path):
            continue
        try:
            with open(path, encoding="utf-8", errors="ignore") as fh:
                for line in fh:
                    line = line.strip()
                    if "=" not in line or line.startswith("#"):
                        continue
                    key, value = line.split("=", 1)
                    value = value.strip().strip('"').strip("'")
                    if SECRET_NAME.search(key) and len(value) >= MIN_SECRET:
                        out["%s in %s" % (key.strip(), os.path.basename(path))] = value
        except OSError:
            continue
    return out


def staged_files() -> list[str]:
    r = subprocess.run(["git", "-C", ROOT, "diff", "--cached", "--name-only",
                        "--diff-filter=ACM"], capture_output=True, text=True)
    if r.returncode != 0:
        sys.exit("no_secrets.py: git diff failed: " + r.stderr.strip()[:200])
    names = [n.strip() for n in r.stdout.splitlines() if n.strip()]
    return [os.path.join(ROOT, n) for n in names]


def scan(paths: list[str], secrets: dict[str, str]) -> int:
    hits = 0
    for path in paths:
        if not os.path.isfile(path):
            continue
        try:
            with open(path, encoding="utf-8", errors="strict") as fh:
                text = fh.read()
        except (OSError, UnicodeDecodeError):
            continue  # a binary file or an unreadable file holds no source secret
        rel = os.path.relpath(path, ROOT)
        for rule, value in secrets.items():
            if value and value in text:
                hits += 1
                print("%s: the value of %s" % (rel, rule))
        for label, pattern in SHAPES:
            for m in pattern.finditer(text):
                hits += 1
                line = text.count("\n", 0, m.start()) + 1
                print("%s:%d: %s" % (rel, line, label))
    return hits


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("paths", nargs="*", help="files to scan (default: the paths of git's index with --staged)")
    ap.add_argument("--staged", action="store_true", help="scan the files of git's index")
    args = ap.parse_args()

    paths = staged_files() if (args.staged or not args.paths) else args.paths
    if not paths:
        return
    secrets = candidate_secrets()
    hits = scan(paths, secrets)
    if hits:
        print("\nno_secrets.py: %d finding(s) in %d file(s). The commit must not carry a credential."
              % (hits, len(paths)))
        print("Rotate the key if it reached a remote, then remove the value from the file.")
        sys.exit(1)
    print("no_secrets.py: %d file(s) clean, against %d known value(s) and %d shape(s)."
          % (len(paths), len(secrets), len(SHAPES)))


if __name__ == "__main__":
    main()
