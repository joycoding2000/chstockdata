"""Code-commit identity for research runs.

A run manifest binds the exact code state. A dirty worktree must not share
the bare HEAD sha with different contents: the identity derives a unique
worktree fingerprint over the tracked diff and the untracked files, so two
different dirty states never share one run identity, and a clean tree binds
exactly the HEAD commit.
"""

from systematic_investing.research.runner import (
    worktree_identity,
)

HEAD = "a" * 40


def test_clean_worktree_binds_the_head_commit() -> None:
    assert worktree_identity(HEAD, diff=b"", untracked=()) == HEAD


def test_dirty_worktree_identity_is_content_derived_and_distinct() -> None:
    dirty = worktree_identity(HEAD, diff=b"diff --git a/f.py b/f.py\n", untracked=())

    assert dirty.startswith(f"{HEAD}+worktree:")
    assert dirty != HEAD
    assert dirty != worktree_identity(HEAD, diff=b"diff --git other\n", untracked=())


def test_untracked_files_change_the_worktree_identity() -> None:
    first = worktree_identity(
        HEAD, diff=b"", untracked=(("new_strategy.py", "sha256:" + "1" * 64),)
    )
    second = worktree_identity(
        HEAD, diff=b"", untracked=(("new_strategy.py", "sha256:" + "2" * 64),)
    )

    assert first.startswith(f"{HEAD}+worktree:")
    assert first != second


def test_untracked_content_change_changes_the_identity() -> None:
    first = worktree_identity(
        HEAD, diff=b"", untracked=(("notes.txt", "sha256:" + "1" * 64),)
    )
    second = worktree_identity(
        HEAD, diff=b"", untracked=(("notes.txt", "sha256:" + "2" * 64),)
    )

    assert first != second
