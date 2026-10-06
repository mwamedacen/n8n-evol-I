import re
from pathlib import Path
from typing import Any, Optional

import requests

# Compatibility for integrations which used to clear the cache. No clients or
# credentials are retained here: every call resolves the selected environment.
_CACHE: dict = {}

_SECRET_FIELDS = frozenset({"apiKey", "api_key", "password", "secret", "token", "X-N8N-API-KEY"})


def _raise_for_status(response: requests.Response) -> None:
    if response.status_code in range(300, 400):
        raise ValueError("n8n API redirect refused; the configured target must respond directly")
    response.raise_for_status()


class N8nClient:
    def __init__(self, base_url: str, api_key: str, timeout: float = 30):
        if not base_url or not api_key:
            raise ValueError("An explicit n8n target and API key are required")
        from helpers.config import target_identity
        url = target_identity({"n8n": {"instanceName": base_url}})["instanceName"]
        self.base_url = url
        self.timeout = timeout
        self._headers = {
            "X-N8N-API-KEY": api_key,
            "Content-Type": "application/json",
        }

    def _url(self, path: str) -> str:
        return f"{self.base_url}/api/v1/{path.lstrip('/')}"

    def get(self, path: str, params: Optional[dict] = None) -> Any:
        resp = requests.get(self._url(path), headers=self._headers, params=params, timeout=self.timeout, allow_redirects=False)
        _raise_for_status(resp)
        return resp.json() if resp.content else None

    def post(self, path: str, body: Any = None) -> Any:
        resp = requests.post(self._url(path), headers=self._headers, json=body, timeout=self.timeout, allow_redirects=False)
        _raise_for_status(resp)
        return resp.json() if resp.content else None

    def put(self, path: str, body: Any) -> Any:
        resp = requests.put(self._url(path), headers=self._headers, json=body, timeout=self.timeout, allow_redirects=False)
        _raise_for_status(resp)
        return resp.json() if resp.content else None

    def delete(self, path: str) -> Any:
        resp = requests.delete(self._url(path), headers=self._headers, timeout=self.timeout, allow_redirects=False)
        _raise_for_status(resp)
        return resp.json() if resp.content else None

    def get_workflow(self, workflow_id: str) -> dict:
        return self.get(f"workflows/{workflow_id}")

    def require_project(self, project_id: str) -> None:
        """Check an explicit project before mutation; unsupported APIs fail closed."""
        params = {"limit": 100}
        while True:
            result = self.get("projects", params=params)
            if any(str(project.get("id")) == str(project_id) for project in result.get("data", [])):
                return
            cursor = result.get("nextCursor")
            if not cursor:
                raise ValueError(f"n8n project '{project_id}' is not accessible with this environment's API key")
            params["cursor"] = cursor

    def create_workflow(self, body: dict, project_id: str | None = None) -> dict:
        payload = dict(body)
        if project_id:
            self.require_project(project_id)
            # Public API supports projectId on creation. Older deployments reject
            # the field; never retry without it and silently change destination.
            payload["projectId"] = project_id
        result = self.post("workflows", payload)
        if not isinstance(result, dict) or not result.get("id"):
            raise ValueError("n8n did not return the created workflow ID")
        if project_id:
            shared = result.get("shared") or self.get_workflow(result["id"]).get("shared", [])
            if not any(str(row.get("projectId")) == str(project_id) for row in shared):
                raise ValueError(f"Created workflow {result['id']}, but n8n did not confirm requested project {project_id}; inspect before continuing")
        return result

    def list_workflows(self, filter: Optional[dict] = None) -> list:
        return self.get("workflows", params=filter or {}).get("data", [])


def ensure_client(env_name: str, workspace: Path) -> N8nClient:
    """Resolve the selected target and credentials afresh, failing closed."""
    from helpers.config import load_env, load_yaml
    data = load_yaml(env_name, workspace)
    api_key = load_env(env_name, workspace).get("N8N_API_KEY", "")
    if not api_key:
        raise ValueError(f"Missing N8N_API_KEY for environment '{env_name}'; configure its own secret file or scoped process variable")
    return N8nClient(base_url=data["n8n"]["instanceName"], api_key=api_key,
                     timeout=data["n8n"].get("timeout", 30))


def redact_for_debug(data: Any) -> Any:
    """Recursively redact known secret fields from a data structure."""
    if isinstance(data, dict):
        return {k: ("[REDACTED]" if k in _SECRET_FIELDS else redact_for_debug(v)) for k, v in data.items()}
    if isinstance(data, list):
        return [redact_for_debug(item) for item in data]
    return data


def _redact_url(url: str) -> str:
    return re.sub(r"(https?://)([^/]+)", r"\1[HOST]", url)
