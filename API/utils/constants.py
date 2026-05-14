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

# Quality check definitions per connector type
QUALITY_CHECKS = {
    "mysql": [
        {"id": "mysql_null_check", "name": "Null value check", "description": "Check for NULL values in columns", "category": "completeness"},
        {"id": "mysql_duplicate_check", "name": "Duplicate record check", "description": "Check for duplicate records", "category": "uniqueness"},
        {"id": "mysql_pk_uniqueness", "name": "Primary key uniqueness", "description": "Verify primary key uniqueness", "category": "uniqueness"},
        {"id": "mysql_fk_integrity", "name": "Foreign key integrity", "description": "Check foreign key relationships", "category": "integrity"},
        {"id": "mysql_data_type", "name": "Data type validation", "description": "Validate data types match schema", "category": "validity"},
        {"id": "mysql_invalid_datetime", "name": "Invalid date/time check", "description": "Check for invalid date/time values", "category": "validity"},
        {"id": "mysql_row_count", "name": "Row count validation", "description": "Validate row count against thresholds", "category": "completeness"},
        {"id": "mysql_missing_columns", "name": "Missing mandatory columns", "description": "Check for missing required columns", "category": "completeness"},
        {"id": "mysql_referential_integrity", "name": "Referential integrity check", "description": "Verify referential integrity constraints", "category": "integrity"},
        {"id": "mysql_outlier", "name": "Outlier/anomaly detection", "description": "Detect statistical outliers in numeric data", "category": "accuracy"},
        {"id": "mysql_data_freshness", "name": "Data freshness check", "description": "Check if data is up-to-date", "category": "timeliness"},
        {"id": "mysql_schema_drift", "name": "Schema drift detection", "description": "Detect schema changes over time", "category": "consistency"},
        {"id": "mysql_pii_detection", "name": "PII/Sensitive data detection", "description": "Detect PII and sensitive data", "category": "governance"},
        {"id": "mysql_truncation", "name": "Truncation check", "description": "Check for truncated data", "category": "completeness"},
        {"id": "mysql_numeric_range", "name": "Numeric range validation", "description": "Validate numeric values are within expected ranges", "category": "validity"},
    ],
    "azure_adf": [
        {"id": "adf_pipeline_status", "name": "Pipeline execution status check", "description": "Check pipeline execution status", "category": "pipeline"},
        {"id": "adf_failed_activity", "name": "Failed activity detection", "description": "Detect failed activities in pipelines", "category": "pipeline"},
        {"id": "adf_pipeline_duration", "name": "Pipeline duration threshold", "description": "Check pipeline duration against thresholds", "category": "performance"},
        {"id": "adf_trigger_failure", "name": "Trigger failure monitoring", "description": "Monitor trigger failures", "category": "pipeline"},
        {"id": "adf_dataset_existence", "name": "Dataset existence validation", "description": "Validate dataset existence", "category": "validity"},
        {"id": "adf_linked_service", "name": "Linked service connectivity check", "description": "Check linked service connectivity", "category": "connectivity"},
        {"id": "adf_parameter_validation", "name": "Parameter validation", "description": "Validate pipeline parameters", "category": "validity"},
        {"id": "adf_schema_drift", "name": "Schema drift detection", "description": "Detect schema drift in data flows", "category": "consistency"},
        {"id": "adf_row_count", "name": "Source-to-target row count validation", "description": "Validate row counts between source and target", "category": "completeness"},
        {"id": "adf_late_execution", "name": "Late pipeline execution detection", "description": "Detect late pipeline executions", "category": "timeliness"},
        {"id": "adf_retry_count", "name": "Retry count monitoring", "description": "Monitor activity retry counts", "category": "pipeline"},
        {"id": "adf_data_freshness", "name": "Data freshness validation", "description": "Validate data freshness", "category": "timeliness"},
        {"id": "adf_dependency_failure", "name": "Dependency failure tracking", "description": "Track pipeline dependency failures", "category": "pipeline"},
        {"id": "adf_missing_file", "name": "Missing file detection", "description": "Detect missing input files", "category": "completeness"},
        {"id": "adf_incremental_load", "name": "Incremental load validation", "description": "Validate incremental load processes", "category": "completeness"},
    ],
    "databricks": [
        {"id": "databricks_delta_schema", "name": "Delta table schema validation", "description": "Validate Delta table schema", "category": "consistency"},
        {"id": "databricks_null_duplicate", "name": "Null/duplicate record detection", "description": "Detect null and duplicate records", "category": "completeness"},
        {"id": "databricks_job_failure", "name": "Job failure monitoring", "description": "Monitor job failures", "category": "pipeline"},
        {"id": "databricks_cluster_health", "name": "Cluster health monitoring", "description": "Monitor cluster health", "category": "infrastructure"},
        {"id": "databricks_notebook_status", "name": "Notebook execution status", "description": "Check notebook execution status", "category": "pipeline"},
        {"id": "databricks_delta_freshness", "name": "Delta freshness check", "description": "Check Delta table freshness", "category": "timeliness"},
        {"id": "databricks_partition_consistency", "name": "Partition consistency validation", "description": "Validate partition consistency", "category": "consistency"},
        {"id": "databricks_streaming_lag", "name": "Streaming lag monitoring", "description": "Monitor streaming lag", "category": "performance"},
        {"id": "databricks_data_completeness", "name": "Data completeness check", "description": "Check data completeness", "category": "completeness"},
        {"id": "databricks_file_ingestion", "name": "File ingestion validation", "description": "Validate file ingestion", "category": "completeness"},
        {"id": "databricks_orphan_table", "name": "Orphan table detection", "description": "Detect orphan tables", "category": "governance"},
        {"id": "databricks_data_skew", "name": "Data skew detection", "description": "Detect data skew", "category": "performance"},
        {"id": "databricks_volume_spike", "name": "Volume spike/drop detection", "description": "Detect volume spikes and drops", "category": "anomaly"},
        {"id": "databricks_pii_detection", "name": "PII detection", "description": "Detect PII data", "category": "governance"},
        {"id": "databricks_unity_permission", "name": "Unity Catalog permission validation", "description": "Validate Unity Catalog permissions", "category": "governance"},
    ]
}

# Rule type mappings
RULE_TYPES = [
    "null_check", "unique_check", "range_check", "regex_check", "custom_sql",
    "fk_check", "datetime_check", "row_count_check", "schema_drift_check",
    "pii_check", "truncation_check", "outlier_check", "freshness_check"
]

