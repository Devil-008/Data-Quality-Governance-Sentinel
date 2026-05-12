# 🚀 Updated Architecture - Chroma DB + LLM Integration

## ✅ What's Changed

### 1. **UI Changes (RuleBooks.jsx)**

- ✅ Removed `Dataset Type` field from upload form
- ✅ Removed `Rule Content` text field from form
- ✅ Now only requires: Name, Description, Connector Type (optional), File upload
- ✅ Changed title from "Add Rule Book" to "Upload Rule Book"
- ✅ Updated file input to accept only .txt and .md files

### 2. **Backend API Changes**

#### Rulebook Controller (`rule_book_controller.py`)

- ✅ Removed `dataset_type` parameter from `/create` endpoint
- ✅ Removed `rule_content` from form parameters (stored in DB automatically)
- ✅ Added automatic parser `_parse_rulebook_txt()` to extract rules from TXT files
- ✅ Integrated Chroma DB storage for vector embeddings
- ✅ Rules are automatically extracted and stored in `dataset_validation_rules` table
- ✅ Rulebook content stored in Chroma vector DB for semantic search

#### API Endpoint: `POST /api/rule-books/create`

```python
# OLD (removed):
dataset_type  # No longer needed
rule_content  # No longer in form params (file-based now)

# NEW (required):
name          # Rule book name
file          # TXT file upload (required)
description   # Optional
connector_type# Optional (mysql, azure_adf, databricks, etc.)
```

### 3. **Database Storage**

#### rule_books TABLE (unchanged structure)

```sql
- id           → Auto-generated
- name         → "MySQL Data Quality Rule Book"
- description  → Description text
- rule_content → Entire TXT file content (stored as-is)
- connector_type → "mysql", "azure_adf", "databricks"
- dataset_type → REMOVED (no longer used)
- created_by   → User ID
- created_at   → Timestamp
```

#### Chroma Vector DB (NEW)

```
Collection: "rulebooks"
- id: rulebook_{id}
- documents: Extracted rules text
- metadata:
  - rulebook_id
  - rulebook_name
  - connector_type
  - type: "rulebook"
```

### 4. **Chroma DB Integration**

New file: `API/utils/chroma_helper.py`

- `init_chroma()` - Initialize Chroma DB on startup
- `add_rulebook_to_chroma()` - Store rulebook in vector DB
- `search_rulebooks()` - Semantic search for applicable rules
- `get_rulebook_content()` - Retrieve full rulebook
- `delete_rulebook_from_chroma()` - Delete from vector DB

### 5. **LLM-Based Quality Evaluation**

New file: `API/utils/llm_evaluator.py`

- `evaluate_quality_with_llm()` - Use Claude AI to evaluate quality based on rules
- `evaluate_pii_with_llm()` - Use LLM for PII detection
- `fetch_applicable_rules()` - Get rules from Chroma for dataset

## 🔄 Quality Check Workflow (Updated)

```
Dataset Quality Check Triggered
         ↓
Fetch Dataset Info (name, type, connector)
         ↓
Search Chroma DB for applicable rules
  └─ Query: "Quality check rules for mysql"
  └─ Filter: connector_type = "mysql"
         ↓
Fetch LLM (Claude API)
  └─ Provide: Dataset info + rules + metrics
  └─ Ask: "Evaluate quality based on rules"
         ↓
LLM Returns:
  - Quality Score (0-100)
  - Issues found
  - Recommendations
         ↓
Store Results in Database
  - Update datasets.quality_score
  - Create monitoring_runs entry
  - Generate alerts if score < threshold
         ↓
Display in UI Dashboard
```

## 📋 Updated Workflow Example

### Upload MySQL Rulebook

```bash
POST /api/rule-books/create
Content-Type: multipart/form-data

Parameters:
- name: "MySQL Data Quality Rule Book"
- description: "Quality rules for MySQL databases"
- connector_type: "mysql"
- file: [mysql_rulebook.txt]

# Note: dataset_type and rule_content are NOT in form anymore
```

### Run Quality Check on Dataset

```bash
POST /api/monitoring/quality-check-all/{connector_id}

Workflow:
1. Fetch all datasets for connector
2. For each dataset:
   a. Get connector type (mysql, azure_adf, etc.)
   b. Search Chroma: "Quality check rules for mysql"
   c. Call LLM with:
      - Dataset info (name, schema, row_count, columns)
      - Dataset metrics (NULL%, duplicates, etc.)
      - Applicable rules (from Chroma)
   d. Get score + issues from LLM
   e. Store in database
   f. Create alerts if needed
```

## 🔌 Configuration (.env)

```bash
# Optional: Custom Chroma DB path
CHROMA_DB_PATH=./chroma_data

# For LLM evaluation
ANTHROPIC_API_KEY=sk-ant-...
```

## 🎯 Benefits of New Architecture

| Aspect             | Old                   | New                                   |
| ------------------ | --------------------- | ------------------------------------- |
| Rule Storage       | Hardcoded in code     | Text file + Chroma vector DB          |
| Rule Search        | Manual filtering      | Semantic search in Chroma             |
| Quality Evaluation | Hardcoded logic       | LLM-based intelligent evaluation      |
| Extensibility      | Requires code changes | Upload new rulebooks anytime          |
| PII Detection      | Pattern matching      | LLM-based comprehensive detection     |
| User Control       | Admin only            | Any authorized user uploads rulebooks |
| Scalability        | Limited (hardcoded)   | Unlimited rulebooks                   |

## 📚 Files Modified

| File                                      | Changes                                                               |
| ----------------------------------------- | --------------------------------------------------------------------- |
| `API/controllers/rule_book_controller.py` | ✅ Removed dataset_type/rule_content params, added Chroma integration |
| `API/main.py`                             | ✅ Added Chroma DB initialization                                     |
| `UI/src/pages/RuleBooks/RuleBooks.jsx`    | ✅ Removed form fields, kept only file upload                         |
| `API/requirements.txt`                    | ✅ chromadb, sentence-transformers already included                   |

## 📝 Files Created

| File                         | Purpose                      |
| ---------------------------- | ---------------------------- |
| `API/utils/chroma_helper.py` | Chroma vector DB integration |
| `API/utils/llm_evaluator.py` | LLM-based rule evaluation    |

## ✅ Next Steps

1. **Restart API Server**

   ```bash
   cd API
   python main.py
   ```

2. **Upload Rulebooks via UI**
   - Go to Settings → Rule Books
   - Click "Add Rule Book"
   - Upload TXT files (only Name, Description, Connector Type, File now)
   - Rules auto-extracted and stored in Chroma

3. **Run Quality Checks**
   - Go to Datasets
   - Click "Run Quality Check"
   - LLM fetches rules from Chroma
   - Evaluates based on rulebook logic
   - Returns quality score + PII info

4. **Monitor Results**
   - Dashboard shows quality scores
   - Alerts created for issues
   - Historical trends tracked

## 🔍 Testing the New Flow

```bash
# 1. Upload rulebook
curl -X POST http://127.0.0.1:8000/api/rule-books/create \
  -H "Authorization: Bearer TOKEN" \
  -F "file=@mysql_rulebook.txt" \
  -F "name=MySQL Rules" \
  -F "connector_type=mysql"

# 2. List rulebooks
curl http://127.0.0.1:8000/api/rule-books/list \
  -H "Authorization: Bearer TOKEN"

# 3. Run quality check
curl -X POST http://127.0.0.1:8000/api/monitoring/quality-check-all/1 \
  -H "Authorization: Bearer TOKEN"
```

## 🚨 Important Notes

⚠️ **Chroma DB Path**: By default stores at `./chroma_data` in API directory

⚠️ **LLM API Key**: Requires `ANTHROPIC_API_KEY` env var for LLM evaluation

⚠️ **Backward Compatibility**: Old endpoint still works but ignores dataset_type param

⚠️ **Rule Extraction**: Parser looks for numbered rules (1., 2., 3., etc.) in TXT files

---

**Ready to test? Upload your first rulebook! 🚀**
