"""The local label: when a copy is the release the version names, and when it is something on top."""

from __future__ import annotations

import json
import subprocess

from spoider import __version__
from spoider.build import Build, _describe, _installed_from_git, version_string


def test_a_clean_build_of_the_tag_is_the_release_and_carries_no_label():
    """The tag names the commit, so a release printing a commit says there is something extra when
    there is not. That is the rule this whole file is about."""
    assert _describe(Build("3f2a1bc", dirty=False, tag=f"v{__version__}")) == __version__


def test_a_build_from_a_changed_tree_says_so():
    """A commit holds nothing of what was in the tree but uncommitted, and a bug report says so."""
    assert (
        _describe(Build("3f2a1bc", dirty=True, tag=f"v{__version__}"))
        == f"{__version__}+3f2a1bc.dirty"
    )


def test_a_build_past_the_tag_says_how_far_past_it_is():
    assert _describe(Build("3f2a1bc", dirty=False, tag="")) == f"{__version__}+3f2a1bc"


def test_a_clean_tree_at_some_other_tag_is_not_this_release():
    """Checked out at an older tag the number in the file is still the newest, so the copy says it
    is not that release."""
    assert _describe(Build("3f2a1bc", dirty=False, tag="v0.4.0")) == f"{__version__}+3f2a1bc"


def test_a_build_that_cannot_name_its_commit_keeps_the_plain_version():
    assert _describe(None) == __version__


def test_a_candidate_keeps_its_own_label_and_gains_the_commit(monkeypatch):
    """PEP 440 allows one local label, so `0.5.15+redraw` becomes `0.5.15+redraw.3f2a1bc`."""
    monkeypatch.setattr("spoider.build.__version__", "0.5.15+redraw")
    assert _describe(Build("3f2a1bc", dirty=False, tag="")) == "0.5.15+redraw.3f2a1bc"
    assert _describe(Build("3f2a1bc", dirty=True, tag="")) == "0.5.15+redraw.3f2a1bc.dirty"


def _record(monkeypatch, vcs_info: dict) -> None:
    raw = json.dumps({"url": "https://github.com/Ramashvili/spoider", "vcs_info": vcs_info})
    monkeypatch.setattr(
        "spoider.build.metadata.distribution",
        lambda name: type("D", (), {"read_text": lambda self, path: raw})(),
    )


def test_an_install_from_the_tag_is_the_release(monkeypatch):
    """`uv tool install git+…@v0.5.14` builds that tag, so it is the release and needs no label."""
    _record(
        monkeypatch,
        {
            "vcs": "git",
            "commit_id": "d307a192040d883f6ec61c76768b7aca4429bf94",
            "requested_revision": f"v{__version__}",
        },
    )
    assert _describe(_installed_from_git()) == __version__


def test_an_install_from_a_branch_says_what_it_carries(monkeypatch):
    """A branch is something that moves, so an install from one is never the release."""
    _record(
        monkeypatch,
        {
            "vcs": "git",
            "commit_id": "d307a192040d883f6ec61c76768b7aca4429bf94",
            "requested_revision": "main",
        },
    )
    assert _describe(_installed_from_git()) == f"{__version__}+d307a19"


def test_an_install_with_no_record_answers_nothing(monkeypatch):
    monkeypatch.setattr(
        "spoider.build.metadata.distribution",
        lambda name: type("D", (), {"read_text": lambda self, path: None})(),
    )
    assert _installed_from_git() is None


def test_the_version_of_this_checkout_follows_the_rule():
    """Run out of this repository, the version is what the tree deserves now: the plain number
    exactly when HEAD is the tag named for it and the source is clean."""
    git = ["git", "-C", ".", "describe", "--tags", "--exact-match", "HEAD"]
    tag = subprocess.run(git, capture_output=True, text=True, check=False).stdout.strip()
    changes = subprocess.run(
        ["git", "-C", ".", "status", "--porcelain", "--untracked-files=normal", "--", "src", "pyproject.toml"],
        capture_output=True,
        text=True,
        check=True,
    ).stdout.strip()

    labelled = not (tag == f"v{__version__}" and not changes)
    shown = version_string()
    assert ("+" in shown) is labelled, shown
    assert shown.split("+")[0] == __version__
    if labelled:
        assert shown.split("+")[1].split(".")[0] == subprocess.run(
            ["git", "rev-parse", "--short=7", "HEAD"], capture_output=True, text=True, check=True
        ).stdout.strip()
