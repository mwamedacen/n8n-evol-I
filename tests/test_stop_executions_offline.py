"""Offline tests for helpers/stop_executions.py — mocks N8nClient HTTP."""
import json
import sys
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
        "workflows": {"alpha": {"id": "wf-alpha", "name": "Alpha"}},
    }))
    (ws / "n8n-config" / ".env.dev").write_text("N8N_API_KEY=fake\n")
    return ws


def _row(eid: str, status: str) -> dict:
    return {"id": eid, "status": status, "workflowId": "wf-alpha", "startedAt": "2026-04-27T00:00:00Z"}


class TestDryRun:
    def test_no_force_prints_candidates_and_does_not_post(self, tmp_path, capsys):
        ws = _make_workspace(tmp_path)

        def get_side_effect(url, headers=None, params=None, timeout=None, allow_redirects=True):
            assert timeout == 30
            assert allow_redirects is False
            r = MagicMock()
            r.raise_for_status.return_value = None
            st = (params or {}).get("status")
            if st == "running":
                r.json.return_value = {"data": [_row("e1", "running"), _row("e2", "running")], "nextCursor": None}
            elif st == "waiting":
                r.json.return_value = {"data": [_row("e3", "waiting")], "nextCursor": None}
            elif st == "queued":
                r.json.return_value = {"data": [], "nextCursor": None}
            else:
                r.json.return_value = {"data": [], "nextCursor": None}
            return r

        with patch("helpers.n8n_client.requests.get") as mock_get, \
             patch("helpers.n8n_client.requests.post") as mock_post:
            mock_get.side_effect = get_side_effect

            import helpers.n8n_client as nc
            nc._CACHE.clear()
            import helpers.stop_executions as se
            old_argv = sys.argv
            sys.argv = ["stop_executions.py", "--workspace", str(ws), "--env", "dev",
                        "--workflow-key", "alpha"]
            try:
                se.main()
            finally:
                sys.argv = old_argv

        out = capsys.readouterr().out
        parsed = json.loads(out)
        assert parsed["dry_run"] is True
        assert parsed["candidates"]["total"] == 3
        assert "Rerun with --force" in parsed["message"]
        # No POST issued.
        assert mock_post.call_count == 0


class TestForceMode:
    def test_force_posts_to_stop_endpoint(self, tmp_path, capsys):
        ws = _make_workspace(tmp_path)

        def get_side_effect(url, headers=None, params=None, timeout=None, allow_redirects=True):
            assert timeout == 30
            assert allow_redirects is False
            r = MagicMock()
            r.raise_for_status.return_value = None
            st = (params or {}).get("status")
            if st == "running":
                r.json.return_value = {"data": [_row("e1", "running")], "nextCursor": None}
            else:
                r.json.return_value = {"data": [], "nextCursor": None}
            return r

        with patch("helpers.n8n_client.requests.get") as mock_get, \
             patch("helpers.n8n_client.requests.post") as mock_post:
            mock_get.side_effect = get_side_effect
            mock_post_resp = MagicMock()
            mock_post_resp.raise_for_status.return_value = None
            mock_post_resp.json.return_value = {"stopped": True, "count": 1}
            mock_post.return_value = mock_post_resp

            import helpers.n8n_client as nc
            nc._CACHE.clear()
            import helpers.stop_executions as se
            old_argv = sys.argv
            sys.argv = ["stop_executions.py", "--workspace", str(ws), "--env", "dev",
                        "--workflow-key", "alpha", "--status", "running", "--force"]
            try:
                se.main()
            finally:
                sys.argv = old_argv

        out = capsys.readouterr().out
        parsed = json.loads(out)
        assert parsed["stopped"]["total"] == 1
        # POST body shape
        assert mock_post.call_count == 1
        post_call = mock_post.call_args_list[-1]
        body = post_call.kwargs.get("json")
        assert body == {"status": ["running"], "workflowId": "wf-alpha"}
        assert post_call.args[0].endswith("/api/v1/executions/stop")

    def test_force_no_candidates_skips_post(self, tmp_path, capsys):
        ws = _make_workspace(tmp_path)

        with patch("helpers.n8n_client.requests.get") as mock_get, \
             patch("helpers.n8n_client.requests.post") as mock_post:
            mock_resp = MagicMock()
            mock_resp.raise_for_status.return_value = None
            mock_resp.json.return_value = {"data": [], "nextCursor": None}
            mock_get.return_value = mock_resp

            import helpers.n8n_client as nc
            nc._CACHE.clear()
            import helpers.stop_executions as se
            old_argv = sys.argv
            sys.argv = ["stop_executions.py", "--workspace", str(ws), "--env", "dev",
                        "--workflow-key", "alpha", "--force"]
            try:
                se.main()
            finally:
                sys.argv = old_argv

        out = capsys.readouterr().out
        parsed = json.loads(out)
        assert parsed["stopped"] == []
        assert mock_post.call_count == 0


class TestStatusListParsing:
    def test_default_statuses_is_running_waiting_queued(self, tmp_path, capsys):
        ws = _make_workspace(tmp_path)
        seen_statuses: list[str] = []

        def get_side_effect(url, headers=None, params=None, timeout=None, allow_redirects=True):
            assert timeout == 30
            assert allow_redirects is False
            r = MagicMock()
            r.raise_for_status.return_value = None
            seen_statuses.append((params or {}).get("status"))
            r.json.return_value = {"data": [], "nextCursor": None}
            return r

        with patch("helpers.n8n_client.requests.get") as mock_get:
            mock_get.side_effect = get_side_effect

            import helpers.n8n_client as nc
            nc._CACHE.clear()
            import helpers.stop_executions as se
            old_argv = sys.argv
            sys.argv = ["stop_executions.py", "--workspace", str(ws), "--env", "dev",
                        "--workflow-key", "alpha"]
            try:
                se.main()
            finally:
                sys.argv = old_argv

        # Helper queries each status in the default list once.
        assert "running" in seen_statuses
        assert "waiting" in seen_statuses
        assert "queued" in seen_statuses

    def test_invalid_status_rejected(self, tmp_path, capsys):
        ws = _make_workspace(tmp_path)
        with patch("helpers.n8n_client.requests.get") as mock_get:
            mock_get.return_value.raise_for_status.return_value = None
            mock_get.return_value.json.return_value = {"data": [], "nextCursor": None}

            import helpers.n8n_client as nc
            nc._CACHE.clear()
            import helpers.stop_executions as se
            old_argv = sys.argv
            sys.argv = ["stop_executions.py", "--workspace", str(ws), "--env", "dev",
                        "--workflow-key", "alpha", "--status", "running,foobar"]
            import pytest
            try:
                with pytest.raises(SystemExit):
                    se.main()
            finally:
                sys.argv = old_argv


class TestNoInteractivePrompt:
    """Regression: helper must never call input() — agents run non-TTY."""

    def test_helper_does_not_prompt(self, tmp_path):
        ws = _make_workspace(tmp_path)
        with patch("helpers.n8n_client.requests.get") as mock_get, \
             patch("helpers.n8n_client.requests.post") as mock_post, \
             patch("builtins.input") as mock_input:
            mock_get.return_value.raise_for_status.return_value = None
            mock_get.return_value.json.return_value = {"data": [_row("e1", "running")], "nextCursor": None}

            import helpers.n8n_client as nc
            nc._CACHE.clear()
            import helpers.stop_executions as se
            old_argv = sys.argv
            sys.argv = ["stop_executions.py", "--workspace", str(ws), "--env", "dev",
                        "--workflow-key", "alpha"]
            try:
                se.main()
            finally:
                sys.argv = old_argv

        assert mock_input.call_count == 0
