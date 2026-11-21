"""The local version: the commit it came from, and where that commit is learned from."""

from __future__ import annotations

import subprocess
from pathlib import Path

from spoider import __version__
from spoider.build import _describe, _installed_from_git, version_string


def test_the_version_names_the_commit_of_the_tree_it_runs_from():
    """Run out of a checkout, the bar says which commit. This is the number a bug report quotes."""
    sha = subprocess.run(
        ["git", "rev-parse", "--short=7", "HEAD"], capture_output=True, text=True, check=True
    ).stdout.strip()
    assert sha, "the repository should have a commit"
    assert version_string().split("+")[0] == __version__
    assert version_string().count("+") == 1, version_string()
    assert version_string().split("+")[1].split(".")[0] == sha


def test_a_clean_build_carries_no_dirty_mark():
    assert _describe(("3f2a1bc", False)) == f"{__version__}+3f2a1bc"


def test_a_build_from_a_changed_tree_says_so():
    """A commit holds nothing of what was in the tree but uncommitted, and a bug report says so."""
    assert _describe(("3f2a1bc", True)) == f"{__version__}+3f2a1bc.dirty"


def test_a_build_that_cannot_name_its_commit_keeps_the_plain_version():
    assert _describe(None) == __version__


def test_an_install_from_git_names_the_commit_its_record_holds(tmp_path: Path, monkeypatch):
    """PEP 610 is what uv and pip leave behind, so an installed copy answers without git."""
    raw = (
        '{"url": "https://github.com/Ramashvili/spoider", '
        '"vcs_info": {"vcs": "git", "commit_id": '
        '"d307a192040d883f6ec61c76768b7aca4429bf94", "requested_revision": "v0.5.13"}}'
    )
    monkeypatch.setattr(
        "spoider.build.metadata.distribution",
        lambda name: type("D", (), {"read_text": lambda self, path: raw})(),
    )
    assert _installed_from_git() == ("d307a19", False)


def test_an_install_with_no_record_answers_nothing(monkeypatch):
    monkeypatch.setattr(
        "spoider.build.metadata.distribution",
        lambda name: type("D", (), {"read_text": lambda self, path: None})(),
    )
    assert _installed_from_git() is None


def test_a_candidate_keeps_its_own_label_and_gains_the_commit(monkeypatch):
    """PEP 440 allows one local label, so `0.5.13+redraw` becomes `0.5.13+redraw.3f2a1bc`."""
    monkeypatch.setattr("spoider.build.__version__", "0.5.13+redraw")
    assert _describe(("3f2a1bc", False)) == "0.5.13+redraw.3f2a1bc"
    assert _describe(("3f2a1bc", True)) == "0.5.13+redraw.3f2a1bc.dirty"
