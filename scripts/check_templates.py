#!/usr/bin/env python3
"""
Pre-commit hook: verifies that no Django/Jinja template tags
({% ... %} or {{ ... }}) are split across multiple lines.

Install:
  Save this file as .git/hooks/pre-commit and make it executable:
    copy scripts\check_templates.py .git\hooks\pre-commit
  Or on Linux/Mac:
    cp scripts/check_templates.py .git/hooks/pre-commit
    chmod +x .git/hooks/pre-commit
"""
import subprocess
import re
import sys
from pathlib import Path

# Pattern that catches an opening tag token that has no closing on the same line
OPEN_BLOCK = re.compile(r'\{%(?!.*?%\})')   # {% without matching %}
OPEN_VAR   = re.compile(r'\{\{(?!.*?\}\})')  # {{ without matching }}

def get_staged_html_files():
    result = subprocess.run(
        ['git', 'diff', '--cached', '--name-only', '--diff-filter=ACM'],
        capture_output=True, text=True
    )
    return [f for f in result.stdout.splitlines() if f.endswith('.html')]


def check_file(path: str):
    errors = []
    with open(path, encoding='utf-8') as f:
        for lineno, line in enumerate(f, 1):
            if OPEN_BLOCK.search(line):
                errors.append((lineno, line.rstrip()))
            elif OPEN_VAR.search(line):
                errors.append((lineno, line.rstrip()))
    return errors


def main():
    files = get_staged_html_files()
    found_errors = False

    for path in files:
        if not Path(path).exists():
            continue
        errors = check_file(path)
        if errors:
            found_errors = True
            print(f"\n[FAIL]  {path}: template tag split across lines:")
            for lineno, line in errors:
                print(f"    Line {lineno}: {line[:120]}")

    if found_errors:
        print(
            "\n[BLOCKED]  Commit blocked: Django template tags must NOT be split across lines."
            "\n    Fix: move the closing %} or }} to the same line as the opening {% or {{."
        )
        sys.exit(1)

    print("✅  Template tag check passed.")
    sys.exit(0)


if __name__ == '__main__':
    main()
