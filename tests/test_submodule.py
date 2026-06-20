import subprocess

import pytest

from tdmruns import submodule as sub
from tdmruns.exceptions import VersionResolutionError


def _git(args, cwd):
    subprocess.run(["git", *args], cwd=str(cwd), check=True, capture_output=True, text=True)


@pytest.fixture
def tiny_repo(tmp_path):
    repo = tmp_path / "tiny"
    repo.mkdir()
    (repo / "file.txt").write_text("v1\n")
    _git(["init", "-q"], repo)
    _git(["config", "user.email", "test@example.com"], repo)
    _git(["config", "user.name", "Test"], repo)
    _git(["add", "-A"], repo)
    _git(["commit", "-q", "-m", "v1"], repo)
    _git(["tag", "v1.0"], repo)
    (repo / "file.txt").write_text("v2\n")
    _git(["add", "-A"], repo)
    _git(["commit", "-q", "-m", "v2"], repo)
    _git(["tag", "v2.0"], repo)
    return repo


def test_resolve_version_by_tag(tmp_path, tiny_repo):
    state = sub.resolve_version(tmp_path, tiny_repo, "v1.0")
    assert state.resolved_tag == "v1.0"
    assert state.detached_head is True
    assert state.dirty is False
    assert (tiny_repo / "file.txt").read_text() == "v1\n"


def test_resolve_version_switches_correctly(tmp_path, tiny_repo):
    sub.resolve_version(tmp_path, tiny_repo, "v1.0")
    state = sub.resolve_version(tmp_path, tiny_repo, "v2.0")
    assert state.resolved_tag == "v2.0"
    assert (tiny_repo / "file.txt").read_text() == "v2\n"


def test_resolve_version_unknown_ref_raises(tmp_path, tiny_repo):
    with pytest.raises(VersionResolutionError):
        sub.resolve_version(tmp_path, tiny_repo, "v999.0")


def test_resolve_version_refuses_dirty_tree(tmp_path, tiny_repo):
    sub.resolve_version(tmp_path, tiny_repo, "v1.0")
    (tiny_repo / "file.txt").write_text("uncommitted change\n")
    with pytest.raises(VersionResolutionError):
        sub.resolve_version(tmp_path, tiny_repo, "v2.0")


def test_short_version_label_prefers_tag(tmp_path, tiny_repo):
    state = sub.resolve_version(tmp_path, tiny_repo, "v1.0")
    assert sub.short_version_label(state) == "v1.0"
