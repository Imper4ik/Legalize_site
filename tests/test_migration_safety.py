import os
import subprocess

import pytest


def test_migration_safety():
    """
    Ensure that previously committed/applied migrations are never modified or deleted.
    Only new migrations (status 'A') are allowed to be added.
    """
    if os.environ.get("ALLOW_MIGRATION_MODIFICATIONS") == "1":
        pytest.skip("Migration safety check bypassed via ALLOW_MIGRATION_MODIFICATIONS env var.")

    # Skip if we are not in a git repository (e.g. running in production docker without .git)
    if not os.path.exists(".git"):
        pytest.skip("Not a git repository, skipping migration safety check.")

    try:
        # Try diffing against origin/main first, fallback to main, then HEAD~1
        target_ref = "origin/main"
        try:
            subprocess.check_output(["git", "rev-parse", "--verify", "origin/main"], stderr=subprocess.DEVNULL)
        except subprocess.CalledProcessError:
            try:
                subprocess.check_output(["git", "rev-parse", "--verify", "main"], stderr=subprocess.DEVNULL)
                target_ref = "main"
            except subprocess.CalledProcessError:
                # If neither main nor origin/main exists, diff against HEAD~1
                try:
                    subprocess.check_output(["git", "rev-parse", "--verify", "HEAD~1"], stderr=subprocess.DEVNULL)
                    target_ref = "HEAD~1"
                except subprocess.CalledProcessError:
                    pytest.skip("Could not find a base git ref to diff against.")

        # Get name status diff
        diff_output = subprocess.check_output(
            ["git", "diff", target_ref, "--name-status"],
            text=True
        )
    except Exception as e:
        pytest.skip(f"Failed to run git diff: {e}")

    modified_migrations = []

    for line in diff_output.splitlines():
        if not line.strip():
            continue
        parts = line.split("\t")
        if len(parts) < 2:
            continue
        status, filepath = parts[0], parts[1]

        # Check if the file is a migration file (excluding initial and __init__.py if needed,
        # but generally no migration file should ever be modified or deleted)
        if "migrations/" in filepath and filepath.endswith(".py") and not filepath.endswith("__init__.py"):
            # If a migration is Modified (M) or Deleted (D), it's a violation
            if any(s in status for s in ["M", "D"]):
                modified_migrations.append((status, filepath))

    if modified_migrations:
        error_msg = (
            "CRITICAL: The following migration files were modified or deleted relative to base ref:\n"
            + "\n".join(f"  [{status}] {filepath}" for status, filepath in modified_migrations)
            + "\nModifying applied migrations causes production database desynchronization. "
            + "Please revert these changes and create a new migration instead."
        )
        raise AssertionError(error_msg)
