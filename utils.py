import os
import logging
import psycopg2
from utils import get_db_conn

def get_db_conn():
    import os
    from dotenv import load_dotenv
    load_dotenv()
    try:
        return psycopg2.connect(os.getenv('DATABASE_URL'), sslmode='require')
    except psycopg2.Error as e:
        logging.error(f"Failed to connect to database: {e}")
        raise

def generate_username():
    with get_db_conn() as conn:
        cur = conn.cursor()
        cur.execute("SELECT MAX(CAST(SUBSTR(username, 7) AS INTEGER)) FROM users WHERE username LIKE 'cyb3r_%'")
        max_suffix = cur.fetchone()[0]
        suffix = (max_suffix or 0) + 1
        return f"cyb3r_{suffix}"

def load_quiz_count():
    with get_db_conn() as conn:
        cur = conn.cursor()
        cur.execute("SELECT count FROM quiz_counts WHERE id = 1")
        result = cur.fetchone()
        return result[0] if result else 0

def save_quiz_count(count):
    with get_db_conn() as conn:
        cur = conn.cursor()
        cur.execute("UPDATE quiz_counts SET count = %s WHERE id = 1", (count,))
        conn.commit()