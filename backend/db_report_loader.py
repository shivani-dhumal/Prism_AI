import mysql.connector, json, os
from config import DB_CONFIG

def generate_reports():
    conn = mysql.connector.connect(**DB_CONFIG)
    cursor = conn.cursor(dictionary=True)
    os.makedirs("reports", exist_ok=True)
    
    # Fetch all table names
    table_cursor = conn.cursor()
    table_cursor.execute("SHOW TABLES")
    
    # Extract and save each table
    for (table,) in table_cursor.fetchall():
        cursor.execute(f"SELECT * FROM {table}")
        with open(f"reports/{table}.json", "w") as f:
            json.dump(cursor.fetchall(), f, indent=4, default=str)
        print(f"Created: reports/{table}.json")

if __name__ == "__main__":
    generate_reports()