"""Regression checks for real data-loss paths; live execution is tested separately."""
import copy
import json
from pathlib import Path
import pytest
import yaml
from helpers.hydrate import hydrate
from helpers.roundtrip import restore, SyncConflict
from helpers.sync_state import save_baseline
from helpers.resync import plan_resync


def project(tmp_path):
    (tmp_path / 'n8n-config').mkdir()
    (tmp_path / 'n8n-workflows-template').mkdir()
    cfg = {'name':'dev','displayName':'Dev','n8n':{'instanceName':'http://localhost:15678'},
           'credentials':{'service':{'id':'credential-dev'}},'workflows':{'sample':{'id':'workflow-dev'}}}
    (tmp_path / 'n8n-config/dev.yml').write_text(yaml.safe_dump(cfg))
    (tmp_path / 'code.js').write_text('function score() { return 1; }\n')
    (tmp_path / 'prompt.md').write_text('Read this:\n"quoted" input\\output\n')
    (tmp_path / 'schema.json').write_text('{"type":"object"}\n')
    source = {'name':'Sample','nodes':[{'id':'{{@uuid:node}}','name':'Code','type':'n8n-nodes-base.code',
               'parameters':{'jsCode':'{{@js:code.js}}\nreturn score();','prompt':'{{@md:prompt.md}}','schema':'{{@json:schema.json}}'},
               'credentials':{'httpHeaderAuth':{'id':'{{@env:credentials.service.id}}'}}}], 'connections':{},'settings':{}}
    (tmp_path / 'n8n-workflows-template/sample.template.json').write_text(json.dumps(source))
    path = hydrate('dev','sample',tmp_path,strict=True)
    built = json.loads(path.read_text())
    meta = json.loads(path.with_suffix('.meta.json').read_text())
    baseline = {**meta, 'remote':built}
    return source,built,baseline


def test_multiline_assets_stable_ids_and_reference_restoration(tmp_path):
    source, built, baseline = project(tmp_path)
    assert built['nodes'][0]['parameters']['prompt'] == (tmp_path/'prompt.md').read_text()
    assert built['nodes'][0]['parameters']['schema'] == (tmp_path/'schema.json').read_text()
    assert json.loads(hydrate('dev','sample',tmp_path).read_text()) == built
    raw = copy.deepcopy(built)
    raw['nodes'][0]['name'] = 'Renamed in UI'
    raw['nodes'][0]['parameters']['jsCode'] = raw['nodes'][0]['parameters']['jsCode'].replace('return 1;', 'return 2;')
    raw['nodes'][0]['parameters']['prompt'] = 'Changed prompt\n'
    restored, files = restore(raw,baseline,tmp_path,'dev')
    assert restored['nodes'][0]['id'] == '{{@uuid:node}}'
    assert restored['nodes'][0]['parameters']['jsCode'] == source['nodes'][0]['parameters']['jsCode']
    assert restored['nodes'][0]['credentials']['httpHeaderAuth']['id'] == '{{@env:credentials.service.id}}'
    assert files['code.js'] == 'function score() { return 2; }\n'
    assert files['prompt.md'] == 'Changed prompt\n'


def test_both_sides_edit_file_conflict_preserves_local(tmp_path,monkeypatch):
    source,built,baseline = project(tmp_path)
    save_baseline(tmp_path,'dev','sample',source,built,baseline['files'])
    (tmp_path/'code.js').write_text('function score() { return 3; }\n')
    raw=copy.deepcopy(built)
    raw['nodes'][0]['parameters']['jsCode']=raw['nodes'][0]['parameters']['jsCode'].replace('return 1;', 'return 2;')
    class Client:
        def get_workflow(self,_):return raw
    monkeypatch.setattr('helpers.resync.ensure_client',lambda *args:Client())
    with pytest.raises(SyncConflict,match='both sides edited'):
        plan_resync(tmp_path,'dev','sample')
    assert 'return 3;' in (tmp_path/'code.js').read_text()
    assert list((tmp_path/'.n8n-state/dev/incoming').glob('*.json'))


def test_changed_credential_binding_requires_explicit_mapping(tmp_path):
    _,built,baseline=project(tmp_path)
    raw=copy.deepcopy(built)
    raw['nodes'][0]['credentials']['httpHeaderAuth']['id']='foreign-prod-credential'
    with pytest.raises(SyncConflict,match='environment binding'):
        restore(raw,baseline,tmp_path,'dev')


def test_placeholder_symlink_escape_rejected(tmp_path):
    from helpers.placeholder.file_resolver import resolve
    source,built,baseline=project(tmp_path)
    (tmp_path/'escaped').symlink_to('/etc')
    with pytest.raises(ValueError,match='escapes'):
        resolve('{"text":"{{@txt:escaped/passwd}}"}',tmp_path)


def test_source_cannot_read_other_environment_secrets(tmp_path):
    from helpers.placeholder.file_resolver import resolve
    project(tmp_path)
    private = tmp_path/'environments/prod'
    private.mkdir(parents=True)
    (private/'.env').write_text('N8N_API_KEY=other-environment')
    with pytest.raises(ValueError,match='private'):
        resolve('{"text":"{{@txt:environments/prod/.env}}"}',tmp_path)
    (tmp_path/'alias.txt').symlink_to(private/'.env')
    with pytest.raises(ValueError,match='private'):
        resolve('{"text":"{{@txt:alias.txt}}"}',tmp_path)


def test_operation_state_symlink_cannot_write_outside_project(tmp_path):
    from helpers.sync_state import operation_lock
    ws=tmp_path/'project'; ws.mkdir()
    outside=tmp_path/'outside'; outside.mkdir()
    (ws/'.n8n-state').symlink_to(outside,target_is_directory=True)
    with pytest.raises(ValueError,match='symlink'):
        with operation_lock(ws,'dev'):pass
    assert list(outside.iterdir()) == []


def test_hydrate_rejects_key_traversal(tmp_path):
    project(tmp_path)
    with pytest.raises(ValueError,match='Workflow key'):
        hydrate('dev','../escape',tmp_path)
    assert not (tmp_path/'.n8n-state/escape.generated.json').exists()


def test_private_atomic_writes_repair_permissions(tmp_path):
    from helpers.sync_state import atomic_write
    out=tmp_path/'baseline.json';out.write_text('{}');out.chmod(0o644)
    atomic_write(out,'{}',private=True)
    assert out.stat().st_mode & 0o777 == 0o600


def test_dehydrate_does_not_mutate_remote_baseline(tmp_path):
    from helpers.dehydrate import dehydrate_data
    source,built,baseline=project(tmp_path)
    original=copy.deepcopy(built)
    restored=json.loads(dehydrate_data(built,'dev',tmp_path,'sample'))
    assert built == original
    assert restored['nodes'][0]['id']=='{{@uuid:node}}'
    following,files=restore(built,{'source':restored,'remote':built,'files':baseline['files']},tmp_path,'dev')
    assert following==restored


def test_new_unmapped_credential_cannot_enter_shared_source(tmp_path):
    source,built,baseline=project(tmp_path)
    raw=copy.deepcopy(built)
    raw['nodes'].append({'id':'new-node','name':'New','type':'n8n-nodes-base.httpRequest','parameters':{},
                         'credentials':{'httpHeaderAuth':{'id':'unmapped-prod-id'}}})
    with pytest.raises(SyncConflict,match='Register the remote credentials'):
        restore(raw,baseline,tmp_path,'dev')


def test_changing_remote_workflow_id_invalidates_baseline(tmp_path):
    from helpers.sync_state import load_baseline
    source,built,baseline=project(tmp_path)
    save_baseline(tmp_path,'dev','sample',source,built,baseline['files'])
    config=tmp_path/'n8n-config/dev.yml';data=yaml.safe_load(config.read_text())
    data['workflows']['sample']['id']='another-workflow'
    config.write_text(yaml.safe_dump(data))
    with pytest.raises(ValueError,match='Workflow binding changed'):
        load_baseline(tmp_path,'dev','sample')


def test_adoption_keeps_existing_legacy_baseline_usable(tmp_path):
    from helpers.sync_state import load_baseline
    from helpers.init import _scaffold
    source,built,baseline=project(tmp_path)
    save_baseline(tmp_path,'dev','sample',source,built,baseline['files'])
    before=(tmp_path/'.n8n-state/dev/baselines/sample.json').read_bytes()
    _scaffold(tmp_path,adopt=True)
    assert load_baseline(tmp_path,'dev','sample')['source']==source
    assert (tmp_path/'.n8n-state/dev/baselines/sample.json').read_bytes()==before


@pytest.mark.parametrize('operation', ['write', 'lock'])
def test_private_ignore_symlink_cannot_write_unrelated_file(tmp_path, operation):
    from helpers.sync_state import atomic_write, operation_lock
    private = tmp_path/'.n8n-state'
    private.mkdir()
    outside=tmp_path/'unrelated'
    (private/'.gitignore').symlink_to(outside)
    with pytest.raises(ValueError,match='gitignore'):
        if operation=='write':
            atomic_write(private/'result.json','{}',private=True)
        else:
            with operation_lock(tmp_path,'dev'):pass
    assert not outside.exists()


def test_private_ignore_preserves_existing_rules_and_overrides_negation(tmp_path):
    from helpers.sync_state import atomic_write
    (tmp_path/'.gitignore').write_text('# user rule\n!baseline.json\n')
    atomic_write(tmp_path/'baseline.json','{}',private=True)
    assert (tmp_path/'.gitignore').read_text()=='# user rule\n!baseline.json\n*\n'


def test_unmapped_error_workflow_cannot_enter_shared_source(tmp_path, monkeypatch):
    source,built,baseline=project(tmp_path)
    raw=copy.deepcopy(built)
    raw['settings']['errorWorkflow']='unmapped-dev-error-handler'
    with pytest.raises(SyncConflict,match='Register the remote workflows'):
        restore(raw,baseline,tmp_path,'dev')
    class Client:
        def get_workflow(self,_):return raw
    monkeypatch.setattr('helpers.resync.ensure_client',lambda *args:Client())
    with pytest.raises(SyncConflict,match='referenced error workflow'):
        plan_resync(tmp_path,'dev','sample')


def test_nested_workflow_dependency_resolves_portable_key():
    from helpers.dependency_graph import _resolve_workflow_id_to_key
    assert _resolve_workflow_id_to_key('{{@env:workflows.group/child.id}}',{}) == 'group/child'


def test_bulk_deploy_orders_nested_dependency_before_parent(tmp_path, monkeypatch):
    from helpers import deploy_all
    project(tmp_path)
    templates=tmp_path/'n8n-workflows-template'
    (templates/'group').mkdir()
    (templates/'group/child.template.json').write_text(json.dumps({'name':'Child','nodes':[],'connections':{},'settings':{}}))
    parent={'name':'Parent','nodes':[{'name':'Call','type':'n8n-nodes-base.executeWorkflow','parameters':{'workflowId':'{{@env:workflows.group/child.id}}'}}],'connections':{},'settings':{}}
    (templates/'parent.template.json').write_text(json.dumps(parent))
    config_path = tmp_path/'n8n-config/dev.yml'
    config = yaml.safe_load(config_path.read_text())
    config['workflows'].update({'parent': {'id': 'parent-id'}, 'group/child': {'id': 'child-id'}})
    config_path.write_text(yaml.safe_dump(config))
    (tmp_path/'n8n-config/deployment_order.yml').write_text(yaml.safe_dump({'tiers':{'Tier 0':['parent','group/child']}}))
    commands=[]
    class Result:returncode=0
    monkeypatch.setattr(deploy_all.subprocess,'run',lambda args:commands.append(args) or Result())
    monkeypatch.setattr('sys.argv',['deploy_all.py','--workspace',str(tmp_path),'--env','dev','--preview'])
    deploy_all.main()
    assert [args[args.index('--workflow-key')+1] for args in commands]==['group/child','parent']


def test_bulk_deploy_skips_drafts_not_registered_in_selected_environment(tmp_path, monkeypatch):
    from helpers import deploy_all
    project(tmp_path)
    # Neither a template nor a remote binding exists for the other environment's draft.
    (tmp_path/'n8n-config/deployment_order.yml').write_text(yaml.safe_dump({'tiers': {'Tier 1': ['other_environment_draft', 'sample']}}))
    commands = []
    class Result: returncode = 0
    monkeypatch.setattr(deploy_all.subprocess, 'run', lambda args: commands.append(args) or Result())
    monkeypatch.setattr('sys.argv', ['deploy_all.py', '--workspace', str(tmp_path), '--env', 'dev', '--preview'])
    deploy_all.main()
    assert len(commands) == 1
    assert commands[0][commands[0].index('--workflow-key') + 1] == 'sample'


def test_bulk_deploy_requires_dependencies_in_selected_environment(tmp_path, monkeypatch):
    from helpers import deploy_all
    source, _, _ = project(tmp_path)
    source['settings']['errorWorkflow'] = '{{@env:workflows.other_environment_handler.id}}'
    (tmp_path/'n8n-workflows-template/sample.template.json').write_text(json.dumps(source))
    (tmp_path/'n8n-config/deployment_order.yml').write_text(yaml.safe_dump({'tiers': {'Tier 1': ['sample', 'other_environment_handler']}}))
    commands = []
    monkeypatch.setattr(deploy_all.subprocess, 'run', lambda args: commands.append(args))
    monkeypatch.setattr('sys.argv', ['deploy_all.py', '--workspace', str(tmp_path), '--env', 'dev'])
    with pytest.raises(SystemExit, match='not registered in environment'):
        deploy_all.main()
    assert not commands


def test_equivalent_url_and_adoption_preserve_legacy_baseline_node_ids(tmp_path):
    import uuid
    from helpers.init import _scaffold
    from helpers.sync_state import baseline_path, load_baseline
    source, built, metadata = project(tmp_path)
    old_identity = {'project': str(tmp_path.resolve()), 'environment': 'dev',
                    'target': 'https://EXAMPLE.test:443', 'projectId': None}
    old_namespace = json.dumps(old_identity, sort_keys=True) + ':sample'
    old_node_id = str(uuid.uuid5(uuid.NAMESPACE_URL, old_namespace + ':node'))
    built['nodes'][0]['id'] = old_node_id
    path = baseline_path(tmp_path, 'dev', 'sample')
    path.parent.mkdir(parents=True)
    path.write_text(json.dumps({'identity': old_identity, 'workflowId': 'workflow-dev',
                               'source': source, 'remote': built, 'files': metadata['files']}))
    _scaffold(tmp_path, adopt=True)
    config_path = tmp_path/'n8n-config/dev.yml'
    config = yaml.safe_load(config_path.read_text())
    config['n8n']['instanceName'] = 'https://example.test'
    config_path.write_text(yaml.safe_dump(config))
    assert load_baseline(tmp_path, 'dev', 'sample')['identity'] == old_identity
    assert json.loads(hydrate('dev', 'sample', tmp_path).read_text())['nodes'][0]['id'] == old_node_id
    save_baseline(tmp_path, 'dev', 'sample', source, built, metadata['files'])
    upgraded = load_baseline(tmp_path, 'dev', 'sample')
    assert upgraded['identity']['target'] == 'https://example.test'
    assert upgraded['nodeNamespace'] == old_namespace
    assert json.loads(hydrate('dev', 'sample', tmp_path).read_text())['nodes'][0]['id'] == old_node_id
    config['n8n']['instanceName'] = 'https://different.example.test'
    config_path.write_text(yaml.safe_dump(config))
    with pytest.raises(ValueError, match='binding changed'):
        load_baseline(tmp_path, 'dev', 'sample')
