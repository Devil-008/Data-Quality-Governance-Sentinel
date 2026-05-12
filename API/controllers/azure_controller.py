"""Azure controller — uses connector credentials to query Azure REST APIs."""
import requests
from fastapi import APIRouter, Depends, HTTPException

from database.db_connection import fetch_one
from middleware.auth_middleware import get_current_user
from utils.common import decrypt_config, logger

router = APIRouter(prefix="/api/azure", tags=["azure"])


def _get_token(cfg: dict) -> str:
    r = requests.post(
        f"https://login.microsoftonline.com/{cfg['tenant_id']}/oauth2/v2.0/token",
        data={
            "grant_type": "client_credentials",
            "client_id": cfg["client_id"],
            "client_secret": cfg["client_secret"],
            "scope": "https://management.azure.com/.default",
        }, timeout=15,
    )
    if r.status_code != 200:
        raise HTTPException(status_code=400, detail=f"Azure auth failed: {r.text[:200]}")
    return r.json()["access_token"]


def _load_cfg(connector_id: int) -> dict:
    row = fetch_one("SELECT type, config_json FROM connectors WHERE id=%s", (connector_id,))
    if not row or row["type"] not in ["azure", "azure_rg", "azure_adf"]:
        raise HTTPException(status_code=404, detail="Azure connector not found")
    return decrypt_config(row["config_json"])


@router.post("/resource-groups/{connector_id}")
def list_resource_groups(connector_id: int, user: dict = Depends(get_current_user)):
    cfg = _load_cfg(connector_id)
    tok = _get_token(cfg)
    r = requests.get(
        f"https://management.azure.com/subscriptions/{cfg['subscription_id']}"
        f"/resourcegroups?api-version=2021-04-01",
        headers={"Authorization": f"Bearer {tok}"}, timeout=15,
    )
    if r.status_code != 200:
        raise HTTPException(status_code=400, detail=r.text[:300])
    return r.json().get("value", [])


@router.post("/resources/{connector_id}")
def list_resources(connector_id: int, user: dict = Depends(get_current_user)):
    cfg = _load_cfg(connector_id)
    tok = _get_token(cfg)
    r = requests.get(
        f"https://management.azure.com/subscriptions/{cfg['subscription_id']}"
        f"/resources?api-version=2021-04-01",
        headers={"Authorization": f"Bearer {tok}"}, timeout=20,
    )
    if r.status_code != 200:
        raise HTTPException(status_code=400, detail=r.text[:300])
    return r.json().get("value", [])
