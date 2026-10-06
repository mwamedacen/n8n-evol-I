"""Offline tests for init.py and doctor.py — no real n8n needed."""
import subprocess
import hashlib
import sys
from pathlib import Path
from unittest.mock import patch, MagicMock

import yaml


def _harness() -> Path:
    return Path(__file__).parent.parent


def run(*args, cwd=None) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, *args],
        capture_output=True,
        text=True,
        cwd=cwd,
    )


class TestInit:
    def test_creates_workspace(self, tmp_path):
        ws = tmp_path / "ws"
        r = run(str(_harness() / "helpers" / "init.py"), "--workspace", str(ws))
        assert r.returncode == 0, r.stderr
        assert (ws / "n8n-config").is_dir()
        assert (ws / "n8n-workflows-template").is_dir()
        assert (ws / "AGENTS.md").is_file()
        assert (ws / "N8N-WORKSPACE-MEMORY.md").is_file()
        assert (ws / "n8n-config" / ".env.example").is_file()

    def test_idempotent_preservation(self, tmp_path):
        ws = tmp_path / "ws"
        run(str(_harness() / "helpers" / "init.py"), "--workspace", str(ws))
        before = {p.relative_to(ws): hashlib.sha256(p.read_bytes()).hexdigest()
                  for p in ws.rglob("*") if p.is_file()}
        r = run(str(_harness() / "helpers" / "init.py"), "--workspace", str(ws))
        assert r.returncode == 0, r.stderr
        after = {p.relative_to(ws): hashlib.sha256(p.read_bytes()).hexdigest()
                 for p in ws.rglob("*") if p.is_file()}
        assert after == before

    def test_force_preserves_existing_files(self, tmp_path):
        ws = tmp_path / "ws"
        run(str(_harness() / "helpers" / "init.py"), "--workspace", str(ws))
        sentinel = ws / "sentinel.txt"
        sentinel.write_text("hello")
        r = run(str(_harness() / "helpers" / "init.py"), "--workspace", str(ws), "--force")
        assert r.returncode == 0
        assert sentinel.read_text() == "hello"


class TestDoctor:
    def test_no_workspace(self, tmp_path):
        r = run(
            str(_harness() / "helpers" / "doctor.py"),
            "--workspace", str(tmp_path / "nonexistent"),
        )
        assert "doctor report" in r.stdout.lower()
        # Should not crash with an unhandled traceback
        assert "Traceback" not in r.stderr

    def test_empty_workspace_reports_fail(self, tmp_path):
        ws = tmp_path / "ws"
        ws.mkdir()
        r = run(str(_harness() / "helpers" / "doctor.py"), "--workspace", str(ws))
        assert "doctor report" in r.stdout.lower()
        assert r.returncode == 1

    def test_no_env_configured(self, tmp_path):
        ws = tmp_path / "ws"
        (ws / "n8n-config").mkdir(parents=True)
        (ws / "n8n-workflows-template").mkdir(parents=True)
        r = run(str(_harness() / "helpers" / "doctor.py"), "--workspace", str(ws))
        output = r.stdout
        assert "no env" in output.lower() or "warn" in output.lower()
        assert r.returncode == 0  # WARN rows don't cause non-zero exit


def _make_audit_workspace(tmp_path: Path) -> Path:
    ws = tmp_path / "ws"
    (ws / "n8n-config").mkdir(parents=True)
    (ws / "n8n-workflows-template").mkdir(parents=True)
    (ws / "n8n-config" / "dev.yml").write_text(yaml.dump({
        "name": "dev",
        "displayName": "Development",
        "n8n": {"instanceName": "https://n8n.example.test"},
        "workflows": {},
    }))
    (ws / "n8n-config" / ".env.dev").write_text("N8N_API_KEY=fake\n")
    return ws


class TestDoctorAudit:
    """Audit phase: opt-in via --with-audit / --audit-only; default off."""

    def test_audit_off_by_default_no_post(self, tmp_path):
        ws = _make_audit_workspace(tmp_path)
        with patch("helpers.n8n_client.requests.get") as mock_get, \
             patch("helpers.n8n_client.requests.post") as mock_post:
            mock_get.return_value.raise_for_status.return_value = None
            mock_get.return_value.json.return_value = {"data": []}

            sys.path.insert(0, str(_harness()))
            import helpers.doctor as doc
            old_argv = sys.argv
            sys.argv = ["doctor.py", "--workspace", str(ws), "--env", "dev"]
            try:
                try:
                    doc.main()
                except SystemExit:
                    pass
            finally:
                sys.argv = old_argv

        assert mock_post.call_count == 0

    def test_with_audit_dict_response_single_category(self, tmp_path, capsys):
        """Per-category-dict shape with a credentials section reports a WARN row."""
        ws = _make_audit_workspace(tmp_path)
        with patch("helpers.n8n_client.requests.get") as mock_get, \
             patch("helpers.n8n_client.requests.post") as mock_post:
            mock_get.return_value.raise_for_status.return_value = None
            mock_get.return_value.json.return_value = {"data": []}
            mock_post.return_value.raise_for_status.return_value = None
            # Per-category dict with one populated section.
            mock_post.return_value.json.return_value = {
                "Credentials Risk Report": {
                    "risk": "credentials",
                    "sections": [
                        {"title": "Unused credentials", "location": [{"id": "c1"}, {"id": "c2"}]},
                    ],
                },
                "Database Risk Report": {"risk": "database", "sections": []},
            }

            sys.path.insert(0, str(_harness()))
            import helpers.doctor as doc
            old_argv = sys.argv
            sys.argv = ["doctor.py", "--workspace", str(ws), "--env", "dev", "--with-audit"]
            try:
                try:
                    doc.main()
                except SystemExit:
                    pass
            finally:
                sys.argv = old_argv

        out = capsys.readouterr().out
        assert mock_post.call_count == 1
        assert "audit / Credentials Risk Report" in out
        assert "2 finding(s)" in out
        # Empty Database Risk Report dropped, not present.
        assert "audit / Database" not in out

    def test_with_audit_array_response_shape(self, tmp_path, capsys):
        """Alternate response shape: array of risk-report objects."""
        ws = _make_audit_workspace(tmp_path)
        with patch("helpers.n8n_client.requests.get") as mock_get, \
             patch("helpers.n8n_client.requests.post") as mock_post:
            mock_get.return_value.raise_for_status.return_value = None
            mock_get.return_value.json.return_value = {"data": []}
            mock_post.return_value.raise_for_status.return_value = None
            mock_post.return_value.json.return_value = [
                {
                    "risk": "instance",
                    "sections": [
                        {"title": "Unprotected webhooks", "location": [{"workflowId": "wf-1"}]},
                    ],
                },
                {"risk": "filesystem", "sections": []},
            ]

            sys.path.insert(0, str(_harness()))
            import helpers.doctor as doc
            old_argv = sys.argv
            sys.argv = ["doctor.py", "--workspace", str(ws), "--env", "dev", "--with-audit"]
            try:
                try:
                    doc.main()
                except SystemExit:
                    pass
            finally:
                sys.argv = old_argv

        out = capsys.readouterr().out
        assert "audit / instance" in out
        assert "1 finding(s)" in out
        assert "audit / filesystem" not in out

    def test_with_audit_empty_response_reports_ok(self, tmp_path, capsys):
        ws = _make_audit_workspace(tmp_path)
        with patch("helpers.n8n_client.requests.get") as mock_get, \
             patch("helpers.n8n_client.requests.post") as mock_post:
            mock_get.return_value.raise_for_status.return_value = None
            mock_get.return_value.json.return_value = {"data": []}
            mock_post.return_value.raise_for_status.return_value = None
            mock_post.return_value.json.return_value = {}

            sys.path.insert(0, str(_harness()))
            import helpers.doctor as doc
            old_argv = sys.argv
            sys.argv = ["doctor.py", "--workspace", str(ws), "--env", "dev", "--with-audit"]
            try:
                try:
                    doc.main()
                except SystemExit:
                    pass
            finally:
                sys.argv = old_argv

        out = capsys.readouterr().out
        assert "no risks reported" in out

    def test_audit_only_skips_other_checks(self, tmp_path, capsys):
        ws = _make_audit_workspace(tmp_path)
        with patch("helpers.n8n_client.requests.get") as mock_get, \
             patch("helpers.n8n_client.requests.post") as mock_post:
            mock_get.return_value.raise_for_status.return_value = None
            mock_get.return_value.json.return_value = {"data": []}
            mock_post.return_value.raise_for_status.return_value = None
            mock_post.return_value.json.return_value = {}

            sys.path.insert(0, str(_harness()))
            import helpers.doctor as doc
            old_argv = sys.argv
            sys.argv = ["doctor.py", "--workspace", str(ws), "--env", "dev", "--audit-only"]
            try:
                try:
                    doc.main()
                except SystemExit:
                    pass
            finally:
                sys.argv = old_argv

        out = capsys.readouterr().out
        # Audit row present
        assert "audit" in out
        # Non-audit rows absent
        assert "workspace tree" not in out
        assert "workflow templates" not in out
        # GET (env reachability) NOT called — only POST audit
        assert mock_get.call_count == 0
        assert mock_post.call_count == 1

    def test_with_audit_404_reports_warn(self, tmp_path, capsys):
        """Older n8n instances without /audit return 404 → graceful WARN row."""
        ws = _make_audit_workspace(tmp_path)
        import requests
        with patch("helpers.n8n_client.requests.get") as mock_get, \
             patch("helpers.n8n_client.requests.post") as mock_post:
            mock_get.return_value.raise_for_status.return_value = None
            mock_get.return_value.json.return_value = {"data": []}
            err = requests.HTTPError("404 Client Error: Not Found")
            mock_post.return_value.raise_for_status.side_effect = err

            sys.path.insert(0, str(_harness()))
            import helpers.doctor as doc
            old_argv = sys.argv
            sys.argv = ["doctor.py", "--workspace", str(ws), "--env", "dev", "--with-audit"]
            try:
                try:
                    doc.main()
                except SystemExit:
                    pass
            finally:
                sys.argv = old_argv

        out = capsys.readouterr().out
        assert "endpoint not available" in out
        assert "[⚠]" in out  # WARN icon
