#!/usr/bin/env python3
"""Manage n8n credentials. Subcommands:

  create     — POST /api/v1/credentials with values from .env.<env> (Path A).
  list-link  — GET /api/v1/credentials and link an existing credential into the YAML (Path B).

Path A flow (agent-mediated creation):
  1. Agent appends required secret env-var names to <workspace>/n8n-config/.env.example
     and tells the user to copy those entries into .env.<env> with real values.
  2. Agent runs:
        manage_credentials.py create --env <env> --key <yaml-key> \\
          --type <n8n-credential-type> --name "<display name>" \\
          --env-vars KEY1,KEY2,...
  3. Helper loads .env.<env> via config.py:load_env(), builds the credential `data`
     payload, POSTs to /api/v1/credentials, and writes the returned id+name into
     <workspace>/n8n-config/<env>.yml under credentials.<key>.

Path B flow (user-mediated):
  1. User creates the credential in the n8n UI.
  2. Agent runs:
        manage_credentials.py list-link --env <env> --key <yaml-key> \\
          --type <n8n-credential-type> [--from-name "<existing display name>"]
  3. Helper GETs /credentials, filters by type (and name if --from-name), writes
     the matching id+name into the YAML.

POLICY (encoded here AND in skills/manage-credentials.md):
  - The agent NEVER reads .env* files itself.
  - The agent NEVER collects secrets in chat.
  - This helper is the SOLE code path that loads .env.<env> for credential creation.
"""
import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))


from helpers.workspace import workspace_root
from helpers.config import load_env, load_yaml, save_yaml, configuration_snapshot
from helpers.n8n_client import N8nClient, ensure_client


def _client_for(env_name: str, workspace: Path) -> N8nClient:
    return ensure_client(env_name, workspace)


def _get_schema(client: N8nClient, cred_type: str) -> dict:
    """Best-effort: GET /credentials/schema/{type}. Returns empty dict on failure."""
    try:
        return client.get(f"credentials/schema/{cred_type}")
    except Exception:
        return {}


def _credential_value(field: str, value: str, schema: dict):
    """Convert dotenv text only when the target schema requires a typed value."""
    expected = schema.get("type")
    if expected is None or expected == "string" or (isinstance(expected, list) and "string" in expected):
        return value
    allowed = expected if isinstance(expected, list) else [expected]
    # Parse JSON scalars/collections, never Python expressions or truthiness.
    # Suppress parser details because they may include the secret input.
    try:
        parsed = json.loads(value)
        json.dumps(parsed, allow_nan=False)
    except (TypeError, ValueError):
        raise ValueError(f"Credential field '{field}' requires schema type {expected}; check its selected environment value") from None
    actual = ("null" if parsed is None else "boolean" if isinstance(parsed, bool)
              else "integer" if isinstance(parsed, int) else "number" if isinstance(parsed, float)
              else "object" if isinstance(parsed, dict) else "array" if isinstance(parsed, list)
              else "string")
    if actual not in allowed and not (actual == "integer" and "number" in allowed):
        raise ValueError(f"Credential field '{field}' requires schema type {expected}; check its selected environment value")
    return parsed


def _build_data_payload(env_vars: list[str], values: dict, schema: dict | None = None) -> dict:
    """Map declared env-var names to their values. The keys in the returned dict
    are the n8n field names — convention: same casing as the env var (e.g. CLIENT_ID
    becomes the field 'CLIENT_ID' OR 'clientId' depending on the cred type schema).
    For simplicity, we pass the env var name as-is and let the schema's `data` shape
    drive the mapping. The agent typically passes camelCased var names.
    """
    data = {}
    properties = (schema or {}).get("properties", {})
    for raw in env_vars:
        var = raw.strip()
        if not var:
            continue
        if "=" in var:
            field, _, env_var = var.partition("=")
            field, env_var = field.strip(), env_var.strip()
        else:
            field = env_var = var
        data[field] = _credential_value(field, values.get(env_var, ""), properties.get(field, {}))
    return data


def cmd_create(args) -> None:
    ws = workspace_root(args.workspace)
    observed = configuration_snapshot(ws, [args.env])
    yaml_data = load_yaml(args.env, ws)
    client = _client_for(args.env, ws)

    env_var_names = [v.strip() for v in (args.env_vars or "").split(",") if v.strip()]
    values = load_env(args.env, ws)
    # Detect-by-env-var-presence: a token like `field=ENV_VAR` is "missing" iff
    # ENV_VAR isn't set in the selected environment. Avoids false positives on legitimately
    # falsy values (empty string, "0", "false") and reports the env-var name
    # the user needs to set, not the raw `field=ENV_VAR` token.
    missing = []
    for raw in env_var_names:
        env_name = raw.split("=", 1)[1].strip() if "=" in raw else raw.strip()
        if env_name not in values:
            missing.append(env_name)
    if missing:
        raise SystemExit(f"Missing environment values: {', '.join(missing)}. Add them to the secret file for '{args.env}'.")

    # Dotenv contains strings; n8n credential fields can require JSON numbers,
    # booleans or collections. Validate conversions before creating anything.
    data_payload = _build_data_payload(env_var_names, values, _get_schema(client, args.type))

    body = {
        "name": args.name,
        "type": args.type,
        "data": data_payload,
    }
    project_id = yaml_data.get("n8n", {}).get("projectId")
    if project_id:
        client.require_project(project_id)
        body["projectId"] = project_id

    if args.dry_run:
        redacted = dict(body)
        redacted["data"] = {k: "[REDACTED]" for k in body["data"]}
        print("[dry-run] would POST /credentials:", json.dumps(redacted, indent=2))
        return

    from helpers.sync_state import operation_lock
    with operation_lock(ws, args.env):
        if configuration_snapshot(ws, [args.env]) != observed:
            raise SystemExit("Environment configuration changed; review it before retrying credential registration")
        resp = client.post("credentials", body)
        cred_id = resp.get("id")
        if not cred_id:
            raise ValueError("n8n did not return the created credential ID; inspect the target before retrying")
        cred_name = resp.get("name", args.name)

        creds = yaml_data.setdefault("credentials", {}) or {}
        creds[args.key] = {"id": cred_id, "name": cred_name, "type": args.type}
        yaml_data["credentials"] = creds
        save_yaml(args.env, ws, yaml_data)
        print(f"Created credential '{cred_name}' (id={cred_id}, type={args.type}) → environment '{args.env}' binding credentials.{args.key}")


def cmd_list_link(args) -> None:
    ws = workspace_root(args.workspace)
    observed = configuration_snapshot(ws, [args.env])
    yaml_data = load_yaml(args.env, ws)
    client = _client_for(args.env, ws)

    try:
        all_creds = []
        params = {"limit": 100}
        while True:
            page = client.get("credentials", params=params)
            all_creds.extend(page.get("data", []) if isinstance(page, dict) else page)
            cursor = page.get("nextCursor") if isinstance(page, dict) else None
            if not cursor:
                break
            params["cursor"] = cursor
    except Exception as e:
        print(f"ERROR: list /credentials failed: {e}", file=sys.stderr)
        sys.exit(1)

    matches = [c for c in all_creds if c.get("type") == args.type]
    project_id = yaml_data.get("n8n", {}).get("projectId")
    if project_id:
        matches = [credential for credential in matches if any(
            str(shared.get("projectId", shared.get("id"))) == str(project_id)
            for shared in credential.get("shared", [])
        )]
    if args.from_name:
        matches = [c for c in matches if c.get("name") == args.from_name]
    if not matches:
        print(f"No credentials match type='{args.type}'" + (f" name='{args.from_name}'" if args.from_name else ""), file=sys.stderr)
        sys.exit(1)
    if len(matches) > 1:
        print("Multiple credentials match. Use --from-name to disambiguate:", file=sys.stderr)
        for c in matches:
            print(f"  - id={c.get('id')} name='{c.get('name')}'", file=sys.stderr)
        sys.exit(1)

    chosen = matches[0]
    if args.dry_run:
        print(f"[dry-run] would link '{chosen.get('name')}' to environment '{args.env}' credentials.{args.key}")
        return
    from helpers.sync_state import operation_lock
    with operation_lock(ws, args.env):
        if configuration_snapshot(ws, [args.env]) != observed:
            raise SystemExit("Environment configuration changed; review it before retrying credential registration")
        creds = yaml_data.setdefault("credentials", {}) or {}
        creds[args.key] = {"id": chosen.get("id"), "name": chosen.get("name"), "type": args.type}
        yaml_data["credentials"] = creds
        save_yaml(args.env, ws, yaml_data)
        print(f"Linked credential '{chosen.get('name')}' (id={chosen.get('id')}) → environment '{args.env}' binding credentials.{args.key}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workspace", "--project", dest="workspace", default=None)
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_create = sub.add_parser("create", help="POST /credentials from .env.<env> (Path A)")
    p_create.add_argument("--env", required=True)
    p_create.add_argument("--key", required=True, help="YAML key to write under credentials.<key>")
    p_create.add_argument("--type", required=True, help="n8n credential type (e.g. microsoftOAuth2Api)")
    p_create.add_argument("--name", required=True, help="Display name for the credential")
    p_create.add_argument("--env-vars", default=None, dest="env_vars",
                          help="Comma-separated env-var names that map to credential data fields. "
                               "Use 'fieldName=ENV_VAR' for explicit mapping.")
    p_create.add_argument("--dry-run", action="store_true")

    p_link = sub.add_parser("list-link", help="GET /credentials and link an existing one (Path B)")
    p_link.add_argument("--env", required=True)
    p_link.add_argument("--key", required=True)
    p_link.add_argument("--type", required=True)
    p_link.add_argument("--from-name", default=None, dest="from_name")
    p_link.add_argument("--dry-run", action="store_true")

    args = parser.parse_args()
    if args.cmd == "create":
        cmd_create(args)
    else:
        cmd_list_link(args)


if __name__ == "__main__":
    main()
