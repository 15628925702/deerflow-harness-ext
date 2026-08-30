"""D5 checkpoint snapshot/store tests. Host-agnostic."""
from deerflow_harness_ext.checkpoint.snapshot import WorkspaceSnapshot, capture_snapshot
from deerflow_harness_ext.checkpoint.store import CheckpointStore


def test_capture_works_without_git(tmp_path):
    s = capture_snapshot(str(tmp_path), run_git=False)
    assert s.head is None and s.diff == ""


def test_snapshot_change_detection():
    a = WorkspaceSnapshot(head="h1", diff="", untracked=[])
    b = WorkspaceSnapshot(head="h1", diff="+x", untracked=[])
    assert a.apply_to(b) is True
    c = WorkspaceSnapshot(head="h1", diff="", untracked=[])
    assert a.apply_to(c) is False


def test_snapshot_change_on_head():
    a = WorkspaceSnapshot(head="abc", diff="", untracked=[])
    b = WorkspaceSnapshot(head="def", diff="", untracked=[])
    assert a.apply_to(b) is True


def test_store_records_and_no_change_without_git(tmp_path):
    st = CheckpointStore(str(tmp_path))
    st.record()
    st.record()
    assert st.changed_since() is False
    assert len(st.as_records()) == 2


def test_store_latest():
    st = CheckpointStore("/tmp/nonexistent-dir-for-test")
    st.record()
    assert st.latest() is not None
