"""In-app notifications controller."""
from fastapi import APIRouter, Depends, HTTPException

from database.db_connection import fetch_all, fetch_one, execute
from middleware.auth_middleware import get_current_user

router = APIRouter(prefix="/api/notifications", tags=["notifications"])


@router.get("/list")
def list_notifications(user: dict = Depends(get_current_user)):
    return fetch_all(
        "SELECT * FROM notifications WHERE user_id=%s ORDER BY created_at DESC LIMIT 200",
        (user["user_id"],),
    )


@router.get("/unread-count")
def unread_count(user: dict = Depends(get_current_user)):
    row = fetch_one(
        "SELECT COUNT(*) AS c FROM notifications WHERE user_id=%s AND is_read=0",
        (user["user_id"],),
    )
    return {"count": int((row or {}).get("c") or 0)}


@router.post("/{nid}/read")
def mark_read(nid: int, user: dict = Depends(get_current_user)):
    if not fetch_one("SELECT id FROM notifications WHERE id=%s AND user_id=%s",
                     (nid, user["user_id"])):
        raise HTTPException(status_code=404, detail="Not found")
    execute("UPDATE notifications SET is_read=1 WHERE id=%s", (nid,))
    return {"ok": True}


@router.post("/read-all")
def read_all(user: dict = Depends(get_current_user)):
    execute("UPDATE notifications SET is_read=1 WHERE user_id=%s", (user["user_id"],))
    return {"ok": True}
