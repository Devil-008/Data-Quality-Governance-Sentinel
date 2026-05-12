"""Settings controller — read/update app_settings."""
from fastapi import APIRouter, Depends, HTTPException
from typing import Dict, Any
from pydantic import BaseModel

from database.db_connection import fetch_all, fetch_one, execute
from middleware.auth_middleware import get_current_user, require_roles
from utils.jwt_helper import hash_password, verify_password

router = APIRouter(prefix="/api/settings", tags=["settings"])


@router.get("/list")
def list_settings(user: dict = Depends(get_current_user)):
    rows = fetch_all("SELECT setting_key, setting_value, updated_at FROM app_settings ORDER BY setting_key")
    return rows


class SettingIn(BaseModel):
    key: str
    value: str


@router.post("/update")
def update_setting(body: SettingIn, user: dict = Depends(require_roles("admin"))):
    # upsert
    execute(
        "INSERT INTO app_settings (setting_key, setting_value) VALUES (%s, %s) "
        "ON DUPLICATE KEY UPDATE setting_value=VALUES(setting_value)",
        (body.key, body.value or ""),
    )
    return {"updated": True}


class PasswordChangeIn(BaseModel):
    old_password: str
    new_password: str


@router.post("/change-password")
def change_password(body: PasswordChangeIn, user: dict = Depends(get_current_user)):
    if not body.new_password or len(body.new_password) < 6:
        raise HTTPException(status_code=400, detail="New password must be at least 6 characters")
    row = fetch_one(
        "SELECT id, password_hash FROM users WHERE id=%s",
        (user["user_id"],),
    )
    if not row:
        raise HTTPException(status_code=404, detail="User not found")
    if not verify_password(body.old_password, row["password_hash"]):
        raise HTTPException(status_code=400, detail="Current password is incorrect")
    execute(
        "UPDATE users SET password_hash=%s WHERE id=%s",
        (hash_password(body.new_password), row["id"]),
    )
    return {"updated": True}
