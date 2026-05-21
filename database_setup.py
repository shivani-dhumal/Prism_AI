# database_setup.py

import mysql.connector
from config import DB_CONFIG


def create_tables():

    # -------- STEP 1: CREATE DATABASE --------
    init_config = DB_CONFIG.copy()
    target_db_name = init_config.pop("database")

    conn = mysql.connector.connect(**init_config)
    cursor = conn.cursor()

    print(f"Creating database '{target_db_name}' if it does not exist...")
    cursor.execute(f"CREATE DATABASE IF NOT EXISTS {target_db_name}")

    cursor.close()
    conn.close()

    # STEP 2: CONNECT TO TARGET DATABASE 
    conn = mysql.connector.connect(**DB_CONFIG)
    cursor = conn.cursor()

    # -------- SCANS TABLE (Web Dashboard) --------
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS scans (
        id INT AUTO_INCREMENT PRIMARY KEY,
        scan_name VARCHAR(255),
        target_directory TEXT,
        status ENUM('RUNNING','COMPLETED','FAILED') DEFAULT 'RUNNING',
        current_stage VARCHAR(100) DEFAULT 'Starting',
        progress INT DEFAULT 0,
        message TEXT,
        total_files INT DEFAULT 0,
        scanned_files INT DEFAULT 0,
        total_issues INT DEFAULT 0,
        high_count INT DEFAULT 0,
        medium_count INT DEFAULT 0,
        low_count INT DEFAULT 0,
        started_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        completed_at TIMESTAMP NULL,
        error_message TEXT
    )
    """)

    # -------- CORE TABLES --------
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS folders (
        id INT AUTO_INCREMENT PRIMARY KEY,
        folder_name VARCHAR(255),
        folder_path TEXT
    )
    """)

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS files (
        id INT AUTO_INCREMENT PRIMARY KEY,
        folder_id INT,
        file_name VARCHAR(255),
        file_path TEXT,
        extension VARCHAR(50),
        FOREIGN KEY (folder_id) REFERENCES folders(id) ON DELETE CASCADE
    )
    """)

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS components (
        id INT AUTO_INCREMENT PRIMARY KEY,
        file_id INT,
        component_name VARCHAR(255),
        FOREIGN KEY (file_id) REFERENCES files(id) ON DELETE CASCADE
    )
    """)

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS ui_elements (
        id INT AUTO_INCREMENT PRIMARY KEY,
        component_id INT,
        tag_name VARCHAR(100),
        action_type VARCHAR(100),
        action_handler VARCHAR(255),
        FOREIGN KEY (component_id) REFERENCES components(id) ON DELETE CASCADE
    )
    """)

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS component_complexity (
        id INT AUTO_INCREMENT PRIMARY KEY,
        component_id INT,
        totallines INT,
        methods INT,
        computed INT,
        watchers INT,
        template_lines INT,
        child_components INT,
        flags TEXT,
        FOREIGN KEY (component_id) REFERENCES components(id) ON DELETE CASCADE
    )
    """)

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS apis (
        id INT AUTO_INCREMENT PRIMARY KEY,
        file_id INT,
        method VARCHAR(10),
        url VARCHAR(255),
        payload TEXT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (file_id) REFERENCES files(id) ON DELETE CASCADE
    )
    """)

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS ui_extraction (
        id INT AUTO_INCREMENT PRIMARY KEY,
        component_id INT,
        file_path TEXT,
        tag_name VARCHAR(50),
        text_value TEXT,
        css_class VARCHAR(255),
        div_id VARCHAR(255),
        line_number VARCHAR(50) ,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (component_id) REFERENCES components(id) ON DELETE CASCADE
    )
    """)

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS file_flags (
        id INT AUTO_INCREMENT PRIMARY KEY,
        file_id INT,
        api_count INT DEFAULT 0,
        payload_keys_max INT DEFAULT 0,
        loc INT DEFAULT 0,
        api_flags TEXT,
        payload_flags TEXT,
        complexity_flags TEXT,
        risk_flags TEXT,
        pattern_flags TEXT,
        ui_flags TEXT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (file_id) REFERENCES files(id) ON DELETE CASCADE
    )
    """)

    # TASK-5 TABLE (Unified) 
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS ui_consistency_report (
        id INT AUTO_INCREMENT PRIMARY KEY,
        component_id INT,
        file_path TEXT,
        rule_name VARCHAR(255),
        status VARCHAR(10),
        actual_result TEXT,
        severity VARCHAR(20),
        recommendation TEXT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        line_number VARCHAR(50) DEFAULT '0-0',
        FOREIGN KEY (component_id) REFERENCES components(id) ON DELETE CASCADE
    )
    """)

    # TASK-6 TABLE (Accessibility & Usability)
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS accessibility_report (
        id INT AUTO_INCREMENT PRIMARY KEY,
        component_id INT,
        file_path TEXT,
        rule_name VARCHAR(255),
        status VARCHAR(10),
        actual_result TEXT,
        severity VARCHAR(20),
        line_number VARCHAR(50) DEFAULT '0-0',
        FOREIGN KEY (component_id) REFERENCES components(id) ON DELETE CASCADE
    )
    """)

   

    # COMPONENT METHODS TABLE
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS component_methods (
        id INT AUTO_INCREMENT PRIMARY KEY,
        component_id INT,
        method_name VARCHAR(255),
        method_lines VARCHAR(50),
        total_lines INT,
        FOREIGN KEY (component_id) REFERENCES components(id) ON DELETE CASCADE
    )
    """)

    # CODE METRICS TABLE (dynamic static-code analysis)
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS code_metrics (
        id INT AUTO_INCREMENT PRIMARY KEY,
        file_id INT,
        file_name VARCHAR(255),
        file_path TEXT,
        extension VARCHAR(50),
        total_lines INT DEFAULT 0,
        code_lines INT DEFAULT 0,
        blank_lines INT DEFAULT 0,
        comment_lines INT DEFAULT 0,
        code_ratio DECIMAL(5,1) DEFAULT 0.0,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (file_id) REFERENCES files(id) ON DELETE CASCADE
    )
    """)

    # BUG DETECTIONS TABLE (Gemini-powered deep bug analysis)
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS bug_detections (
        id INT AUTO_INCREMENT PRIMARY KEY,
        file_id INT,
        file_name VARCHAR(255),
        file_path TEXT,
        bug_category VARCHAR(50),
        title VARCHAR(500),
        severity VARCHAR(20),
        line_number INT DEFAULT 0,
        description TEXT,
        fix_suggestion TEXT,
        confidence DECIMAL(3,2) DEFAULT 0.50,
        status ENUM('OPEN','FIXED','IGNORED') DEFAULT 'OPEN',
        fixed_code TEXT DEFAULT NULL,
        status_updated_at TIMESTAMP NULL,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (file_id) REFERENCES files(id) ON DELETE CASCADE
    )
    """)

    # Add status columns if they don't exist (for existing databases)
    for col, definition in [
        ("status", "ENUM('OPEN','FIXED','IGNORED') DEFAULT 'OPEN'"),
        ("fixed_code", "TEXT DEFAULT NULL"),
        ("status_updated_at", "TIMESTAMP NULL"),
    ]:
        try:
            cursor.execute(f"ALTER TABLE bug_detections ADD COLUMN {col} {definition}")
        except Exception:
            pass  # Column already exists

    conn.commit()
    cursor.close()
    conn.close()

    print("Database and tables created successfully.")


if __name__ == "__main__":
    create_tables()