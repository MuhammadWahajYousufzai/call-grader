"""Deployment boundaries: production targets, secret handling, and private audio."""

import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from appwrite.exception import AppwriteException

SCRIPTS = Path(__file__).resolve().parents[3] / "scripts"


def load_script(name):
    spec = importlib.util.spec_from_file_location(name, SCRIPTS / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


deploy = load_script("deploy_appwrite")
bootstrap = load_script("bootstrap_appwrite")


def test_bootstrap_fails_when_required_seed_rows_cannot_be_created():
    tables = Mock()
    tables.list_rows.return_value = {"rows": []}
    tables.create_row.side_effect = RuntimeError("columns unavailable")
    with pytest.raises(RuntimeError, match="Bootstrap seed failed"):
        bootstrap.seed(tables, "database")


@pytest.mark.parametrize("endpoint", ["http://localhost/v1", "https://example.com", "https://user:password@example.com/v1"])
def test_production_target_rejects_local_or_ambiguous_endpoints(endpoint):
    with pytest.raises(deploy.DeployError):
        deploy.validate_target(endpoint, "production-project")


def test_config_does_not_overwrite_existing_secrets(monkeypatch, tmp_path):
    path = tmp_path / ".env.production.json"
    path.write_text("existing-credential")
    monkeypatch.setattr(deploy.getpass, "getpass", lambda _: "test-secret")
    with pytest.raises(FileExistsError):
        deploy.configure(SimpleNamespace(local=False, endpoint="https://example.com/v1", project_id="prod", config=path))
    assert path.read_text() == "existing-credential"


def test_malformed_config_is_private_and_does_not_expose_credentials(tmp_path):
    path = tmp_path / ".env.production.json"
    path.write_text("malformed-private-credential")
    path.chmod(0o600)
    with pytest.raises(deploy.DeployError) as error:
        deploy.configuration(SimpleNamespace(config=path, local=False))
    assert "malformed-private-credential" not in str(error.value)


def test_world_readable_config_is_rejected(tmp_path):
    path = tmp_path / "config.json"
    path.write_text("{}")
    path.chmod(0o644)
    with pytest.raises(deploy.DeployError, match="owner-only"):
        deploy.configuration(SimpleNamespace(config=path, local=False))


def test_variables_preserve_unrelated_values_and_use_distinct_resource_ids(monkeypatch):
    calls = []
    def fake_command(args, *a, **kw):
        calls.append(args)
        return {"variables": [{"key": "INTERNAL_API_TOKEN", "$id": "existing"},
                              {"key": "UNRELATED", "$id": "untouched"}]}
    monkeypatch.setattr(deploy, "command", fake_command)
    for resource_id in ("api", "site"):
        deploy.variables("functions", resource_id, {"INTERNAL_API_TOKEN": "secret", "APPWRITE_ENDPOINT": "endpoint"}, None, {}, ())
    mutations = [args for args in calls if args[1] != "list-variables"]
    assert len(mutations) == 4
    assert all("--secret" in args and "untouched" not in args for args in mutations)
    assert mutations[0][mutations[0].index("--variable-id") + 1] == "existing"
    assert mutations[1][mutations[1].index("--variable-id") + 1] != mutations[3][mutations[3].index("--variable-id") + 1]


def test_schema_waits_for_columns_before_creating_indexes(monkeypatch):
    tables = Mock()
    tables.list_columns.side_effect = [{"columns": [{"key": "name", "status": "processing"}]},
                                      {"columns": [{"key": "name", "status": "available"}]}]
    monkeypatch.setattr(bootstrap.time, "sleep", Mock())
    bootstrap.wait_available(tables, "db", "agents", "columns", [{"key": "name"}], attempts=2)
    assert tables.list_columns.call_count == 2


def test_failed_provisioning_fails_immediately(monkeypatch):
    tables = Mock()
    tables.list_columns.return_value = {"columns": [{"key": "name", "status": "failed"}]}
    monkeypatch.setattr(bootstrap.time, "sleep", Mock())
    with pytest.raises(RuntimeError, match="provisioning failed"):
        bootstrap.wait_available(tables, "db", "agents", "columns", [{"key": "name"}])
    bootstrap.time.sleep.assert_not_called()


def test_function_cli_updates_preserve_scopes_and_private_permissions():
    template = json.loads((SCRIPTS.parent / "appwrite.config.json").read_text())
    function = template["functions"][3]
    args = deploy.function_metadata(function)
    assert args.count("--scopes") == len(function["scopes"])
    assert "--schedule" in args and "--commands" in args and "--deployment-retention" in args
    with pytest.raises(deploy.DeployError, match="must remain empty"):
        deploy.function_metadata({**function, "execute": ['any']})


def test_new_recordings_bucket_has_no_client_access():
    storage = Mock()
    storage.get_bucket.side_effect = AppwriteException("missing", code=404)
    bootstrap.ensure_bucket(storage, "call_recordings")
    settings = storage.create_bucket.call_args.kwargs
    assert settings["permissions"] == [] and settings["file_security"] is False


def test_existing_recordings_bucket_is_secured_without_deleting_audio():
    storage = Mock()
    storage.get_bucket.return_value = {"name": "Recordings", "$permissions": ['read("users")'], "fileSecurity": True}
    bootstrap.ensure_bucket(storage, "call_recordings")
    storage.update_bucket.assert_called_once_with(bucket_id="call_recordings", name="Recordings", permissions=[], file_security=False)
    storage.delete_bucket.assert_not_called()
    storage.delete_file.assert_not_called()


def test_private_recordings_bucket_is_left_unchanged():
    storage = Mock()
    storage.get_bucket.return_value = {"name": "Recordings", "$permissions": [], "fileSecurity": False}
    bootstrap.ensure_bucket(storage, "call_recordings")
    storage.update_bucket.assert_not_called()


def test_api_readiness_returns_failure_status_when_appwrite_is_unavailable(monkeypatch):
    from app.main import ready, repos
    monkeypatch.setattr(repos, "list_docs", Mock(side_effect=RuntimeError("unavailable")))
    response = ready()
    assert response.status_code == 503
    assert json.loads(response.body)["ok"] is False


def test_verification_rejects_public_function_before_any_pipeline_work(monkeypatch):
    monkeypatch.syspath_prepend(str(SCRIPTS))
    import verify_appwrite
    current = {"enabled": True, "deploymentId": "ready-build", "execute": ['any']}
    mocked = Mock(return_value=current)
    monkeypatch.setattr(verify_appwrite, "command", mocked)
    with pytest.raises(verify_appwrite.DeployError, match="must be private"):
        verify_appwrite.verify_resources(SCRIPTS, {}, ())
    assert mocked.call_count == 1


def test_fresh_schema_verification_cannot_target_production(monkeypatch):
    monkeypatch.syspath_prepend(str(SCRIPTS))
    import verify_bootstrap
    with pytest.raises(verify_bootstrap.DeployError, match="restricted"):
        verify_bootstrap.verify_fresh_schema(SimpleNamespace(local=False))


def test_paused_function_metadata_cannot_enable_the_workload():
    template = json.loads((SCRIPTS.parent / 'appwrite.config.json').read_text())
    function = next(f for f in template['functions'] if f['$id'] == 'call-grader-worker')
    args = deploy.function_metadata({**function, 'schedule': '', 'enabled': False})
    assert '--enabled=false' in args and '--enabled' not in args
    assert args[args.index('--schedule')+1] == ''


def test_local_key_swap_is_refreshed_from_private_env(monkeypatch, tmp_path):
    config = {'APPWRITE_ENDPOINT': 'http://localhost/v1', 'APPWRITE_PROJECT_ID': 'local',
              'GEMINI_API_KEY': 'old-test-key', 'JAZZ_UAN': 'test', 'JAZZ_PASSWORD': 'test',
              'INTERNAL_API_TOKEN': 'test', 'GEMINI_TRANSCRIBE_MODEL': 'gemini-3.5-transcribe',
              'GEMINI_ROMANIZER_MODEL': 'gemini-3.8-flash', 'GEMINI_GRADING_MODEL': 'gemini-3.8-flash'}
    path = tmp_path / 'private.json'
    path.write_text(json.dumps(config))
    path.chmod(0o600)
    (tmp_path / 'appwrite.config.json').write_text(json.dumps({'projectId': 'local'}))
    (tmp_path / '.env').write_text('GEMINI_API_KEY=new-test-key\nGEMINI_REQUESTS_PER_MINUTE=3\n')
    monkeypatch.setattr(deploy, 'ROOT', tmp_path)
    values, _ = deploy.configuration(SimpleNamespace(local=True, config=path, flash_model='gemini-2.5-flash'))
    assert values['GEMINI_GRADING_MODEL'] == 'gemini-2.5-flash'
    assert values['GEMINI_ROMANIZER_MODEL'] == 'gemini-2.5-flash'
    assert values['GEMINI_API_KEY'] == 'new-test-key'
    assert values['GEMINI_REQUESTS_PER_MINUTE'] == '3'
    assert json.loads(path.read_text())['GEMINI_API_KEY'] == 'old-test-key'


def test_production_rejects_temporary_flash_override(tmp_path):
    config = {'APPWRITE_ENDPOINT': 'https://example.com/v1', 'APPWRITE_PROJECT_ID': 'prod',
              'GEMINI_API_KEY': 'test-key', 'JAZZ_UAN': 'test', 'JAZZ_PASSWORD': 'test',
              'INTERNAL_API_TOKEN': 'test', 'GEMINI_TRANSCRIBE_MODEL': 'gemini-3.5-transcribe',
              'GEMINI_ROMANIZER_MODEL': 'gemini-3.8-flash', 'GEMINI_GRADING_MODEL': 'gemini-3.8-flash'}
    path = tmp_path / 'private.json'
    path.write_text(json.dumps(config))
    path.chmod(0o600)
    with pytest.raises(deploy.DeployError, match='only for bounded local testing'):
        deploy.configuration(SimpleNamespace(local=False, config=path, flash_model='gemini-2.5-flash'))
    values, _ = deploy.configuration(SimpleNamespace(local=False, config=path, flash_model=None))
    assert values['GEMINI_ROMANIZER_MODEL'] == 'gemini-3.8-flash'
    assert values['GEMINI_GRADING_MODEL'] == 'gemini-3.8-flash'


def test_fresh_schema_uses_bounded_varchar_for_indexed_strings(monkeypatch):
    from app.appwrite.schema import TABLES

    tables = Mock()
    tables.list_columns.return_value = {'columns': []}
    tables.list_indexes.return_value = {'indexes': []}
    monkeypatch.setattr(bootstrap, 'wait_available', lambda *args, **kwargs: None)
    bootstrap.ensure_table(tables, 'disposable', 'agents', TABLES['agents'])
    attributes = [call.kwargs for call in tables.create_varchar_column.call_args_list]
    assert {item['key'] for item in attributes} == {'name', 'jazz_identifier', 'jazz_extension'}
    assert next(item['size'] for item in attributes if item['key'] == 'jazz_identifier') == 128
    tables.create_text_column.assert_not_called()
    tables.create_index.assert_called_once()
