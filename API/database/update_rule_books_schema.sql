-- Update rule_books table for file upload support
-- Run this script on your MySQL database

-- Add new columns for file upload
ALTER TABLE rule_books 
ADD COLUMN IF NOT EXISTS filename VARCHAR(255) NULL AFTER description,
ADD COLUMN IF NOT EXISTS file_path TEXT NULL AFTER filename;

-- Remove old columns that are no longer needed
ALTER TABLE rule_books 
DROP COLUMN IF EXISTS dataset_type,
DROP COLUMN IF EXISTS rule_content;

-- Verify the changes
DESCRIBE rule_books;
