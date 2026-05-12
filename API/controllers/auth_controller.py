"""Auth controller — login, current user, register (admin-only)."""
from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel, EmailStr

from database.db_connection import fetch_one, execute
from utils.jwt_helper import verify_password, create_token, hash_password
from utils.common import logger
from middleware.auth_middleware import get_current_user, require_roles
from utils.constants import ROLES

router = APIRouter(prefix="/api/auth", tags=["auth"])


class LoginIn(BaseModel):
    username: str
    password: str


class RegisterIn(BaseModel):
    username: str
    email: EmailStr
    password: str
    role: str = "viewer"


@router.post("/login")
def login(body: LoginIn):
    user = fetch_one(
        "SELECT id, username, email, password_hash, role, is_active "
        "FROM users WHERE username = %s OR email = %s",
        (body.username, body.username),
    )
    if not user or not user["is_active"]:
        raise HTTPException(status_code=401, detail="Invalid credentials")
    if not verify_password(body.password, user["password_hash"]):
        raise HTTPException(status_code=401, detail="Invalid credentials")
    token = create_token(user["id"], user["username"], user["role"])
    logger.info("User %s logged in", user["username"])
    return {
        "token": token,
        "user": {
            "id": user["id"],
            "username": user["username"],
            "email": user["email"],
            "role": user["role"],
        },
    }


@router.get("/me")
def me(user: dict = Depends(get_current_user)):
    row = fetch_one(
        "SELECT id, username, email, role, is_active, created_at FROM users WHERE id=%s",
        (user["user_id"],),
    )
    if not row:
        raise HTTPException(status_code=404, detail="User not found")
    return row


@router.post("/register")
def register(body: RegisterIn, user: dict = Depends(require_roles("admin"))):
    if body.role not in ROLES:
        raise HTTPException(status_code=400, detail="Invalid role")
    existing = fetch_one(
        "SELECT id FROM users WHERE username=%s OR email=%s",
        (body.username, body.email),
    )
    if existing:
        raise HTTPException(status_code=409, detail="User already exists")
    new_id = execute(
        "INSERT INTO users (username, email, password_hash, role) VALUES (%s, %s, %s, %s)",
        (body.username, body.email, hash_password(body.password), body.role),
    )
    return {"id": new_id, "message": "User created"}
