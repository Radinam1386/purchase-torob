"""Publish the prepared archive to one Liara app. Never print credentials."""
import json
from pathlib import Path
import sys

import httpx
from dotenv import dotenv_values

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "output/liara"
APP = "purchase-torob"
TEAM = "6ad390439ed11c6f00304442"
env = dotenv_values(ROOT / ".env")
client = httpx.Client(base_url="https://api.liara.ir", headers={"Authorization": f"Bearer {env['LIARA_API_TOKEN']}"}, params={"teamID": TEAM}, timeout=60)

def request(method, path, **kwargs):
    print(f"Liara {method} {path}", file=sys.stderr, flush=True)
    response = client.request(method, path, **kwargs)
    if response.is_error:
        raise SystemExit(f"Liara HTTP {response.status_code}: {response.text[:1500]}")
    return response.json() if response.content else {}

action = sys.argv[1]
if action == "provision":
    networks = request("GET", "/v1/networks")["networks"]
    network = next((n for n in networks if n["name"] == "torob"), None)
    if network is None:
        request("POST", "/v1/networks", json={"networkName": "torob"})
        network = next(n for n in request("GET", "/v1/networks")["networks"] if n["name"] == "torob")
    projects = request("GET", "/v1/projects")["projects"]
    if not any(p["project_id"] == APP for p in projects):
        request("POST", "/v1/projects/", json={"name": APP, "platform": "docker", "planID": "medium-g2", "bundlePlanID": "basic", "network": network["_id"], "readOnlyRootFilesystem": False})
    project = request("GET", f"/v1/projects/{APP}")["project"]
    print(json.dumps({"app": APP, "plan": project.get("planID"), "bundle": project.get("bundlePlanID"), "keys": list(project)}))
elif action == "configure":
    project = request("GET", f"/v1/projects/{APP}")["project"]
    disks = request("GET", f"/v1/projects/{project['_id']}/disks")
    if not any(d["name"] == "catalog" for d in disks.get("disks", [])):
        request("POST", f"/v1/projects/{APP}/disks", json={"name": "catalog", "size": 2})
    allowed = {"LLM_API_KEY", "LLM_MODEL", "LLM_BASE_URL", "LLM_REASONING_EFFORT", "SEARCH_ENDPOINT", "SEARCH_API_KEY", "AGENT_MAX_TOOL_ROUNDS", "AGENT_TIMEOUT_MS", "DEFAULT_LAT", "DEFAULT_LNG", "DEFAULT_RADIUS_KM", "GEOCODING_URL", "TZ"}
    variables = {item["key"]: item["value"] for item in project.get("envs", [])}
    variables.update({k: v for k, v in env.items() if k in allowed and v is not None})
    variables.update(DB_PATH="/app/data/torob.sqlite", TOOL_LOG_PATH="/app/data/tool-calls.jsonl", TZ="Asia/Tehran", AGENT_API_INTERNAL="http://127.0.0.1:8000")
    assert "LIARA_API_TOKEN" not in variables
    request("POST", "/v1/projects/update-envs", json={"project": APP, "variables": [{"key": k, "value": v} for k, v in variables.items()]})
    print(json.dumps({"app": APP, "diskGB": 2, "environmentKeys": sorted(variables)}))
elif action == "deploy":
    archive_name = sys.argv[2] if len(sys.argv) > 2 else "app.tgz"
    assert archive_name in {"app.tgz", "cached.tgz"}
    with (OUT / archive_name).open("rb") as source:
        uploaded = request("POST", f"/v2/projects/{APP}/sources", files={"file": ("source.tgz", source, "application/gzip")}, timeout=600)
    print(json.dumps({"uploadKeys": list(uploaded)}), flush=True)
    release = request("POST", f"/v2/projects/{APP}/releases", json={"sourceID": uploaded["sourceID"], "port": 3000, "type": "docker", "build": {"cache": True, "dockerfile": "Dockerfile", "location": "germany"}, "disks": [{"name": "catalog", "mountTo": "/app/data"}], "message": "Complete consultation, product map and Mock contact flow"})
    (OUT / "release.json").write_text(json.dumps(release, indent=2), encoding="utf-8")
    print(json.dumps(release))
elif action == "status":
    saved = json.loads((OUT / "release.json").read_text(encoding="utf-8"))
    release_id = saved.get("releaseID") or saved.get("release", {}).get("_id") or saved.get("_id")
    log_path = OUT / "build-log.json"
    previous = json.loads(log_path.read_text(encoding="utf-8")) if log_path.exists() else {}
    outputs = previous.get("buildOutput", []) if previous.get("release", {}).get("_id") == release_id else []
    for _ in range(12):
        params = {"since": outputs[-1]["createdAt"]} if outputs else {}
        state = request("GET", f"/v2/releases/{release_id}/build-logs", params=params)
        fresh = state.get("buildOutput", [])
        seen = {item["_id"] for item in outputs}
        new = [item for item in fresh if item["_id"] not in seen]
        outputs.extend(new)
        if len(fresh) < 20 or not new:
            break
    state["buildOutput"] = outputs
    (OUT / "build-log.json").write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")
    release = state.get("release", {})
    print(json.dumps({"release": {k: release.get(k) for k in ("_id", "state", "failReason", "queue")}, "lastLines": [b.get("line") for b in state.get("buildOutput", [])[-12:]]}, ensure_ascii=False))
else:
    raise SystemExit("Expected provision, configure, deploy or status")
