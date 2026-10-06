"""Offline bootstrap name regressions; all client and persistence calls mocked."""
from copy import deepcopy
from unittest.mock import MagicMock

import pytest

from helpers import bootstrap_env


@pytest.fixture
def calls(monkeypatch):
    client = MagicMock()
    factory = MagicMock(return_value=client)
    save = MagicMock()
    monkeypatch.setattr(bootstrap_env, "N8nClient", factory)
    monkeypatch.setattr(bootstrap_env, "save_yaml", save)
    return factory, client, save


def config(workflows, display_name="", postfix=""):
    return {"n8n": {"instanceName": "https://example.invalid", "projectId": "project-1"},
            "displayName": display_name, "workflowNamePostfix": postfix,
            "workflows": workflows}


@pytest.mark.parametrize("label", ["", " " * 3, "x" * 129])
def test_invalid_later_name_prevents_every_create(tmp_path, calls, label):
    data = config({"first": {"id": "", "name": "Valid"},
                   "later": {"id": "placeholder", "name": label}})
    before = deepcopy(data)
    with pytest.raises(ValueError, match=r"Workflow 'later'.*1 to 128 characters"):
        bootstrap_env._mint_placeholder_workflows(tmp_path, "test", data, "fictional-key", False)
    factory, client, save = calls
    factory.assert_not_called()
    client.create_workflow.assert_not_called()
    save.assert_not_called()
    assert data == before


@pytest.mark.parametrize("length", [1, 128])
def test_name_boundaries_are_created_and_bound_once(tmp_path, calls, length):
    data = config({"task": {"id": "your-placeholder", "name": "x" * length}})
    factory, client, save = calls
    client.create_workflow.return_value = {"id": "new-owned-id"}
    bootstrap_env._mint_placeholder_workflows(tmp_path, "test", data, "fictional-key", False)
    factory.assert_called_once_with("https://example.invalid", "fictional-key")
    client.create_workflow.assert_called_once_with(
        {"name": "x" * length, "nodes": [], "connections": {}, "settings": {}},
        project_id="project-1")
    save.assert_called_once_with("test", tmp_path, data)
    assert data["workflows"]["task"]["id"] == "new-owned-id"
    bootstrap_env._mint_placeholder_workflows(tmp_path, "test", data, "fictional-key", False)
    assert factory.call_count == client.create_workflow.call_count == save.call_count == 1


def test_full_prefix_label_postfix_are_validated_without_exposing_values(tmp_path, calls):
    label = "SENSITIVE_LABEL_" + "x" * 100
    data = config({"nested/task": {"id": "", "name": label}}, "prefix" * 3, "postfix")
    with pytest.raises(ValueError) as exc:
        bootstrap_env._mint_placeholder_workflows(tmp_path, "test", data, "SENSITIVE_API_KEY", False)
    assert "nested/task" in str(exc.value)
    assert "1 to 128" in str(exc.value)
    assert label not in str(exc.value)
    assert "SENSITIVE_API_KEY" not in str(exc.value)
    calls[0].assert_not_called()
    calls[2].assert_not_called()


def test_existing_bound_and_nonmapping_rows_keep_skip_behavior(tmp_path, calls):
    data = config({"bound": {"id": "existing-owned-id", "name": "x" * 129},
                   "legacy-row": "unchanged", "new": {"id": "", "name": "New"}},
                  "Display", " [TEST]")
    factory, client, save = calls
    bound = deepcopy(data["workflows"]["bound"])
    client.create_workflow.return_value = {"id": "new-owned-id"}
    bootstrap_env._mint_placeholder_workflows(tmp_path, "test", data, "fictional-key", False)
    client.create_workflow.assert_called_once_with(
        {"name": "Display New [TEST]", "nodes": [], "connections": {}, "settings": {}},
        project_id="project-1")
    save.assert_called_once_with("test", tmp_path, data)
    assert data["workflows"]["bound"] == bound
    assert data["workflows"]["legacy-row"] == "unchanged"


def test_valid_batch_preserves_order_and_persists_each_returned_id(tmp_path, calls):
    data = config({"first": {"id": "", "name": "First"},
                   "second": {"name": "Second"}})
    factory, client, save = calls
    client.create_workflow.side_effect = [{"id": "owned-first"}, {"id": "owned-second"}]
    persisted = []
    save.side_effect = lambda *args: persisted.append(deepcopy(args[2]["workflows"]))
    bootstrap_env._mint_placeholder_workflows(tmp_path, "test", data, "fictional-key", False)
    assert [c.args[0]["name"] for c in client.create_workflow.call_args_list] == ["First", "Second"]
    assert persisted[0]["first"]["id"] == "owned-first"
    assert "id" not in persisted[0]["second"]
    assert persisted[1]["second"]["id"] == "owned-second"
    assert factory.call_count == 1


def test_dry_run_uses_same_batch_preflight_without_partial_preview(tmp_path, calls, capsys):
    data = config({"first": {"id": "", "name": "Valid"},
                   "later": {"id": "", "name": "x" * 129}})
    with pytest.raises(ValueError, match=r"Workflow 'later'.*1 to 128"):
        bootstrap_env._mint_placeholder_workflows(tmp_path, "test", data, "fictional-key", True)
    assert capsys.readouterr().out == ""
    calls[0].assert_not_called()
    calls[2].assert_not_called()


def test_valid_dry_run_keeps_names_and_bindings_unchanged(tmp_path, calls, capsys):
    data = config({"task": {"id": "placeholder", "name": "Task"}})
    before = deepcopy(data)
    bootstrap_env._mint_placeholder_workflows(tmp_path, "test", data, "fictional-key", True)
    assert "would mint workflow 'Task'" in capsys.readouterr().out
    assert data == before
    calls[0].assert_not_called()
    calls[2].assert_not_called()


@pytest.mark.parametrize("unit", ["\U0001F600", "x\uFE0F", "\ud83d\ude00"])
@pytest.mark.parametrize("length", [128, 129])
def test_unicode_backend_boundaries_preserve_name_bytes_and_create_gate(tmp_path, calls, unit, length):
    name = unit * length
    data = config({"task": {"id": "", "name": name}})
    factory, client, save = calls
    if length == 129:
        with pytest.raises(ValueError, match=r"1 to 128 characters.*got 129"):
            bootstrap_env._mint_placeholder_workflows(tmp_path, "test", data, "fictional-key", False)
        factory.assert_not_called()
        save.assert_not_called()
        assert data["workflows"]["task"]["id"] == ""
    else:
        client.create_workflow.return_value = {"id": "new-owned-id"}
        bootstrap_env._mint_placeholder_workflows(tmp_path, "test", data, "fictional-key", False)
        assert client.create_workflow.call_args.args[0]["name"] == name
        assert data["workflows"]["task"]["id"] == "new-owned-id"


@pytest.mark.parametrize("name,expected", [(" ", 1), ("\uFE0F", 1), ("x\uFE0F\uFE0E", 2)])
def test_backend_count_does_not_add_trimming_or_strip_leading_selectors(name, expected):
    assert bootstrap_env._workflow_name_length(name) == expected
