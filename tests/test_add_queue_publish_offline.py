"""Offline tests for helpers/add_queue_publish_to_workflow.py."""
import json
from pathlib import Path

import pytest
import yaml

from helpers.add_queue_publish_to_workflow import (
    _insert_publish,
    _auto_register_queue_scopes,
    _PUBLISH_NODE_NAME,
)


def _minimal_template() -> dict:
    """A tiny workflow: trigger → terminal Set node."""
    return {
        "name": "Smoke",
        "nodes": [
            {
                "id": "t1",
                "name": "Webhook",
                "type": "n8n-nodes-base.webhook",
                "typeVersion": 2,
                "position": [240, 300],
                "parameters": {"path": "smoke"},
            },
            {
                "id": "s1",
                "name": "Set",
                "type": "n8n-nodes-base.set",
                "typeVersion": 3.4,
                "position": [460, 300],
                "parameters": {},
            },
        ],
        "connections": {
            "Webhook": {
                "main": [[{"node": "Set", "type": "main", "index": 0}]],
            },
        },
        "settings": {},
    }


def _publish_node(template: dict) -> dict:
    return next(n for n in template["nodes"] if n["name"] == _PUBLISH_NODE_NAME)


def test_publish_node_inserted_with_default_inputs():
    tpl = _insert_publish(_minimal_template(), "={{ 'orders' }}")
    pub = _publish_node(tpl)
    assert pub["type"] == "n8n-nodes-base.executeWorkflow"
    assert pub["parameters"]["workflowId"]["value"] == "{{@env:workflows.queue_publish.id}}"
    inputs = pub["parameters"]["workflowInputs"]["value"]
    assert inputs["stream"] == "={{ 'orders' }}"
    assert inputs["payload"] == "={{ $json }}"
    assert inputs["max_len"] is None
    assert inputs["approximate"] is True


def test_publish_max_len_and_approximate():
    tpl = _insert_publish(_minimal_template(), "={{ 'orders' }}", max_len=1000, approximate=True)
    inputs = _publish_node(tpl)["parameters"]["workflowInputs"]["value"]
    assert inputs["max_len"] == 1000
    assert inputs["approximate"] is True


def test_publish_no_approximate_flag():
    tpl = _insert_publish(_minimal_template(), "={{ 'orders' }}", max_len=100, approximate=False)
    inputs = _publish_node(tpl)["parameters"]["workflowInputs"]["value"]
    assert inputs["max_len"] == 100
    assert inputs["approximate"] is False


def test_double_insert_refused():
    tpl = _insert_publish(_minimal_template(), "={{ 'orders' }}")
    with pytest.raises(SystemExit):
        _insert_publish(tpl, "={{ 'orders' }}")


def test_downstream_nodes_shifted_right_by_220():
    tpl_in = _minimal_template()
    original_set_x = next(n for n in tpl_in["nodes"] if n["name"] == "Set")["position"][0]
    tpl = _insert_publish(tpl_in, "={{ 'orders' }}")
    new_set_x = next(n for n in tpl["nodes"] if n["name"] == "Set")["position"][0]
    assert new_set_x == original_set_x + 220


def test_auto_register_queue_scopes_static(tmp_path):
    """Static stream → appended to queueScopes in every env yml (idempotent)."""
    ws = tmp_path / "ws"
    (ws / "n8n-config").mkdir(parents=True)
    for env in ("dev", "prod"):
        (ws / "n8n-config" / f"{env}.yml").write_text(yaml.dump({"name": env}))
    _auto_register_queue_scopes(ws, "={{ 'foo' }}", ["dev", "prod"])
    for env in ("dev", "prod"):
        data = yaml.safe_load((ws / "n8n-config" / f"{env}.yml").read_text())
        assert data["queueScopes"] == ["foo"]


def test_auto_register_queue_scopes_dynamic_skipped(tmp_path, capsys):
    """Dynamic stream → no env yml mutation, prints a warning."""
    ws = tmp_path / "ws"
    (ws / "n8n-config").mkdir(parents=True)
    (ws / "n8n-config" / "dev.yml").write_text(yaml.dump({"name": "dev"}))
    _auto_register_queue_scopes(ws, "={{ 'foo-' + $json.x }}")
    data = yaml.safe_load((ws / "n8n-config" / "dev.yml").read_text())
    assert "queueScopes" not in data or data.get("queueScopes") in (None, [])
    captured = capsys.readouterr()
    assert "dynamic" in captured.err.lower()


def _three_node_template() -> dict:
    """Trigger → Validate → Set, used to test named-node insertion modes."""
    return {
        "name": "Three",
        "nodes": [
            {"id": "t1", "name": "Webhook", "type": "n8n-nodes-base.webhook",
             "typeVersion": 2, "position": [240, 300], "parameters": {}},
            {"id": "v1", "name": "Validate", "type": "n8n-nodes-base.code",
             "typeVersion": 2, "position": [460, 300], "parameters": {}},
            {"id": "s1", "name": "Set", "type": "n8n-nodes-base.set",
             "typeVersion": 3.4, "position": [680, 300], "parameters": {}},
        ],
        "connections": {
            "Webhook": {"main": [[{"node": "Validate", "type": "main", "index": 0}]]},
            "Validate": {"main": [[{"node": "Set", "type": "main", "index": 0}]]},
        },
        "settings": {},
    }


def test_insertion_after_named_node():
    tpl = _insert_publish(_three_node_template(), "={{ 'orders' }}",
                          insertion_point="after-named-node:Validate")
    # Wiring: Validate → Queue Publish → Set
    assert tpl["connections"]["Validate"]["main"][0][0]["node"] == _PUBLISH_NODE_NAME
    assert tpl["connections"][_PUBLISH_NODE_NAME]["main"][0][0]["node"] == "Set"
    # Webhook → Validate untouched
    assert tpl["connections"]["Webhook"]["main"][0][0]["node"] == "Validate"
    # Only Set (downstream of Validate) shifted; Webhook + Validate stay put
    positions = {n["name"]: n["position"][0] for n in tpl["nodes"]}
    assert positions["Webhook"] == 240
    assert positions["Validate"] == 460
    assert positions["Set"] == 680 + 220


def test_insertion_before_named_node():
    tpl = _insert_publish(_three_node_template(), "={{ 'orders' }}",
                          insertion_point="before-named-node:Set")
    # Wiring: Validate → Queue Publish → Set
    assert tpl["connections"]["Validate"]["main"][0][0]["node"] == _PUBLISH_NODE_NAME
    assert tpl["connections"][_PUBLISH_NODE_NAME]["main"][0][0]["node"] == "Set"
    positions = {n["name"]: n["position"][0] for n in tpl["nodes"]}
    # Set and downstream shift; Webhook + Validate don't
    assert positions["Webhook"] == 240
    assert positions["Validate"] == 460
    assert positions["Set"] == 680 + 220


def test_insertion_before_terminal_single():
    tpl = _insert_publish(_three_node_template(), "={{ 'orders' }}",
                          insertion_point="before-terminal")
    # Set is the only terminal — Publish lands before it
    assert tpl["connections"]["Validate"]["main"][0][0]["node"] == _PUBLISH_NODE_NAME
    assert tpl["connections"][_PUBLISH_NODE_NAME]["main"][0][0]["node"] == "Set"


def test_insertion_before_terminal_ambiguous():
    """Multiple terminals → error, point user at before-named-node."""
    tpl = _three_node_template()
    # Add a second terminal: Webhook → SecondLeaf
    tpl["nodes"].append({"id": "sl", "name": "SecondLeaf", "type": "n8n-nodes-base.noOp",
                         "typeVersion": 1, "position": [240, 500], "parameters": {}})
    tpl["connections"]["Webhook"]["main"][0].append({"node": "SecondLeaf", "type": "main", "index": 0})
    with pytest.raises(SystemExit) as exc:
        _insert_publish(tpl, "={{ 'orders' }}", insertion_point="before-terminal")
    assert "before-named-node" in str(exc.value)


def test_insertion_named_node_missing():
    with pytest.raises(SystemExit) as exc:
        _insert_publish(_three_node_template(), "={{ 'orders' }}",
                        insertion_point="after-named-node:DoesNotExist")
    assert "not found" in str(exc.value).lower()


def test_insertion_named_node_requires_target():
    with pytest.raises(SystemExit) as exc:
        _insert_publish(_three_node_template(), "={{ 'orders' }}",
                        insertion_point="after-named-node")
    assert "requires a target" in str(exc.value).lower()


def test_insertion_unknown_mode_errors():
    with pytest.raises(SystemExit):
        _insert_publish(_three_node_template(), "={{ 'orders' }}",
                        insertion_point="middle-of-the-canvas")


def test_auto_register_queue_scopes_idempotent(tmp_path):
    """Re-running with the same static scope does not create duplicates."""
    ws = tmp_path / "ws"
    (ws / "n8n-config").mkdir(parents=True)
    (ws / "n8n-config" / "dev.yml").write_text(yaml.dump({"name": "dev"}))
    _auto_register_queue_scopes(ws, "={{ 'foo' }}")
    _auto_register_queue_scopes(ws, "={{ 'foo' }}")
    data = yaml.safe_load((ws / "n8n-config" / "dev.yml").read_text())
    assert data["queueScopes"] == ["foo"]
