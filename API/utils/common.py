"""Common helpers — logging, config encryption, PII detection."""
import os
import re
import json
import logging
import base64
from typing import Any, Dict, List, Tuple
from cryptography.fernet import Fernet
from dotenv import load_dotenv

from utils.constants import PII_PATTERNS, PII_NAME_HINTS

load_dotenv()

# --- Logging --------------------------------------------------------------
os.makedirs("logs", exist_ok=True)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    handlers=[
        logging.FileHandler("logs/app.log"),
        logging.StreamHandler(),
    ],
)
logger = logging.getLogger("dq_sentinel")


# --- Config encryption ----------------------------------------------------
# Deterministic key derived from JWT_SECRET so the user only manages one secret.
def _fernet() -> Fernet:
    secret = os.getenv("JWT_SECRET", "changeme").encode("utf-8")
    # Pad/trim to 32 bytes and base64-urlsafe encode
    raw = (secret * ((32 // len(secret)) + 1))[:32]
    key = base64.urlsafe_b64encode(raw)
    return Fernet(key)


def encrypt_text(text: str) -> str:
    if text is None:
        return None
    return _fernet().encrypt(text.encode("utf-8")).decode("utf-8")


def decrypt_text(token: str) -> str:
    if not token:
        return token
    try:
        return _fernet().decrypt(token.encode("utf-8")).decode("utf-8")
    except Exception:
        return token  # tolerate plain text for older rows


def encrypt_config(config: Dict[str, Any]) -> str:
    """Encrypt the password-like fields then return JSON string."""
    safe = dict(config)
    for f in ("password", "client_secret", "token", "secret"):
        if f in safe and safe[f]:
            safe[f] = encrypt_text(str(safe[f]))
    return json.dumps(safe)


def decrypt_config(config_json: str) -> Dict[str, Any]:
    if not config_json:
        return {}
    try:
        d = json.loads(config_json)
    except Exception:
        return {}
    for f in ("password", "client_secret", "token", "secret"):
        if f in d and d[f]:
            d[f] = decrypt_text(d[f])
    return d


def mask_secret(value: str) -> str:
    if not value:
        return ""
    if len(value) <= 4:
        return "****"
    return value[:2] + "****" + value[-2:]


# --- PII Detection --------------------------------------------------------
def detect_pii_in_column_name(name: str) -> str:
    """Return PII category by name hint, else empty string."""
    if not name:
        return ""
    lname = name.lower()
    for category, hints in PII_NAME_HINTS.items():
        for h in hints:
            if h in lname:
                return category
    return ""


def detect_pii_in_samples(samples: List[str]) -> str:
    """Return the first PII category detected across samples."""
    if not samples:
        return ""
    text = " ".join(str(s) for s in samples if s is not None)[:5000]
    for cat, pattern in PII_PATTERNS.items():
        try:
            if re.search(pattern, text):
                return cat
        except re.error:
            continue
    return ""


def safe_json_loads(s: str, default=None):
    if not s:
        return default
    try:
        return json.loads(s)
    except Exception:
        return default


def safe_json_dumps(obj: Any) -> str:
    try:
        return json.dumps(obj, default=str)
    except Exception:
        return "{}"
