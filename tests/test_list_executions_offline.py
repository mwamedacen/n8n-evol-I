"""Offline tests for helpers/list_executions.py — mocks N8nClient HTTP."""
import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch, MagicMock

import yaml


def _harness() -> Path:
    return Path(__file__).parent.parent


sys.path.insert(0, str(_harness()))


def _make_workspace(tmp_path: Path) -> Path:
    ws = tmp_path / "ws"
    (ws / "n8n-config").mkdir(parents=True)
    (ws / "n8n-workflows-template").mkdir(parents=True)
    (ws / "n8n-config" / "dev.yml").write_text(yaml.dump({
        "name": "dev",
        "displayName": "Development",
        "n8n": {"instanceName": "https://n8n.example.test"},
        "workflows": {
            "alpha": {"id": "wf-alpha", "name": "Alpha"},
            "beta":  {"id": "wf-beta",  "name": "Beta"},
        },
    }))
    (ws / "n8n-config" / ".env.dev").write_text("N8N_API_KEY=fake\n")
    return ws


def _row(eid: str, wid: str, status: str, started_at: str) -> dict:
    return {
        "id": eid,
        "workflowId": wid,
        "status": status,
        "startedAt": started_at,
        "stoppedAt": None,
        "finished": status not in ("running", "waiting", "queued"),
    }


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _ago(seconds: int) -> str:
    return (datetime.now(timezone.utc) - timedelta(seconds=seconds)).isoformat().replace("+00:00", "Z")


class TestKeyedFlow:
    """Path A — caller provides --workflow-key, helper hits /executions once with workflowId."""

    def test_keyed_returns_filtered_rows(self, tmp_path, capsys):
        ws = _make_workspace(tmp_path)

        rows = [
            _row("e1", "wf-alpha", "success", _now_iso()),
            _row("e2", "wf-alpha", "error", _now_iso()),
        ]

        with patch("helpers.n8n_client.requests.get") as mock_get:
            mock_resp = MagicMock()
            mock_resp.raise_for_status.return_value = None
            mock_resp.json.return_value = {"data": rows, "nextCursor": None}
            mock_get.return_value = mock_resp

            import helpers.n8n_client as nc
            nc._CACHE.clear()
            import helpers.list_executions as le
            old_argv = sys.argv
            sys.argv = ["list_executions.py", "--workspace", str(ws), "--env", "dev",
                        "--workflow-key", "alpha"]
            try:
                le.main()
            finally:
                sys.argv = old_argv

        out = capsys.readouterr().out
        parsed = json.loads(out)
        assert len(parsed) == 2
        assert {r["id"] for r in parsed} == {"e1", "e2"}

    def test_keyed_uses_workflowId_param(self, tmp_path):
        ws = _make_workspace(tmp_path)

        with patch("helpers.n8n_client.requests.get") as mock_get:
            mock_resp = MagicMock()
            mock_resp.raise_for_status.return_value = None
            mock_resp.json.return_value = {"data": [], "nextCursor": None}
            mock_get.return_value = mock_resp

            import helpers.n8n_client as nc
            nc._CACHE.clear()
            import helpers.list_executions as le
            old_argv = sys.argv
            sys.argv = ["list_executions.py", "--workspace", str(ws), "--env", "dev",
                        "--workflow-key", "alpha"]
            try:
                le.main()
            finally:
                sys.argv = old_argv

        call = mock_get.call_args_list[-1]
        params = call.kwargs.get("params") or {}
        assert params.get("workflowId") == "wf-alpha"


class TestEnvScopedFlow:
    """When no --workflow-key, helper makes a single env-scoped call (no workflowId param)."""

    def test_no_workflow_key_omits_workflowId_param(self, tmp_path, capsys):
        ws = _make_workspace(tmp_path)

        rows = [
            _row("e-alpha-1", "wf-alpha", "success", _now_iso()),
            _row("e-beta-1", "wf-beta", "error", _now_iso()),
        ]

        with patch("helpers.n8n_client.requests.get") as mock_get:
            mock_resp = MagicMock()
            mock_resp.raise_for_status.return_value = None
            mock_resp.json.return_value = {"data": rows, "nextCursor": None}
            mock_get.return_value = mock_resp

            import helpers.n8n_client as nc
            nc._CACHE.clear()
            import helpers.list_executions as le
            old_argv = sys.argv
            sys.argv = ["list_executions.py", "--workspace", str(ws), "--env", "dev"]
            try:
                le.main()
            finally:
                sys.argv = old_argv

        # Single env-scoped GET to /executions; no workflowId param.
        assert mock_get.call_count == 1
        params = mock_get.call_args_list[-1].kwargs.get("params") or {}
        assert "workflowId" not in params

        parsed = json.loads(capsys.readouterr().out)
        ids = {r["id"] for r in parsed}
        assert ids == {"e-alpha-1", "e-beta-1"}


class TestCursorPagination:
    """Helper follows nextCursor across pages."""

    def test_pagination_stitches_two_pages(self, tmp_path, capsys):
        ws = _make_workspace(tmp_path)

        page1 = {"data": [_row(f"e{i}", "wf-alpha", "success", _now_iso()) for i in range(3)],
                 "nextCursor": "cursor-2"}
        page2 = {"data": [_row(f"e{i}", "wf-alpha", "success", _now_iso()) for i in range(3, 5)],
                 "nextCursor": None}
        responses = iter([page1, page2])

        def get_side_effect(url, headers=None, params=None, timeout=None, allow_redirects=True):
            assert timeout == 30
            assert allow_redirects is False
            r = MagicMock()
            r.raise_for_status.return_value = None
            r.json.return_value = next(responses)
            return r

        with patch("helpers.n8n_client.requests.get") as mock_get:
            mock_get.side_effect = get_side_effect

            import helpers.n8n_client as nc
            nc._CACHE.clear()
            import helpers.list_executions as le
            old_argv = sys.argv
            sys.argv = ["list_executions.py", "--workspace", str(ws), "--env", "dev",
                        "--workflow-key", "alpha", "--limit", "10"]
            try:
                le.main()
            finally:
                sys.argv = old_argv

        parsed = json.loads(capsys.readouterr().out)
        assert len(parsed) == 5

        page2_call = mock_get.call_args_list[-1]
        assert page2_call.kwargs.get("params", {}).get("cursor") == "cursor-2"

    def test_limit_caps_post_filter_rows(self, tmp_path, capsys):
        ws = _make_workspace(tmp_path)

        rows = [_row(f"e{i}", "wf-alpha", "success", _now_iso()) for i in range(20)]

        with patch("helpers.n8n_client.requests.get") as mock_get:
            mock_resp = MagicMock()
            mock_resp.raise_for_status.return_value = None
            mock_resp.json.return_value = {"data": rows, "nextCursor": None}
            mock_get.return_value = mock_resp

            import helpers.n8n_client as nc
            nc._CACHE.clear()
            import helpers.list_executions as le
            old_argv = sys.argv
            sys.argv = ["list_executions.py", "--workspace", str(ws), "--env", "dev",
                        "--workflow-key", "alpha", "--limit", "5"]
            try:
                le.main()
            finally:
                sys.argv = old_argv

        parsed = json.loads(capsys.readouterr().out)
        assert len(parsed) == 5


class TestStartedWindow:
    """Client-side time-window filtering applies to startedAt."""

    def test_started_after_excludes_older_rows(self, tmp_path, capsys):
        ws = _make_workspace(tmp_path)
        now = datetime.now(timezone.utc)
        old = (now - timedelta(days=2)).isoformat().replace("+00:00", "Z")
        recent = now.isoformat().replace("+00:00", "Z")
        rows = [
            _row("old", "wf-alpha", "success", old),
            _row("recent", "wf-alpha", "success", recent),
        ]
        threshold = (now - timedelta(hours=1)).isoformat().replace("+00:00", "Z")

        with patch("helpers.n8n_client.requests.get") as mock_get:
            mock_resp = MagicMock()
            mock_resp.raise_for_status.return_value = None
            mock_resp.json.return_value = {"data": rows, "nextCursor": None}
            mock_get.return_value = mock_resp

            import helpers.n8n_client as nc
            nc._CACHE.clear()
            import helpers.list_executions as le
            old_argv = sys.argv
            sys.argv = ["list_executions.py", "--workspace", str(ws), "--env", "dev",
                        "--workflow-key", "alpha", "--started-after", threshold]
            try:
                le.main()
            finally:
                sys.argv = old_argv

        parsed = json.loads(capsys.readouterr().out)
        assert {r["id"] for r in parsed} == {"recent"}


class TestTallyMode:
    """`--tally` walks all pages, emits a histogram + hung/crash counts."""

    def test_tally_returns_histogram_with_hung_counts(self, tmp_path, capsys):
        ws = _make_workspace(tmp_path)

        rows = [
            _row("e1", "wf-alpha", "success", _now_iso()),
            _row("e2", "wf-alpha", "error", _now_iso()),
            _row("e3", "wf-alpha", "waiting", _now_iso()),
            _row("e4", "wf-alpha", "queued", _now_iso()),
            _row("e5", "wf-alpha", "running", _ago(7200)),
            _row("e6", "wf-alpha", "running", _now_iso()),
            _row("e7", "wf-alpha", "crashed", _now_iso()),
        ]

        with patch("helpers.n8n_client.requests.get") as mock_get:
            mock_resp = MagicMock()
            mock_resp.raise_for_status.return_value = None
            mock_resp.json.return_value = {"data": rows, "nextCursor": None}
            mock_get.return_value = mock_resp

            import helpers.n8n_client as nc
            nc._CACHE.clear()
            import helpers.list_executions as le
            old_argv = sys.argv
            sys.argv = ["list_executions.py", "--workspace", str(ws), "--env", "dev",
                        "--workflow-key", "alpha", "--tally"]
            try:
                le.main()
            finally:
                sys.argv = old_argv

        parsed = json.loads(capsys.readouterr().out)
        assert parsed["total"] == 7
        assert parsed["hung_count"] == 3
        assert parsed["crash_count"] == 1
        assert parsed["running_hung_count"] == 1
        assert parsed["by_status"]["success"] == 1
        assert parsed["by_status"]["error"] == 1
        assert parsed["by_status"]["crashed"] == 1

    def test_tally_ignores_limit(self, tmp_path, capsys):
        """`--tally` must walk all rows even if --limit is small."""
        ws = _make_workspace(tmp_path)
        rows = [_row(f"e{i}", "wf-alpha", "success", _now_iso()) for i in range(50)]

        with patch("helpers.n8n_client.requests.get") as mock_get:
            mock_resp = MagicMock()
            mock_resp.raise_for_status.return_value = None
            mock_resp.json.return_value = {"data": rows, "nextCursor": None}
            mock_get.return_value = mock_resp

            import helpers.n8n_client as nc
            nc._CACHE.clear()
            import helpers.list_executions as le
            old_argv = sys.argv
            sys.argv = ["list_executions.py", "--workspace", str(ws), "--env", "dev",
                        "--workflow-key", "alpha", "--tally", "--limit", "5"]
            try:
                le.main()
            finally:
                sys.argv = old_argv

        parsed = json.loads(capsys.readouterr().out)
        assert parsed["total"] == 50

    def test_tally_env_scoped_without_workflow_key(self, tmp_path, capsys):
        """`--tally` without `--workflow-key` issues a single env-scoped call (no workflowId)."""
        ws = _make_workspace(tmp_path)

        rows = [
            _row("a1", "wf-alpha", "success", _now_iso()),
            _row("a2", "wf-alpha", "error", _now_iso()),
            _row("b1", "wf-beta", "error", _now_iso()),
        ]

        with patch("helpers.n8n_client.requests.get") as mock_get:
            mock_resp = MagicMock()
            mock_resp.raise_for_status.return_value = None
            mock_resp.json.return_value = {"data": rows, "nextCursor": None}
            mock_get.return_value = mock_resp

            import helpers.n8n_client as nc
            nc._CACHE.clear()
            import helpers.list_executions as le
            old_argv = sys.argv
            sys.argv = ["list_executions.py", "--workspace", str(ws), "--env", "dev",
                        "--tally"]
            try:
                le.main()
            finally:
                sys.argv = old_argv

        # One env-scoped GET; no workflowId in params.
        assert mock_get.call_count == 1
        params = mock_get.call_args_list[-1].kwargs.get("params") or {}
        assert "workflowId" not in params

        parsed = json.loads(capsys.readouterr().out)
        assert parsed["total"] == 3
        assert parsed["by_status"]["success"] == 1
        assert parsed["by_status"]["error"] == 2


class TestStatusFilter:
    def test_status_passed_through_to_api(self, tmp_path):
        ws = _make_workspace(tmp_path)

        with patch("helpers.n8n_client.requests.get") as mock_get:
            mock_resp = MagicMock()
            mock_resp.raise_for_status.return_value = None
            mock_resp.json.return_value = {"data": [], "nextCursor": None}
            mock_get.return_value = mock_resp

            import helpers.n8n_client as nc
            nc._CACHE.clear()
            import helpers.list_executions as le
            old_argv = sys.argv
            sys.argv = ["list_executions.py", "--workspace", str(ws), "--env", "dev",
                        "--workflow-key", "alpha", "--status", "crashed"]
            try:
                le.main()
            finally:
                sys.argv = old_argv

        params = mock_get.call_args_list[-1].kwargs.get("params") or {}
        assert params.get("status") == "crashed"
        assert params.get("workflowId") == "wf-alpha"
