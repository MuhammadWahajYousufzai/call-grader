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


deploy = load_script("deploy_production")
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


def test_config_does_not_overwrite_existing_secrets(tmp_path):
    path = tmp_path / ".env.production"
    path.write_text("existing-credential")
    with pytest.raises(deploy.DeployError):
        deploy.write_env(path, {"INTERNAL_API_TOKEN": "replacement"})
    assert path.read_text() == "existing-credential"


def test_config_error_does_not_expose_malformed_credentials(monkeypatch, tmp_path):
    path = tmp_path / ".env.production"
    path.write_text("malformed-private-credential")
    monkeypatch.setattr(deploy.subprocess, "run", Mock(return_value=SimpleNamespace(
        returncode=1, stderr="dotenv error: malformed-private-credential", stdout="")))
    with pytest.raises(deploy.DeployError) as error:
        deploy.configuration(SimpleNamespace(env_file=path))
    assert "malformed-private-credential" not in str(error.value)


def test_runtime_network_ambiguity_stops_deployment(monkeypatch):
    containers = [{"Config": {"Image": "openruntimes/executor:0.29.0", "Env": [f"OPR_EXECUTOR_NETWORK={name}"]}}
                  for name in ("runtime-a", "runtime-b")]
    mock_run = Mock(side_effect=["container-a\ncontainer-b", json.dumps(containers)])
    monkeypatch.setattr(deploy, "run", mock_run)
    with pytest.raises(deploy.DeployError, match="Cannot select one"):
        deploy.runtime_network({}, None)
    assert mock_run.call_count == 2


def test_configure_site_selects_production_preserves_other_variables_and_hides_token(monkeypatch, capsys):
    values = {"APPWRITE_ENDPOINT": "https://production.example.com/v1", "APPWRITE_PROJECT_ID": "production-project",
              "APPWRITE_API_KEY": "fake-key", "OPENAI_API_KEY": "fake-openai", "JAZZ_UAN": "fake-uan",
              "JAZZ_PASSWORD": "fake-password", "INTERNAL_API_TOKEN": "private-test-token"}
    monkeypatch.setattr(deploy, "configuration", lambda args: (values, [], {}))
    calls = []

    def fake_run(command, env, **kwargs):
        calls.append((command, env))
        if command[2] == "get":
            return json.dumps({"framework": "nextjs", "adapter": "ssr", "scopes": ["sessions.write"]})
        if command[2] == "list-variables":
            return json.dumps({"variables": [{"key": "INTERNAL_API_TOKEN", "$id": "existing-token"}]})
        return "{}"

    monkeypatch.setattr(deploy, "run", fake_run)
    deploy.configure_site(SimpleNamespace(site_id="production-site", site_origin="https://calls.example.com/", dry_run=False))
    mutations = [command for command, _ in calls if command[2] in ("create-variable", "update-variable")]
    assert len(mutations) == 3
    token = next(command for command in mutations if "INTERNAL_API_TOKEN" in command)
    assert token[2] == "update-variable" and "existing-token" in token and "--secret" in token
    assert all(env["APPWRITE_PROJECT_ID"] == "production-project" for _, env in calls)
    assert all(env["APPWRITE_ENDPOINT"] == "https://production.example.com/v1" for _, env in calls)
    assert "private-test-token" not in capsys.readouterr().out


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
