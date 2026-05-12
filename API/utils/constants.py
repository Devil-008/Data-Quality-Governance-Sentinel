"""Application-wide constants."""



CONNECTOR_TYPES = ["mysql", "mssql", "databricks", "github", "azure_adf"]

ALERT_SEVERITY = ["critical", "high", "medium", "low", "info"]

ALERT_CATEGORY = [
    "quality", "schema_drift", "pii", "governance",
    "pipeline", "cloud", "databricks"
]

ROLE_ADMIN = "admin"
ROLE_STEWARD = "steward"
ROLE_VIEWER = "viewer"

ROLES = [ROLE_ADMIN, ROLE_STEWARD, ROLE_VIEWER]

# PII regex patterns
PII_PATTERNS = {
    "email":   r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}",
    "phone":   r"(\+?\d{1,3}[-\s]?)?\(?\d{3,5}\)?[-\s]?\d{3,4}[-\s]?\d{3,4}",
    "aadhaar": r"\b\d{4}\s?\d{4}\s?\d{4}\b",
    "pan":     r"\b[A-Z]{5}[0-9]{4}[A-Z]{1}\b",
    "otp":     r"\b\d{4,6}\b",
    "ip":      r"\b(?:\d{1,3}\.){3}\d{1,3}\b",
}

# Hints by column name (case-insensitive substring)
PII_NAME_HINTS = {
    "email":   ["email", "e_mail", "mail"],
    "phone":   ["phone", "mobile", "contact", "msisdn"],
    "aadhaar": ["aadhaar", "aadhar", "uid"],
    "pan":     ["pan", "pan_no", "pan_number"],
    "otp":     ["otp"],
    "ip":      ["ip", "ip_addr", "ip_address"],
    "name":    ["first_name", "last_name", "full_name", "fname", "lname"],
    "dob":     ["dob", "birth", "birthday"],
}
