import mysql.connector
from config import DB_CONFIG

try:
    conn = mysql.connector.connect(**DB_CONFIG)
    cursor = conn.cursor(dictionary=True)
    cursor.execute("SELECT id, file_path, line_number, title, severity, status, fixed_code FROM bug_detections LIMIT 5")
    rows = cursor.fetchall()
    print("Found bug records:")
    for row in rows:
        print(row)
    cursor.close()
    conn.close()
except Exception as e:
    print(f"Error: {e}")
