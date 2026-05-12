-- =====================================================
-- DQ Sentinel: Database Schema
-- =====================================================
CREATE DATABASE IF NOT EXISTS dq_sentinel_v1
  CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
USE dq_sentinel_v1;

-- USERS
CREATE TABLE IF NOT EXISTS users (
  id INT AUTO_INCREMENT PRIMARY KEY,
  username VARCHAR(80) NOT NULL UNIQUE,
  email VARCHAR(150) NOT NULL UNIQUE,
  password_hash VARCHAR(255) NOT NULL,
  role ENUM('admin','steward','viewer') NOT NULL DEFAULT 'viewer',
  is_active TINYINT(1) NOT NULL DEFAULT 1,
  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
) ENGINE=InnoDB;

-- CONNECTORS
CREATE TABLE IF NOT EXISTS connectors (
  id INT AUTO_INCREMENT PRIMARY KEY,
  name VARCHAR(150) NOT NULL,
  type ENUM('mysql','mssql','azure','databricks','github') NOT NULL,
  config_json TEXT NOT NULL,
  status ENUM('healthy','unhealthy','unknown') NOT NULL DEFAULT 'unknown',
  last_tested_at DATETIME NULL,
  last_scanned_at DATETIME NULL,
  created_by INT NULL,
  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  UNIQUE KEY uq_connector_name (name),
  INDEX idx_connectors_type (type),
  INDEX idx_connectors_status (status)
) ENGINE=InnoDB;

-- DATASETS (tables / views / files / cloud objects)
CREATE TABLE IF NOT EXISTS datasets (
  id INT AUTO_INCREMENT PRIMARY KEY,
  connector_id INT NOT NULL,
  schema_name VARCHAR(150) NULL,
  dataset_name VARCHAR(200) NOT NULL,
  dataset_type ENUM('table','view','file','job','workflow','blob','adf','cluster','notebook') NOT NULL DEFAULT 'table',
  row_count BIGINT NULL,
  column_count INT NULL,
  contains_pii TINYINT(1) NOT NULL DEFAULT 0,
  pii_categories VARCHAR(500) NULL,
  quality_score DECIMAL(5,2) NULL,
  last_profiled_at DATETIME NULL,
  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  CONSTRAINT fk_datasets_connector FOREIGN KEY (connector_id) REFERENCES connectors(id) ON DELETE CASCADE,
  UNIQUE KEY uq_dataset (connector_id, schema_name, dataset_name),
  INDEX idx_datasets_pii (contains_pii),
  INDEX idx_datasets_score (quality_score)
) ENGINE=InnoDB;

-- COLUMNS
CREATE TABLE IF NOT EXISTS dataset_columns (
  id INT AUTO_INCREMENT PRIMARY KEY,
  dataset_id INT NOT NULL,
  column_name VARCHAR(200) NOT NULL,
  data_type VARCHAR(100) NULL,
  is_nullable TINYINT(1) NOT NULL DEFAULT 1,
  is_pii TINYINT(1) NOT NULL DEFAULT 0,
  pii_category VARCHAR(80) NULL,
  null_pct DECIMAL(5,2) NULL,
  distinct_count BIGINT NULL,
  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  CONSTRAINT fk_columns_dataset FOREIGN KEY (dataset_id) REFERENCES datasets(id) ON DELETE CASCADE,
  UNIQUE KEY uq_column (dataset_id, column_name),
  INDEX idx_columns_pii (is_pii)
) ENGINE=InnoDB;

-- SCHEMA HISTORY (for drift detection)
CREATE TABLE IF NOT EXISTS schema_history (
  id INT AUTO_INCREMENT PRIMARY KEY,
  dataset_id INT NOT NULL,
  snapshot_json TEXT NOT NULL,
  captured_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  CONSTRAINT fk_schist_dataset FOREIGN KEY (dataset_id) REFERENCES datasets(id) ON DELETE CASCADE,
  INDEX idx_schist_dataset_time (dataset_id, captured_at)
) ENGINE=InnoDB;

-- MONITORING RUNS
CREATE TABLE IF NOT EXISTS monitoring_runs (
  id INT AUTO_INCREMENT PRIMARY KEY,
  connector_id INT NULL,
  dataset_id INT NULL,
  run_type ENUM('scan','quality','schema_drift','pii','cloud') NOT NULL,
  status ENUM('running','success','failed') NOT NULL DEFAULT 'running',
  message TEXT NULL,
  metrics_json TEXT NULL,
  started_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  finished_at DATETIME NULL,
  CONSTRAINT fk_mruns_connector FOREIGN KEY (connector_id) REFERENCES connectors(id) ON DELETE CASCADE,
  CONSTRAINT fk_mruns_dataset FOREIGN KEY (dataset_id) REFERENCES datasets(id) ON DELETE CASCADE,
  INDEX idx_mruns_started (started_at),
  INDEX idx_mruns_type (run_type),
  INDEX idx_mruns_status (status)
) ENGINE=InnoDB;

-- ALERTS
CREATE TABLE IF NOT EXISTS alerts (
  id INT AUTO_INCREMENT PRIMARY KEY,
  connector_id INT NULL,
  dataset_id INT NULL,
  category ENUM('quality','schema_drift','pii','governance','pipeline','cloud','databricks') NOT NULL,
  severity ENUM('critical','high','medium','low','info') NOT NULL,
  title VARCHAR(255) NOT NULL,
  message TEXT NOT NULL,
  ai_summary TEXT NULL,
  ai_root_cause TEXT NULL,
  ai_impact TEXT NULL,
  ai_recommendation TEXT NULL,
  status ENUM('open','acknowledged','resolved') NOT NULL DEFAULT 'open',
  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  resolved_at DATETIME NULL,
  CONSTRAINT fk_alerts_connector FOREIGN KEY (connector_id) REFERENCES connectors(id) ON DELETE SET NULL,
  CONSTRAINT fk_alerts_dataset FOREIGN KEY (dataset_id) REFERENCES datasets(id) ON DELETE SET NULL,
  INDEX idx_alerts_severity (severity),
  INDEX idx_alerts_category (category),
  INDEX idx_alerts_status (status),
  INDEX idx_alerts_created (created_at)
) ENGINE=InnoDB;

-- NOTIFICATIONS (in-app)
CREATE TABLE IF NOT EXISTS notifications (
  id INT AUTO_INCREMENT PRIMARY KEY,
  user_id INT NULL,
  alert_id INT NULL,
  title VARCHAR(255) NOT NULL,
  message TEXT NULL,
  is_read TINYINT(1) NOT NULL DEFAULT 0,
  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  CONSTRAINT fk_notif_user FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
  CONSTRAINT fk_notif_alert FOREIGN KEY (alert_id) REFERENCES alerts(id) ON DELETE SET NULL,
  INDEX idx_notif_user_read (user_id, is_read),
  INDEX idx_notif_created (created_at)
) ENGINE=InnoDB;

-- MONITORING JOBS (scheduler entries)
CREATE TABLE IF NOT EXISTS monitoring_jobs (
  id INT AUTO_INCREMENT PRIMARY KEY,
  connector_id INT NOT NULL,
  job_type ENUM('scan','quality','schema_drift','pii','cloud') NOT NULL,
  interval_minutes INT NOT NULL DEFAULT 60,
  enabled TINYINT(1) NOT NULL DEFAULT 1,
  last_run_at DATETIME NULL,
  next_run_at DATETIME NULL,
  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  CONSTRAINT fk_mjobs_connector FOREIGN KEY (connector_id) REFERENCES connectors(id) ON DELETE CASCADE,
  INDEX idx_mjobs_enabled (enabled)
) ENGINE=InnoDB;

-- APP SETTINGS
CREATE TABLE IF NOT EXISTS app_settings (
  setting_key VARCHAR(120) NOT NULL PRIMARY KEY,
  setting_value TEXT NULL,
  updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
) ENGINE=InnoDB;

-- Seed admin user (password = Admin@123) — change immediately on first login
-- bcrypt hash of "Admin@123"
INSERT INTO users (username, email, password_hash, role)
VALUES (
  'admin',
  'admin@dqsentinel.local',
  '$2b$12$6a3dWLyCi8Wf4yxElP5HJOw4L7pJOOGNXnlMPbRSzVmnNyUu593gK',
  'admin'
)
ON DUPLICATE KEY UPDATE username = username;

INSERT INTO app_settings (setting_key, setting_value)
VALUES
  ('alert_email_recipients', ''),
  ('default_scan_interval_minutes', '60'),
  ('ai_enabled', '1')
ON DUPLICATE KEY UPDATE setting_key = setting_key;
