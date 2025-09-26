import logging
import psycopg2
from utils import get_db_conn

def init_db():
    try:
        with get_db_conn() as conn:
            cur = conn.cursor()
            cur.execute('''CREATE TABLE IF NOT EXISTS headlines
                           (id SERIAL PRIMARY KEY, title TEXT, description TEXT, link TEXT, timestamp TIMESTAMP WITH TIME ZONE, source TEXT, published_date TIMESTAMP WITH TIME ZONE, hash TEXT)''')
            cur.execute('''CREATE TABLE IF NOT EXISTS slides
                           (id SERIAL PRIMARY KEY, title TEXT, content TEXT, headline_id INTEGER REFERENCES headlines(id), created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP)''')
            cur.execute('''CREATE TABLE IF NOT EXISTS quiz
                           (id SERIAL PRIMARY KEY, question TEXT, options TEXT, correct INTEGER, explanation TEXT, created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP, slide_id INTEGER REFERENCES slides(id))''')
            cur.execute('''CREATE TABLE IF NOT EXISTS users
                           (id SERIAL PRIMARY KEY, social_id TEXT NOT NULL, provider TEXT NOT NULL,
                            username TEXT UNIQUE NOT NULL, bio TEXT, domain TEXT, join_team BOOLEAN DEFAULT FALSE, join_public BOOLEAN DEFAULT FALSE,
                            CONSTRAINT unique_social UNIQUE (social_id, provider))''')
            cur.execute('''CREATE TABLE IF NOT EXISTS scores
                           (id SERIAL PRIMARY KEY, user_id INTEGER, quiz_id INTEGER, score INTEGER,
                            completed_at TIMESTAMP WITH TIME ZONE, FOREIGN KEY (user_id) REFERENCES users(id),
                            FOREIGN KEY (quiz_id) REFERENCES quiz(id))''')
            cur.execute('''CREATE TABLE IF NOT EXISTS user_totals
                           (id SERIAL PRIMARY KEY, user_id INTEGER UNIQUE, total_score INTEGER DEFAULT 0, perfect_quizzes INTEGER DEFAULT 0,
                            last_quiz TIMESTAMP WITH TIME ZONE, quizzes_taken INTEGER DEFAULT 0, FOREIGN KEY (user_id) REFERENCES users(id))''')
            cur.execute('''CREATE TABLE IF NOT EXISTS quiz_counts
                           (id SERIAL PRIMARY KEY, count INTEGER DEFAULT 0)''')
            cur.execute("SELECT COUNT(*) FROM quiz_counts")
            if cur.fetchone()[0] == 0:
                cur.execute("INSERT INTO quiz_counts (id, count) VALUES (1, 0)")
            cur.execute("""
                SELECT column_name
                FROM information_schema.columns
                WHERE table_name = 'quiz' AND column_name = 'created_at'
            """)
            if not cur.fetchone():
                cur.execute("""
                    ALTER TABLE quiz
                    ADD COLUMN created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
                """)
                cur.execute("""
                    UPDATE quiz
                    SET created_at = CURRENT_TIMESTAMP
                    WHERE created_at IS NULL
                """)
            cur.execute("""
                SELECT column_name
                FROM information_schema.columns
                WHERE table_name = 'slides' AND column_name = 'headline_id'
            """)
            if not cur.fetchone():
                cur.execute("ALTER TABLE slides ADD COLUMN headline_id INTEGER REFERENCES headlines(id)")
            cur.execute("""
                SELECT column_name
                FROM information_schema.columns
                WHERE table_name = 'quiz' AND column_name = 'slide_id'
            """)
            if not cur.fetchone():
                cur.execute("ALTER TABLE quiz ADD COLUMN slide_id INTEGER REFERENCES slides(id)")
            cur.execute("""
                SELECT column_name
                FROM information_schema.columns
                WHERE table_name = 'slides' AND column_name = 'created_at'
            """)
            if not cur.fetchone():
                cur.execute("""
                    ALTER TABLE slides
                    ADD COLUMN created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
                """)
                cur.execute("""
                    UPDATE slides
                    SET created_at = CURRENT_TIMESTAMP
                    WHERE created_at IS NULL
                """)
            cur.execute("""
                SELECT column_name
                FROM information_schema.columns
                WHERE table_name = 'users' AND column_name = 'domain'
            """)
            if not cur.fetchone():
                cur.execute("ALTER TABLE users ADD COLUMN domain TEXT")
            cur.execute("""
                SELECT column_name
                FROM information_schema.columns
                WHERE table_name = 'users' AND column_name = 'join_team'
            """)
            if not cur.fetchone():
                cur.execute("ALTER TABLE users ADD COLUMN join_team BOOLEAN DEFAULT FALSE")
            cur.execute("""
                SELECT column_name
                FROM information_schema.columns
                WHERE table_name = 'users' AND column_name = 'join_public'
            """)
            if not cur.fetchone():
                cur.execute("ALTER TABLE users ADD COLUMN join_public BOOLEAN DEFAULT FALSE")
            cur.execute("""
                SELECT column_name
                FROM information_schema.columns
                WHERE table_name = 'headlines' AND column_name = 'published_date'
            """)
            if not cur.fetchone():
                cur.execute("ALTER TABLE headlines ADD COLUMN published_date TIMESTAMP WITH TIME ZONE")
            cur.execute("""
                SELECT column_name
                FROM information_schema.columns
                WHERE table_name = 'headlines' AND column_name = 'hash'
            """)
            if not cur.fetchone():
                cur.execute("ALTER TABLE headlines ADD COLUMN hash TEXT")
            conn.commit()
            logging.info("Database tables initialized successfully")
    except psycopg2.Error as e:
        logging.error(f"Failed to initialize or migrate database: {e}")
        raise