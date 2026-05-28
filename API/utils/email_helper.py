"""SMTP email helper with HTML template rendering."""
import os
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from typing import List
from jinja2 import Environment, FileSystemLoader, select_autoescape
from dotenv import load_dotenv

from utils.common import logger

load_dotenv()

SMTP_HOST = os.getenv("SMTP_HOST", "")
SMTP_PORT = int(os.getenv("SMTP_PORT", "587"))
SMTP_USERNAME = os.getenv("SMTP_USERNAME") or os.getenv("SMTP_USER", "")
SMTP_PASSWORD = os.getenv("SMTP_PASSWORD", "")
SMTP_FROM = os.getenv("SMTP_FROM_EMAIL") or os.getenv("SMTP_FROM") or SMTP_USERNAME
SMTP_TLS = (os.getenv("SMTP_TLS") or os.getenv("SMTP_USE_TLS") or "true").lower() == "true"

TEMPLATE_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "templates")
_env = Environment(
    loader=FileSystemLoader(TEMPLATE_DIR),
    autoescape=select_autoescape(["html", "xml"]),
)


def render_template(name: str, **context) -> str:
    try:
        tpl = _env.get_template(name)
        return tpl.render(**context)
    except Exception as e:
        logger.error("Template render failed (%s): %s", name, e)
        return f"<p>{context.get('message','')}</p>"


def send_email(to_list: List[str], subject: str, html_body: str) -> bool:
    """Send an HTML email. Returns True on success."""
    if not SMTP_HOST or not SMTP_USERNAME or not to_list:
        logger.warning("SMTP not configured or no recipients; skipping email.")
        return False
    try:
        msg = MIMEMultipart("alternative")
        msg["Subject"] = subject
        msg["From"] = SMTP_FROM
        msg["To"] = ", ".join(to_list)
        msg.attach(MIMEText(html_body, "html"))

        with smtplib.SMTP(SMTP_HOST, SMTP_PORT, timeout=20) as s:
            if SMTP_TLS:
                s.starttls()
            s.login(SMTP_USERNAME, SMTP_PASSWORD)
            s.sendmail(SMTP_FROM, to_list, msg.as_string())
        logger.info("Email sent to %s: %s", to_list, subject)
        return True
    except Exception as e:
        logger.error("send_email failed: %s", e)
        return False


def send_alert_email(to_list: List[str], alert: dict) -> bool:
    """Pick the right template based on category and send."""
    cat = (alert.get("category") or "").lower()
    if cat == "schema_drift":
        tpl = "schema_alert.html"
        subj = f"[Schema Drift] {alert.get('title','Schema Drift')}"
    elif cat in ("pii", "governance"):
        tpl = "governance_alert.html"
        subj = f"[Governance] {alert.get('title','Governance Alert')}"
    else:
        tpl = "alert_email.html"
        subj = f"[{alert.get('severity','info').upper()}] {alert.get('title','Alert')}"
    html = render_template(tpl, alert=alert)
    return send_email(to_list, subj, html)
