"""Offline tests for helpers/create_queue.py — copy + register flow."""
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest


def _stub_workspace(tmp_path: Path) -> Path:
    ws = tmp_path / "ws"
    (ws / "n8n-config").mkdir(parents=True)
    (ws / "n8n-workflows-template").mkdir()
    (ws / "n8n-config/dev.yml").write_text("name: dev\ndisplayName: Development\nn8n:\n  instanceName: https://dev.invalid\n")
    return ws


def test_create_queue_copies_three_primitives(tmp_path, monkeypatch):
    ws = _stub_workspace(tmp_path)
    fake = MagicMock(returncode=0, stdout="ok\n", stderr="")
    with patch("subprocess.run", return_value=fake), \
         patch("sys.argv", ["create_queue.py", "--workspace", str(ws)]):
        import importlib
        import helpers.create_queue as cq
        importlib.reload(cq)
        cq.main()
    for prim in ("queue_publish", "queue_pop", "queue_ack"):
        assert (ws / "n8n-workflows-template" / f"{prim}.template.json").exists(), \
            f"expected {prim}.template.json to be copied"
    assert not (ws / "n8n-workflows-template" / "error_handler_queue_cleanup.template.json").exists()


def test_create_queue_with_error_handler_copies_four(tmp_path):
    ws = _stub_workspace(tmp_path)
    fake = MagicMock(returncode=0, stdout="ok\n", stderr="")
    with patch("subprocess.run", return_value=fake), \
         patch("sys.argv", ["create_queue.py", "--workspace", str(ws), "--include-error-handler"]):
        import importlib
        import helpers.create_queue as cq
        importlib.reload(cq)
        cq.main()
    for prim in ("queue_publish", "queue_pop", "queue_ack", "error_handler_queue_cleanup"):
        assert (ws / "n8n-workflows-template" / f"{prim}.template.json").exists()


def test_create_queue_emits_one_subprocess_per_primitive(tmp_path):
    ws = _stub_workspace(tmp_path)
    fake = MagicMock(returncode=0, stdout="ok\n", stderr="")
    with patch("subprocess.run", return_value=fake) as run, \
         patch("sys.argv", ["create_queue.py", "--workspace", str(ws)]):
        import importlib
        import helpers.create_queue as cq
        importlib.reload(cq)
        cq.main()
    # Three primitives → three create_workflow.py subprocess invocations.
    assert run.call_count == 3
    for call in run.call_args_list:
        cmd = call[0][0]
        assert "create_workflow.py" in cmd[1]
        assert "--no-template" in cmd
        assert "--tier" in cmd


def test_create_queue_with_sample_test_copies_five(tmp_path):
    """--with-sample-test copies the three primitives + the two sample-test workflows."""
    ws = _stub_workspace(tmp_path)
    fake = MagicMock(returncode=0, stdout="ok\n", stderr="")
    with patch("subprocess.run", return_value=fake) as run, \
         patch("sys.argv", ["create_queue.py", "--workspace", str(ws), "--with-sample-test"]):
        import importlib
        import helpers.create_queue as cq
        importlib.reload(cq)
        cq.main()
    for fname in ("queue_publish", "queue_pop", "queue_ack",
                  "queue_sample_producer", "queue_sample_consumer"):
        assert (ws / "n8n-workflows-template" / f"{fname}.template.json").exists(), fname
    # 3 primitives + 2 sample-test workflows = 5 subprocess calls
    assert run.call_count == 5
    # Sample-test workflows register at Tier 1, not Tier 0a
    tiers_by_key = {}
    for call in run.call_args_list:
        cmd = call[0][0]
        key = cmd[cmd.index("--key") + 1]
        tier = cmd[cmd.index("--tier") + 1]
        tiers_by_key[key] = tier
    assert tiers_by_key["queue_publish"] == "Tier 0a: leaves"
    assert tiers_by_key["queue_sample_producer"] == "Tier 1"
    assert tiers_by_key["queue_sample_consumer"] == "Tier 1"


def test_create_queue_partial_failure_continues_and_exits_nonzero(tmp_path):
    """If a registration fails, copy still completes and the process exits non-zero."""
    ws = _stub_workspace(tmp_path)
    bad = MagicMock(returncode=2, stdout="", stderr="boom\n")
    with patch("subprocess.run", return_value=bad), \
         patch("sys.argv", ["create_queue.py", "--workspace", str(ws)]):
        import importlib
        import helpers.create_queue as cq
        importlib.reload(cq)
        with pytest.raises(SystemExit) as exc:
            cq.main()
        assert exc.value.code == 1
    # Templates still copied even though all registrations failed.
    for prim in ("queue_publish", "queue_pop", "queue_ack"):
        assert (ws / "n8n-workflows-template" / f"{prim}.template.json").exists()
