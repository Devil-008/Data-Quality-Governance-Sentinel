-- =====================================================
-- DQ Sentinel: Seed Default Rule Books
-- =====================================================
USE dq_sentinel_v1;

-- MySQL Rule Book
INSERT INTO rule_books (name, description, rule_content, connector_type, created_by, created_at)
VALUES (
    'MySQL Standard Quality Checks',
    'Comprehensive quality checks for MySQL databases including null checks, duplicates, PK/FK integrity, and more',
    'MySQL quality checks including 16 standard validation rules',
    'mysql',
    1,
    NOW()
);

SET @mysql_rule_book_id = LAST_INSERT_ID();

-- MySQL Rules
INSERT INTO dataset_validation_rules (rule_book_id, rule_name, rule_type, rule_config, is_active, created_at) VALUES
(@mysql_rule_book_id, 'Null Value Check', 'null_check', '{"max_nulls": 0}', 1, NOW()),
(@mysql_rule_book_id, 'Duplicate Record Check', 'unique_check', '{}', 1, NOW()),
(@mysql_rule_book_id, 'Primary Key Uniqueness', 'custom_sql', '{"sql": "SELECT COUNT(*) - COUNT(DISTINCT {{pk_columns}}) AS duplicates FROM {{table}}"}', 1, NOW()),
(@mysql_rule_book_id, 'Foreign Key Integrity', 'custom_sql', '{"sql": "SELECT COUNT(*) AS orphaned FROM {{table}} t LEFT JOIN {{ref_table}} r ON t.{{fk_column}} = r.{{ref_column}} WHERE t.{{fk_column}} IS NOT NULL AND r.{{ref_column}} IS NULL"}', 1, NOW()),
(@mysql_rule_book_id, 'Data Type Validation', 'custom_sql', '{}', 1, NOW()),
(@mysql_rule_book_id, 'Invalid Date/Time Check', 'custom_sql', '{"sql": "SELECT COUNT(*) AS invalid FROM {{table}} WHERE {{date_column}} < ''1900-01-01'' OR {{date_column}} > ''2100-12-31''"}', 1, NOW()),
(@mysql_rule_book_id, 'Row Count Validation', 'row_count_check', '{"min_rows": 1}', 1, NOW()),
(@mysql_rule_book_id, 'Missing Mandatory Columns', 'custom_sql', '{}', 1, NOW()),
(@mysql_rule_book_id, 'Referential Integrity Check', 'custom_sql', '{}', 1, NOW()),
(@mysql_rule_book_id, 'Outlier/Anomaly Detection', 'custom_sql', '{}', 1, NOW()),
(@mysql_rule_book_id, 'Data Freshness Check', 'freshness_check', '{"max_days_old": 7}', 1, NOW()),
(@mysql_rule_book_id, 'Schema Drift Detection', 'schema_drift_check', '{}', 1, NOW()),
(@mysql_rule_book_id, 'PII/Sensitive Data Detection', 'pii_check', '{}', 1, NOW()),
(@mysql_rule_book_id, 'Truncation Check', 'custom_sql', '{"sql": "SELECT COUNT(*) AS truncated FROM {{table}} WHERE CHAR_LENGTH({{string_column}}) = CHARACTER_MAXIMUM_LENGTH"}', 1, NOW()),
(@mysql_rule_book_id, 'Numeric Range Validation', 'range_check', '{}', 1, NOW());

-- Azure Data Factory Rule Book
INSERT INTO rule_books (name, description, rule_content, connector_type, created_by, created_at)
VALUES (
    'ADF Standard Quality Checks',
    'Comprehensive quality checks for Azure Data Factory including pipeline status, triggers, linked services, and more',
    'Azure Data Factory quality checks including 15 standard monitoring rules',
    'azure_adf',
    1,
    NOW()
);

SET @adf_rule_book_id = LAST_INSERT_ID();

-- ADF Rules
INSERT INTO dataset_validation_rules (rule_book_id, rule_name, rule_type, rule_config, is_active, created_at) VALUES
(@adf_rule_book_id, 'Pipeline Execution Status Check', 'custom_sql', '{}', 1, NOW()),
(@adf_rule_book_id, 'Failed Activity Detection', 'custom_sql', '{}', 1, NOW()),
(@adf_rule_book_id, 'Pipeline Duration Threshold', 'custom_sql', '{"max_duration_minutes": 60}', 1, NOW()),
(@adf_rule_book_id, 'Trigger Failure Monitoring', 'custom_sql', '{}', 1, NOW()),
(@adf_rule_book_id, 'Dataset Existence Validation', 'custom_sql', '{}', 1, NOW()),
(@adf_rule_book_id, 'Linked Service Connectivity Check', 'custom_sql', '{}', 1, NOW()),
(@adf_rule_book_id, 'Parameter Validation', 'custom_sql', '{}', 1, NOW()),
(@adf_rule_book_id, 'Schema Drift Detection', 'schema_drift_check', '{}', 1, NOW()),
(@adf_rule_book_id, 'Source-to-Target Row Count Validation', 'row_count_check', '{}', 1, NOW()),
(@adf_rule_book_id, 'Late Pipeline Execution Detection', 'custom_sql', '{"max_late_minutes": 30}', 1, NOW()),
(@adf_rule_book_id, 'Retry Count Monitoring', 'custom_sql', '{"max_retries": 3}', 1, NOW()),
(@adf_rule_book_id, 'Data Freshness Validation', 'freshness_check', '{"max_days_old": 1}', 1, NOW()),
(@adf_rule_book_id, 'Dependency Failure Tracking', 'custom_sql', '{}', 1, NOW()),
(@adf_rule_book_id, 'Missing File Detection', 'custom_sql', '{}', 1, NOW()),
(@adf_rule_book_id, 'Incremental Load Validation', 'custom_sql', '{}', 1, NOW());

-- Databricks Rule Book
INSERT INTO rule_books (name, description, rule_content, connector_type, created_by, created_at)
VALUES (
    'Databricks Standard Quality Checks',
    'Comprehensive quality checks for Databricks including Delta tables, jobs, clusters, and more',
    'Databricks quality checks including 15 standard validation rules',
    'databricks',
    1,
    NOW()
);

SET @databricks_rule_book_id = LAST_INSERT_ID();

-- Databricks Rules
INSERT INTO dataset_validation_rules (rule_book_id, rule_name, rule_type, rule_config, is_active, created_at) VALUES
(@databricks_rule_book_id, 'Delta Table Schema Validation', 'schema_drift_check', '{}', 1, NOW()),
(@databricks_rule_book_id, 'Null/Duplicate Record Detection', 'null_check', '{}', 1, NOW()),
(@databricks_rule_book_id, 'Job Failure Monitoring', 'custom_sql', '{}', 1, NOW()),
(@databricks_rule_book_id, 'Cluster Health Monitoring', 'custom_sql', '{}', 1, NOW()),
(@databricks_rule_book_id, 'Notebook Execution Status', 'custom_sql', '{}', 1, NOW()),
(@databricks_rule_book_id, 'Delta Freshness Check', 'freshness_check', '{"max_days_old": 1}', 1, NOW()),
(@databricks_rule_book_id, 'Partition Consistency Validation', 'custom_sql', '{}', 1, NOW()),
(@databricks_rule_book_id, 'Streaming Lag Monitoring', 'custom_sql', '{"max_lag_seconds": 300}', 1, NOW()),
(@databricks_rule_book_id, 'Data Completeness Check', 'null_check', '{}', 1, NOW()),
(@databricks_rule_book_id, 'File Ingestion Validation', 'custom_sql', '{}', 1, NOW()),
(@databricks_rule_book_id, 'Orphan Table Detection', 'custom_sql', '{}', 1, NOW()),
(@databricks_rule_book_id, 'Data Skew Detection', 'custom_sql', '{}', 1, NOW()),
(@databricks_rule_book_id, 'Volume Spike/Drop Detection', 'custom_sql', '{"threshold_percent": 50}', 1, NOW()),
(@databricks_rule_book_id, 'PII Detection', 'pii_check', '{}', 1, NOW()),
(@databricks_rule_book_id, 'Unity Catalog Permission Validation', 'custom_sql', '{}', 1, NOW());

SELECT 'Rule books seeded successfully!' AS message;
SELECT 
    rb.name AS rule_book_name,
    rb.connector_type,
    COUNT(dvr.id) AS rule_count
FROM rule_books rb
LEFT JOIN dataset_validation_rules dvr ON rb.id = dvr.rule_book_id
GROUP BY rb.id, rb.name, rb.connector_type;
