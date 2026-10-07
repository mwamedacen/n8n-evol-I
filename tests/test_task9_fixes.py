"""Unit tests for the task #9 deep-dive fixes plus the task #12 finding-#15 fix.

Each test pins one fix landed in the deep-dive — if a future refactor breaks
the behavior, the test fails loudly with a name pointing at the original
finding number.
"""
import json
import os
from pathlib import Path

import pytest
import yaml


# ---------------------------------------------------------------------------
# Finding #2 — sentinel guard in env_resolver
# ---------------------------------------------------------------------------


def test_finding2_sentinel_guard_blocks_placeholder_value(tmp_path: Path) -> None:
    """env_resolver must refuse to substitute the bootstrap-env sentinel
    'placeholder' / '' / 'your-...' for any workflows.* or credentials.* path.
    """
    from helpers.placeholder.env_resolver import resolve

    (tmp_path / "n8n-config").mkdir()
    (tmp_path / "n8n-config" / "dev.yml").write_text(yaml.dump({
        "name": "dev",
        "displayName": "D",
        "n8n": {"instanceName": "x"},
        "workflows": {"foo": {"id": "placeholder", "name": "Foo"}},
        "credentials": {},
    }))
    (tmp_path / "n8n-config" / ".env.dev").write_text("N8N_API_KEY=test\n")

    text = '{"workflowId":"{{@env:workflows.foo.id}}"}'
    with pytest.raises(ValueError, match=r"[Ss]entinel"):
        resolve(text, "dev", tmp_path)


def test_finding2_sentinel_guard_allows_real_id(tmp_path: Path) -> None:
    """A non-sentinel id must pass through unchanged."""
    from helpers.placeholder.env_resolver import resolve

    (tmp_path / "n8n-config").mkdir()
    (tmp_path / "n8n-config" / "dev.yml").write_text(yaml.dump({
        "name": "dev",
        "displayName": "D",
        "n8n": {"instanceName": "x"},
        "workflows": {"foo": {"id": "AB12cdEFghI3JkLm", "name": "Foo"}},
        "credentials": {},
    }))
    (tmp_path / "n8n-config" / ".env.dev").write_text("N8N_API_KEY=test\n")

    text = '{"workflowId":"{{@env:workflows.foo.id}}"}'
    out = resolve(text, "dev", tmp_path)
    assert out == '{"workflowId":"AB12cdEFghI3JkLm"}'


def test_finding2_sentinel_guard_skips_non_id_paths(tmp_path: Path) -> None:
    """Sentinel guard only enforces on workflows.* / credentials.* — top-level
    fields like displayName can legitimately contain any string."""
    from helpers.placeholder.env_resolver import resolve

    (tmp_path / "n8n-config").mkdir()
    (tmp_path / "n8n-config" / "dev.yml").write_text(yaml.dump({
        "name": "dev",
        "displayName": "placeholder",  # contrived but legal — non-id path
        "n8n": {"instanceName": "x"},
        "workflows": {},
        "credentials": {},
    }))
    (tmp_path / "n8n-config" / ".env.dev").write_text("N8N_API_KEY=test\n")

    out = resolve('{"name":"{{@env:displayName}}"}', "dev", tmp_path)
    assert out == '{"name":"placeholder"}'


# ---------------------------------------------------------------------------
# Finding #3 — dehydrate metadata strip extension
# ---------------------------------------------------------------------------


def test_finding3_dehydrate_strips_publish_model_metadata() -> None:
    """All five fields added in the 2026-04 publish-model expansion must be
    stripped on dehydrate. If n8n adds more, extend the strip list."""
    from helpers.dehydrate import _METADATA_FIELDS

    for field in ("activeVersion", "activeVersionId", "versionCounter",
                  "description", "staticData"):
        assert field in _METADATA_FIELDS, (
            f"_METADATA_FIELDS must strip '{field}' (added in task #9 fix). "
            f"Current strip list: {sorted(_METADATA_FIELDS)}"
        )


def test_finding3_dehydrate_does_not_strip_workflow_content() -> None:
    """Regression guard: never strip name/nodes/connections/settings — those
    are the workflow's actual content, not metadata."""
    from helpers.dehydrate import _METADATA_FIELDS

    for field in ("name", "nodes", "connections", "settings"):
        assert field not in _METADATA_FIELDS, (
            f"_METADATA_FIELDS must NOT strip '{field}' — that's workflow "
            f"content, not metadata. Removing it would corrupt every template."
        )


# ---------------------------------------------------------------------------
# Finding #6 — n8n_client empty-response guard
# ---------------------------------------------------------------------------


def test_finding6_empty_response_returns_none() -> None:
    """All four verbs must return None instead of raising JSONDecodeError when
    n8n returns 204 No Content (e.g. DELETE /variables/{id})."""
    from unittest.mock import patch, Mock
    from helpers.n8n_client import N8nClient

    client = N8nClient(base_url="https://x.test", api_key="k")

    for verb in ("get", "post", "put", "delete"):
        mock_resp = Mock()
        mock_resp.status_code = 204
        mock_resp.content = b""  # empty body
        mock_resp.raise_for_status = Mock()
        with patch(f"helpers.n8n_client.requests.{verb}", return_value=mock_resp):
            args = ("path",) if verb in ("get", "delete") else ("path", {})
            result = getattr(client, verb)(*args) if verb != "delete" else client.delete("path")
            assert result is None, f"{verb}() must return None on empty response, got {result!r}"


# ---------------------------------------------------------------------------
# Finding #8 — init.py seeds cloud-functions-tests/conftest.py
# ---------------------------------------------------------------------------


def test_finding8_init_seeds_cloud_fn_conftest(tmp_path: Path) -> None:
    """init.py must seed cloud-functions-tests/conftest.py mirroring the
    n8n-functions-tests scaffold so `pytest cloud-functions-tests/` works
    out-of-the-box after add_cloud_function.py."""
    import subprocess
    import sys

    workspace = tmp_path / "ws"
    helper = Path(__file__).resolve().parents[1] / "helpers" / "init.py"
    r = subprocess.run(
        [sys.executable, str(helper), "--workspace", str(workspace)],
        capture_output=True, text=True,
    )
    assert r.returncode == 0, r.stderr

    conftest = workspace / "cloud-functions-tests" / "conftest.py"
    assert conftest.exists(), "init.py must seed cloud-functions-tests/conftest.py"
    content = conftest.read_text()
    assert "cloud-functions" in content, (
        "conftest must add cloud-functions/ to sys.path so test imports of "
        "`functions.<name>` resolve. Got:\n" + content
    )


# ---------------------------------------------------------------------------
# Finding (extra) — doctor.py --json verdict mode
# ---------------------------------------------------------------------------


def test_doctor_json_mode_emits_verdict(tmp_path: Path) -> None:
    """doctor.py --json must emit {verdict, checks} with a known verdict value."""
    import subprocess
    import sys

    workspace = tmp_path / "ws"
    init_helper = Path(__file__).resolve().parents[1] / "helpers" / "init.py"
    subprocess.run(
        [sys.executable, str(init_helper), "--workspace", str(workspace)],
        capture_output=True, text=True, check=True,
    )

    doctor = Path(__file__).resolve().parents[1] / "helpers" / "doctor.py"
    r = subprocess.run(
        [sys.executable, str(doctor), "--workspace", str(workspace), "--json"],
        capture_output=True, text=True,
    )
    out = json.loads(r.stdout)
    assert "verdict" in out and "checks" in out
    # No env configured yet → "ok" or "fail" depending on whether template
    # check fires. The schema is what matters here, not the verdict.
    assert out["verdict"] in {
        "ok", "fail", "needs-bootstrap", "needs-mint",
        "api-unreachable", "audit-findings",
    }
    assert isinstance(out["checks"], list)
    for row in out["checks"]:
        assert set(row.keys()) == {"state", "label", "detail"}


# ---------------------------------------------------------------------------
# Finding #11 — deploy_run_assert exposes --expect-status
# ---------------------------------------------------------------------------


def test_finding11_deploy_run_assert_has_expect_status() -> None:
    """The --expect-status flag must be in deploy_run_assert's argparse and
    threaded through to the inner run.py call."""
    import subprocess
    import sys

    helper = Path(__file__).resolve().parents[1] / "helpers" / "deploy_run_assert.py"
    r = subprocess.run([sys.executable, str(helper), "--help"], capture_output=True, text=True)
    assert "--expect-status" in r.stdout, (
        "deploy_run_assert.py must expose --expect-status in argparse"
    )


# ---------------------------------------------------------------------------
# Finding #12 — create_lock two-pass refactor
# ---------------------------------------------------------------------------


def test_finding15_normalize_canonical_form_passthrough() -> None:
    """`={{ <expr> }}` form is the canonical n8n executeWorkflow defineBelow
    expression syntax and must pass through unchanged."""
    from helpers.add_lock_to_workflow import _normalize_n8n_expression

    out, normalized = _normalize_n8n_expression("={{ $execution.id }}")
    assert out == "={{ $execution.id }}"
    assert normalized is False


def test_finding15_normalize_bare_equals_form() -> None:
    """Bare `=<expr>` (no `{{ }}`) is silently treated as a literal by n8n —
    must be auto-wrapped to `={{ <expr> }}` form. This was the root cause of
    finding #15 (lock-concurrency live test exposed a literal-string scope)."""
    from helpers.add_lock_to_workflow import _normalize_n8n_expression

    out, normalized = _normalize_n8n_expression("='lock-' + $json.scope")
    assert out == "={{ 'lock-' + $json.scope }}"
    assert normalized is True


def test_finding15_normalize_literal_scope() -> None:
    """A bare literal (no leading `=`) is wrapped as a JS string expression so
    the deployed template uses the canonical form consistently."""
    from helpers.add_lock_to_workflow import _normalize_n8n_expression

    out, normalized = _normalize_n8n_expression("global")
    assert out == '={{ "global" }}'
    assert normalized is True


def test_finding15_reject_empty_scope() -> None:
    """Empty / None scope is rejected with a clear remediation pointer.
    Avoids a silent ghost-bug where an unset env var produces an empty-string
    scope on a deployed lock."""
    import pytest as _pytest
    from helpers.add_lock_to_workflow import _normalize_n8n_expression

    for bad in ("", "   ", None):
        with _pytest.raises(ValueError, match=r"non-empty"):
            _normalize_n8n_expression(bad)


def test_finding15_deployed_template_uses_canonical_form(tmp_path: Path) -> None:
    """End-to-end: invoke add_lock_to_workflow.py with a bare-= expression and
    verify the deployed template's Lock Acquire node has the canonical
    `={{ ... }}` form on `parameters.workflowInputs.value.scope`."""
    import subprocess
    import sys
    import yaml

    workspace = tmp_path / "ws"
    init_helper = Path(__file__).resolve().parents[1] / "helpers" / "init.py"
    subprocess.run(
        [sys.executable, str(init_helper), "--workspace", str(workspace)],
        capture_output=True, text=True, check=True,
    )

    (workspace / "n8n-config" / "dev.yml").write_text(yaml.safe_dump({
        "name": "dev", "displayName": "Development",
        "n8n": {"instanceName": "https://dev.invalid"},
    }))

    # Stub a minimal workflow template for the helper to wrap.
    (workspace / "n8n-workflows-template" / "demo.template.json").write_text(json.dumps({
        "name": "demo",
        "nodes": [{"id": "a", "name": "Webhook", "type": "n8n-nodes-base.webhook",
                   "typeVersion": 2, "position": [240, 300], "parameters": {"path": "demo"}}],
        "connections": {},
        "settings": {"executionOrder": "v1"},
    }))
    # Need lock_acquisition / lock_release primitive templates present (helper
    # checks they're in the workspace before splicing).
    for primitive in ("lock_acquisition", "lock_release"):
        (workspace / "n8n-workflows-template" / f"{primitive}.template.json").write_text(json.dumps({
            "name": primitive, "nodes": [], "connections": {},
        }))

    helper = Path(__file__).resolve().parents[1] / "helpers" / "add_lock_to_workflow.py"
    r = subprocess.run(
        [sys.executable, str(helper),
         "--workspace", str(workspace), "--workflow-key", "demo", "--env", "dev",
         "--scope-expression", "='lock-' + $json.scope"],
        capture_output=True, text=True,
    )
    # Helper should succeed and emit the deprecation warning to stderr.
    assert r.returncode == 0, f"helper exited {r.returncode}\nstdout: {r.stdout}\nstderr: {r.stderr}"
    assert "normalized to canonical form" in r.stderr.lower(), (
        "Bare-= input must trigger a deprecation warning. Got stderr:\n" + r.stderr
    )

    # Verify the deployed template's scope field is now canonical.
    deployed = json.loads((workspace / "n8n-workflows-template" / "demo.template.json").read_text())
    acquire_node = next(n for n in deployed["nodes"] if n["name"] == "Lock Acquire")
    scope = acquire_node["parameters"]["workflowInputs"]["value"]["scope"]
    assert scope.startswith("={{") and scope.rstrip().endswith("}}"), (
        f"Lock Acquire node's scope must be in canonical ={{ ... }} form, got {scope!r}"
    )

    release_node = next(n for n in deployed["nodes"] if n["name"] == "Lock Release")
    release_scope = release_node["parameters"]["workflowInputs"]["value"]["scope"]
    assert release_scope == scope, "Acquire and Release must use the same normalized scope expression"


def test_finding12_create_lock_two_pass_structure() -> None:
    """create_lock.py must copy all primitives in pass 1 before attempting any
    registration, so a registration failure mid-loop doesn't leave a partially-
    copied workspace."""
    helper = Path(__file__).resolve().parents[1] / "helpers" / "create_lock.py"
    src = helper.read_text()
    # The fix uses two distinct loops. Look at call sites only (exclude the
    # function definitions, which use `def _copy_primitive(`).
    import re
    copy_calls = [m.start() for m in re.finditer(r"_copy_primitive\(ws", src)]
    register_calls = [m.start() for m in re.finditer(r"_register_via_create_workflow\(ws", src)]
    assert copy_calls and register_calls, (
        "create_lock.py must contain at least one call to each helper"
    )
    assert max(copy_calls) < min(register_calls), (
        "create_lock.py must do all _copy_primitive calls before any "
        "_register_via_create_workflow call (two-pass refactor for "
        "resumability — see task #9 finding #12)."
    )
