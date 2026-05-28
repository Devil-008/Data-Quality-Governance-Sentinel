"""Application-wide constants."""


CONNECTOR_TYPES = ["mysql", "mssql", "databricks", "github", "azure_adf"]

ALERT_SEVERITY = ["critical", "high", "medium", "low", "info"]

ALERT_CATEGORY = [
    "quality", "schema_drift", "pii", "governance",
    "pipeline", "cloud", "databricks", "anomaly",
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

# ---------------------------------------------------------------------------
# Quality check catalogues — the user-facing list of checks per connector type.
# (The Python quality_engine executes these as deterministic rules.)
# ---------------------------------------------------------------------------
QUALITY_CHECKS = {
    "mysql": [
        # Completeness
        {"id": "mysql_null_check", "name": "Null value check",
         "description": "Detects NULL or missing values per column",
         "category": "completeness"},
        {"id": "mysql_blank_garbage", "name": "Blank / garbage values",
         "description": "Detects whitespace-only, control-char, or junk values",
         "category": "completeness"},
        {"id": "mysql_missing_columns", "name": "Missing mandatory columns",
         "description": "Verifies that all required columns exist",
         "category": "completeness"},
        {"id": "mysql_row_count", "name": "Row count validation",
         "description": "Validates row count against thresholds",
         "category": "completeness"},
        {"id": "mysql_truncation", "name": "Truncation check",
         "description": "Detects values right at max length (potentially truncated)",
         "category": "completeness"},

        # Uniqueness
        {"id": "mysql_duplicate_check", "name": "Duplicate record check",
         "description": "Detects duplicated records / values",
         "category": "uniqueness"},
        {"id": "mysql_pk_uniqueness", "name": "Primary key uniqueness",
         "description": "Verifies PK rows are unique",
         "category": "uniqueness"},

        # Validity
        {"id": "mysql_data_type", "name": "Data type validation",
         "description": "Validates declared vs actual types",
         "category": "validity"},
        {"id": "mysql_invalid_datetime", "name": "Invalid date/time check",
         "description": "Detects dates outside reasonable bounds",
         "category": "validity"},
        {"id": "mysql_numeric_range", "name": "Numeric range validation",
         "description": "Min/max sanity checks on numeric fields",
         "category": "validity"},

        # Accuracy
        {"id": "mysql_outlier", "name": "Outlier / anomaly detection",
         "description": "Statistical IQR + z-score outlier scan",
         "category": "accuracy"},
        {"id": "mysql_misplaced_data", "name": "Misplaced / incorrect data",
         "description": "Mixed-type values in a single column",
         "category": "accuracy"},
        {"id": "mysql_invalid_sign", "name": "Invalid negative / positive values",
         "description": "Negative values in non-negative fields and vice-versa",
         "category": "accuracy"},

        # Integrity
        {"id": "mysql_fk_integrity", "name": "Foreign key integrity",
         "description": "Detects FK orphans",
         "category": "integrity"},
        {"id": "mysql_referential_integrity",
         "name": "Referential integrity check",
         "description": "Verifies referential consistency between tables",
         "category": "integrity"},

        # Timeliness
        {"id": "mysql_data_freshness", "name": "Data freshness check",
         "description": "Detects stale data using max(timestamp_col)",
         "category": "timeliness"},

        # Consistency
        {"id": "mysql_schema_drift", "name": "Schema drift detection",
         "description": "Compares current schema vs last snapshot",
         "category": "consistency"},

        # Governance
        {"id": "mysql_pii_detection", "name": "PII / sensitive data detection",
         "description": "Detects PII categories by name and content",
         "category": "governance"},
        {"id": "mysql_governance", "name": "Data governance compliance",
         "description": "Required metadata / classification present",
         "category": "governance"},

        # Anomaly
        {"id": "mysql_trend_deviation",
         "name": "Substantial trend deviation (historical)",
         "description": "Compares current metrics against historical baseline",
         "category": "anomaly"},
    ],
    "azure_adf": [
        {"id": "adf_pipeline_status", "name": "Pipeline execution status",
         "description": "Recent run statuses per pipeline",
         "category": "pipeline"},
        {"id": "adf_failed_activity", "name": "Failed activity detection",
         "description": "Detects failed activities inside pipelines",
         "category": "pipeline"},
        {"id": "adf_pipeline_duration", "name": "Pipeline duration threshold",
         "description": "Compares run duration against historical mean",
         "category": "anomaly"},
        {"id": "adf_trigger_failure", "name": "Trigger failure monitoring",
         "description": "Detects schedule / trigger failures",
         "category": "pipeline"},
        {"id": "adf_dataset_existence", "name": "Dataset existence validation",
         "description": "Validates ADF Datasets are reachable",
         "category": "validity"},
        {"id": "adf_linked_service", "name": "Linked service connectivity",
         "description": "Verifies linked services respond",
         "category": "connectivity"},
        {"id": "adf_parameter_validation", "name": "Parameter validation",
         "description": "Validates pipeline parameters",
         "category": "validity"},
        {"id": "adf_schema_drift", "name": "Schema drift detection",
         "description": "Detects schema drift in dataflows",
         "category": "consistency"},
        {"id": "adf_row_count",
         "name": "Source-to-target row count validation",
         "description": "Validates row counts between source and target",
         "category": "completeness"},
        {"id": "adf_late_execution", "name": "Late pipeline execution detection",
         "description": "Detects pipelines that ran late vs schedule",
         "category": "timeliness"},
        {"id": "adf_retry_count", "name": "Retry count monitoring",
         "description": "Monitors retry counts per activity",
         "category": "pipeline"},
        {"id": "adf_data_freshness", "name": "Data freshness validation",
         "description": "Validates output dataset freshness",
         "category": "timeliness"},
        {"id": "adf_dependency_failure", "name": "Dependency failure tracking",
         "description": "Tracks dependency-pipeline failures",
         "category": "pipeline"},
        {"id": "adf_missing_file", "name": "Missing file detection",
         "description": "Detects missing input files",
         "category": "completeness"},
        {"id": "adf_incremental_load", "name": "Incremental load validation",
         "description": "Validates incremental-load pipelines",
         "category": "completeness"},
    ],
    "databricks": [
        # Note: We now focus on pipelines/jobs only — clusters are no longer
        # discovered as datasets.
        {"id": "databricks_pipeline_status", "name": "Pipeline / job status",
         "description": "Recent run statuses per pipeline/job",
         "category": "pipeline"},
        {"id": "databricks_job_failure", "name": "Job / pipeline failure monitoring",
         "description": "Detects failed runs on jobs and DLT pipelines",
         "category": "pipeline"},
        {"id": "databricks_notebook_status", "name": "Notebook execution status",
         "description": "Tracks notebook/task execution outcomes",
         "category": "pipeline"},
        {"id": "databricks_pipeline_duration",
         "name": "Pipeline duration trend",
         "description": "Detects runtime deviations vs historical baseline",
         "category": "anomaly"},
        {"id": "databricks_streaming_lag", "name": "Streaming lag monitoring",
         "description": "Monitors structured-streaming lag",
         "category": "performance"},
        {"id": "databricks_data_completeness", "name": "Data completeness check",
         "description": "Validates expected rows per pipeline output",
         "category": "completeness"},
        {"id": "databricks_file_ingestion", "name": "File ingestion validation",
         "description": "Validates file ingestion counts",
         "category": "completeness"},
        {"id": "databricks_data_skew", "name": "Data skew detection",
         "description": "Detects skew in pipeline output partitions",
         "category": "performance"},
        {"id": "databricks_volume_spike", "name": "Volume spike / drop detection",
         "description": "Detects substantial deviations in record counts",
         "category": "anomaly"},
        {"id": "databricks_pii_detection", "name": "PII detection",
         "description": "Detects PII in pipeline outputs",
         "category": "governance"},
    ],
}

# Rule type mappings (used by user-defined rule books)
RULE_TYPES = [
    "null_check", "unique_check", "range_check", "regex_check", "custom_sql",
    "fk_check", "datetime_check", "row_count_check", "schema_drift_check",
    "pii_check", "truncation_check", "outlier_check", "freshness_check",
    "garbage_check", "sign_check", "misplaced_check", "trend_deviation_check",
]
