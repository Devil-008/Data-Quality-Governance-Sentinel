"""GitHub controller — workflow runs, secret-leak heuristics, schema (CSV) validation."""
import re
import requests
import csv
import io
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from database.db_connection import fetch_one
from middleware.auth_middleware import get_current_user
from utils.common import decrypt_config

router = APIRouter(prefix="/api/github", tags=["github"])


def _ctx(connector_id: int):
    row = fetch_one("SELECT type, config_json FROM connectors WHERE id=%s", (connector_id,))
    if not row or row["type"] != "github":
        raise HTTPException(status_code=404, detail="GitHub connector not found")
    cfg = decrypt_config(row["config_json"])
    repo = (cfg.get("repository_url") or "").rstrip("/")
    if repo.startswith("http"):
        path = repo.split("github.com/", 1)[-1]
    else:
        path = repo
    headers = {
        "Authorization": f"Bearer {cfg.get('token')}",
        "Accept": "application/vnd.github+json",
    }
    return path, headers


@router.post("/workflows/{connector_id}")
def list_workflows(connector_id: int, user: dict = Depends(get_current_user)):
    path, headers = _ctx(connector_id)
    r = requests.get(f"https://api.github.com/repos/{path}/actions/runs?per_page=30",
                     headers=headers, timeout=20)
    if r.status_code != 200:
        raise HTTPException(status_code=400, detail=r.text[:300])
    runs = r.json().get("workflow_runs", [])
    return [
        {
            "id": run.get("id"),
            "name": run.get("name"),
            "status": run.get("status"),
            "conclusion": run.get("conclusion"),
            "branch": run.get("head_branch"),
            "created_at": run.get("created_at"),
            "html_url": run.get("html_url"),
        }
        for run in runs
    ]


# secret leak regex heuristics
SECRET_PATTERNS = [
    ("aws_access_key", r"AKIA[0-9A-Z]{16}"),
    ("aws_secret_key", r"(?i)aws(.{0,20})?[\'\"][0-9a-zA-Z/+]{40}[\'\"]"),
    ("generic_api_key", r"(?i)api[_-]?key[\"' :=]+[0-9A-Za-z\-_]{20,}"),
    ("private_key", r"-----BEGIN (RSA|EC|DSA|OPENSSH|PRIVATE) PRIVATE KEY-----"),
    ("github_token", r"gh[pousr]_[A-Za-z0-9]{36,}"),
    ("slack_token", r"xox[baprs]-[A-Za-z0-9-]{10,}"),
]


@router.post("/secret-scan/{connector_id}")
def secret_scan(connector_id: int, user: dict = Depends(get_current_user)):
    path, headers = _ctx(connector_id)
    # pull repo tree
    r = requests.get(f"https://api.github.com/repos/{path}", headers=headers, timeout=15)
    if r.status_code != 200:
        raise HTTPException(status_code=400, detail=r.text[:300])
    default_branch = r.json().get("default_branch", "main")
    tree_r = requests.get(
        f"https://api.github.com/repos/{path}/git/trees/{default_branch}?recursive=1",
        headers=headers, timeout=20,
    )
    if tree_r.status_code != 200:
        raise HTTPException(status_code=400, detail=tree_r.text[:300])
    findings = []
    tree = tree_r.json().get("tree", []) or []
    # only scan small text files (limit ~50 files)
    for entry in tree[:200]:
        if entry.get("type") != "blob":
            continue
        fpath = entry.get("path", "")
        if not any(fpath.endswith(ext) for ext in
                   (".py", ".js", ".ts", ".env", ".yml", ".yaml", ".json", ".txt", ".md", ".sh")):
            continue
        size = entry.get("size") or 0
        if size > 200_000:
            continue
        raw = requests.get(
            f"https://raw.githubusercontent.com/{path}/{default_branch}/{fpath}",
            headers={"Authorization": headers["Authorization"]}, timeout=15,
        )
        if raw.status_code != 200:
            continue
        content = raw.text
        for label, pattern in SECRET_PATTERNS:
            try:
                if re.search(pattern, content):
                    findings.append({"file": fpath, "type": label})
                    break
            except re.error:
                continue
        if len(findings) >= 25:
            break
    return {"findings": findings}


class CsvIn(BaseModel):
    file_path: str  # path inside repo
    required_columns: list[str] = []


@router.post("/csv-validate/{connector_id}")
def csv_validate(connector_id: int, body: CsvIn, user: dict = Depends(get_current_user)):
    path, headers = _ctx(connector_id)
    r = requests.get(f"https://api.github.com/repos/{path}", headers=headers, timeout=15)
    if r.status_code != 200:
        raise HTTPException(status_code=400, detail=r.text[:300])
    branch = r.json().get("default_branch", "main")
    raw = requests.get(
        f"https://raw.githubusercontent.com/{path}/{branch}/{body.file_path}",
        headers={"Authorization": headers["Authorization"]}, timeout=20,
    )
    if raw.status_code != 200:
        raise HTTPException(status_code=400, detail=f"File not found: {raw.status_code}")
    text = raw.text
    rdr = csv.reader(io.StringIO(text))
    rows = list(rdr)
    if not rows:
        return {"ok": False, "rows": 0, "issues": ["Empty CSV"]}
    header = [h.strip() for h in rows[0]]
    issues = []
    missing = [c for c in body.required_columns if c not in header]
    if missing:
        issues.append(f"Missing required columns: {missing}")
    expected_cols = len(header)
    bad_rows = sum(1 for r in rows[1:] if len(r) != expected_cols)
    if bad_rows:
        issues.append(f"{bad_rows} rows have inconsistent column count")
    return {
        "ok": not issues, "rows": len(rows) - 1, "columns": header, "issues": issues,
    }
