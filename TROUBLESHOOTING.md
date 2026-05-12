# 🆘 Troubleshooting Guide

## Common Issues & Solutions

### Issue 1: Chroma DB Not Initializing

```
Error: "Failed to initialize Chroma DB"
```

**Solution:**

```bash
# 1. Check if chroma_data directory can be created
cd API
mkdir -p chroma_data

# 2. Check permissions
ls -la chroma_data

# 3. Reinstall chromadb
pip install --upgrade chromadb

# 4. Restart API
python main.py
```

---

### Issue 2: LLM Not Working (Anthropic API)

```
Error: "ANTHROPIC_API_KEY not found"
```

**Solution:**

```bash
# 1. Get key from https://console.anthropic.com/account/keys
# 2. Add to .env
ANTHROPIC_API_KEY=sk-ant-your-key-here

# 3. Reload environment
source .env  # Linux/Mac
# or set manually for Windows

# 4. Restart API
python main.py

# 5. Quality checks will still work without LLM (fallback to basic evaluation)
```

---

### Issue 3: Rulebook Upload Fails

```
Error: "Failed to create rule book"
```

**Solution:**

```bash
# 1. Check file format (must be .txt or .md)
file mysql_rulebook.txt

# 2. Check file content
head mysql_rulebook.txt
# Should start with: "MYSQL RULE BOOK"

# 3. Check parser logs
# Look for: "Created rulebook ... with N rules"

# 4. Verify name is provided
# -F "name=MySQL Rules" required

# 5. Check database connection
curl http://127.0.0.1:8000/api/dashboard/summary
```

---

### Issue 4: Quality Check Returns Empty Score

```
Score: null or 0
No issues detected
```

**Solution:**

```bash
# 1. Verify rulebook was uploaded
curl http://127.0.0.1:8000/api/rule-books/list \
  -H "Authorization: Bearer TOKEN"

# 2. Check if rules were extracted
# Response should have "rules_created": 16

# 3. Verify Chroma DB has data
# Check: API/chroma_data/index/uuid.idx

# 4. Manually test LLM evaluation
python -c "from utils.llm_evaluator import get_llm_client; print(get_llm_client())"

# 5. Check logs for errors
# API logs should show rule fetching and LLM calls
```

---

### Issue 5: Rules Not Extracted (rules_created: 0)

```
"rules_created": 0
```

**Solution:**

```bash
# 1. Check TXT file format
# Must have numbered rules: "1. Rule Name"

# 2. Verify structure
cat mysql_rulebook.txt | grep "^[0-9]\\."
# Should show rule numbers

# 3. Check for required fields
grep -E "Purpose:|Penalty:|Rule Type:" mysql_rulebook.txt

# 4. Validate file encoding
file mysql_rulebook.txt
# Should be: ASCII text or UTF-8

# 5. Test parser manually
python -c "
from controllers.rule_book_controller import _parse_rulebook_txt
with open('mysql_rulebook.txt') as f:
    content = f.read()
    result = _parse_rulebook_txt(content)
    print(f'Rules found: {len(result[\"rules\"])}')
"
```

---

### Issue 6: Port Already in Use

```
Error: "Address already in use"
```

**Solution:**

```bash
# 1. Find process using port 8000
# Linux/Mac:
lsof -i :8000

# Windows:
netstat -ano | findstr :8000

# 2. Kill process
# Linux/Mac:
kill -9 <PID>

# Windows:
taskkill /PID <PID> /F

# 3. Restart API
python main.py
```

---

### Issue 7: Database Connection Failed

```
Error: "MySQL connection failed"
```

**Solution:**

```bash
# 1. Check .env settings
cat .env | grep DB_
# Verify: DB_HOST, DB_USER, DB_PASSWORD, DB_NAME

# 2. Test MySQL connection
mysql -h localhost -u root -p dq_sentinel_v1

# 3. Restart MySQL
# Mac:
brew services restart mysql

# Linux:
sudo systemctl restart mysql

# Windows:
# Services → Restart MySQL80

# 4. Check schema exists
mysql -u root -p -e "USE dq_sentinel_v1; SHOW TABLES;"

# 5. Run schema setup if needed
mysql -u root -p dq_sentinel_v1 < API/database/schema.sql
```

---

### Issue 8: CORS Errors in Browser

```
Error: "Access to XMLHttpRequest blocked by CORS"
```

**Solution:**

```bash
# 1. Check .env CORS_ORIGINS
cat .env | grep CORS

# 2. Should include your UI URL:
CORS_ORIGINS=http://localhost:5173,http://127.0.0.1:5173

# 3. If using different port, add it:
CORS_ORIGINS=http://localhost:3000,http://localhost:5173

# 4. Restart API
python main.py
```

---

### Issue 9: File Upload Not Working

```
Error: "Failed to read file" or "File content cannot be empty"
```

**Solution:**

```bash
# 1. Check file size (should be < 10MB)
ls -lah mysql_rulebook.txt

# 2. Check file is readable
cat mysql_rulebook.txt | head

# 3. Check MIME type
file -i mysql_rulebook.txt
# Should be: text/plain

# 4. Verify using curl
curl -X POST http://127.0.0.1:8000/api/rule-books/create \
  -H "Authorization: Bearer TOKEN" \
  -F "name=Test" \
  -F "file=@mysql_rulebook.txt" \
  -v  # verbose to see full response
```

---

### Issue 10: LLM Response Empty

```
"score": 100, "issues": [], "recommendations": []
```

**Solution:**

```bash
# 1. Check ANTHROPIC_API_KEY is valid
echo $ANTHROPIC_API_KEY

# 2. Test API key
python -c "
from anthropic import Anthropic
client = Anthropic(api_key='sk-ant-...')
print('API key valid!')
"

# 3. Check rulebook content is being fetched
# Add debug logs in monitoring_controller.py

# 4. Verify dataset metrics are being collected
# Check monitoring_runs table for metrics_json

# 5. Check API rate limits
# Anthropic API might be rate limited

# 6. Try simple test
python -c "
from utils.llm_evaluator import evaluate_quality_with_llm
result = evaluate_quality_with_llm(
    {'dataset_name': 'test', 'dataset_type': 'table'},
    {'row_count': 1000},
    'mysql'
)
print(result)
"
```

---

## Debug Logging

### Enable Debug Mode

```bash
# Add to .env
LOG_LEVEL=DEBUG

# Restart API
python main.py

# Watch logs for:
# - "Chroma DB initialized"
# - "Rulebook X added to Chroma DB"
# - "Searching for rules..."
# - "LLM evaluation..."
```

### Check Logs

```bash
# API logs (last 50 lines)
tail -50 API/api.log

# Search for errors
grep -i error API/api.log

# Search for specific rulebook
grep -i "rulebook 1" API/api.log
```

---

## Quick Diagnostics

### Test 1: API Health

```bash
curl http://127.0.0.1:8000/api/dashboard/summary
# Should return 200 with data
```

### Test 2: Chroma DB

```bash
python -c "
from utils.chroma_helper import get_chroma_db
db = get_chroma_db()
print(f'Collection: {db.name}')
print(f'Count: {db.count()}')
"
```

### Test 3: LLM Client

```bash
python -c "
from utils.llm_evaluator import get_llm_client
client = get_llm_client()
print(f'Client: {client is not None}')
"
```

### Test 4: Database

```bash
python -c "
from database.db_connection import fetch_one
result = fetch_one('SELECT COUNT(*) as count FROM rule_books')
print(f'Total rulebooks: {result[\"count\"]}')
"
```

---

## Performance Issues

### Slow Quality Checks

```bash
# 1. Check Chroma DB size
du -sh API/chroma_data/

# 2. Check API response times
curl -w "Time: %{time_total}s\n" http://127.0.0.1:8000/api/rule-books/list

# 3. Check LLM latency
# Usually takes 2-5 seconds per evaluation

# 4. Monitor resource usage
top  # or Task Manager on Windows

# 5. Optimize Chroma search
# Reduce top_k from 10 to 5 in search_rulebooks()
```

### Memory Usage

```bash
# Check API memory
ps aux | grep "python API/main.py"

# If using too much memory:
# 1. Reduce Chroma collection size
# 2. Clear old rulebooks
# 3. Restart API
```

---

## Getting Help

### Collect Diagnostic Info

```bash
# Create debug bundle
mkdir debug_info
cp .env debug_info/
cp API/api.log debug_info/ 2>/dev/null
ls -la API/chroma_data/ > debug_info/chroma_info.txt
python -c "import sys; print(sys.version)" > debug_info/python_version.txt
pip freeze > debug_info/requirements.txt

# Zip and share
tar -czf debug_info.tar.gz debug_info/
```

### Log Key Information

```
- Python version: python --version
- API version: grep version API/main.py
- Database: mysql --version
- Chroma: pip show chromadb
- Anthropic: pip show anthropic
```

---

**For more help, check the logs and follow the solutions above! 🔧**
