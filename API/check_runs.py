
import pymysql
import os
from dotenv import load_dotenv

load_dotenv()

def check():
    conn = pymysql.connect(
        host=os.getenv("MYSQL_HOST"),
        port=int(os.getenv("MYSQL_PORT")),
        user=os.getenv("MYSQL_USER"),
        password=os.getenv("MYSQL_PASSWORD"),
        database=os.getenv("MYSQL_NAME"),
        charset="utf8mb4",
        cursorclass=pymysql.cursors.DictCursor,
    )
    cur = conn.cursor()
    
    cur.execute("""
        SELECT r.*, c.name AS connector_name, d.dataset_name 
        FROM monitoring_runs r 
        LEFT JOIN connectors c ON c.id=r.connector_id 
        LEFT JOIN datasets d ON d.id=r.dataset_id 
        ORDER BY r.started_at DESC LIMIT 5
    """)
    rows = cur.fetchall()
    for r in rows:
        print(f"Run ID: {r['id']}, Type: {r['run_type']}, Conn: {r['connector_name']}, Dataset: {r['dataset_name']}, Started: {r['started_at']}")
    conn.close()

if __name__ == "__main__":
    check()
