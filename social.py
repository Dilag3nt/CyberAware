from flask import Blueprint, jsonify, request
import logging
import tweepy
import bleach
import html
from utils import get_db_conn
from psycopg2.extras import DictCursor

social_bp = Blueprint('social', __name__)

X_API_KEY = os.getenv("X_API_KEY")
X_API_SECRET = os.getenv("X_API_SECRET")
X_ACCESS_TOKEN = os.getenv("X_ACCESS_TOKEN")
X_ACCESS_TOKEN_SECRET = os.getenv("X_ACCESS_TOKEN_SECRET")

def post_to_x():
    with get_db_conn() as conn:
        cur = conn.cursor(cursor_factory=DictCursor)
        try:
            cur.execute("SELECT COUNT(*) FROM quiz")
            row_count = cur.fetchone()[0]
            if row_count == 0:
                logging.error("No rows in quiz table for X post")
                return
            cur.execute("""
                SELECT headlines.title, headlines.source, quiz.question
                FROM headlines
                JOIN slides ON slides.headline_id = headlines.id
                JOIN quiz ON quiz.slide_id = slides.id
                WHERE quiz.created_at = (SELECT MAX(created_at) FROM quiz)
                AND quiz.question NOT LIKE 'True or False:%'
                ORDER BY RANDOM() LIMIT 1
            """)
            row = cur.fetchone()
            if not row:
                logging.error("No linked headline/quiz found for X post")
                return
            title = html.unescape(row['title'])
            source = html.unescape(row['source'])
            question = html.unescape(row['question'])
        except Exception as e:
            logging.error(f"Error during query: {e}")
            return
    text = f"🛡️ {title} ({source})\n\n❓ {question}\n\nBecome cyber-aware on dilag3nt[.]com"
    clean_text = bleach.clean(text, tags=[], strip=True)
    if len(clean_text) > 280:
        truncated = f"🛡️ {title} ({source})\n\n❓ {question}\n\nBecome cyber-aware on dilag3nt[.]com"
        clean_text = bleach.clean(truncated, tags=[], strip=True)[:280]
    logging.debug(f"X post content: {clean_text}")
    try:
        client = tweepy.Client(
            consumer_key=X_API_KEY,
            consumer_secret=X_API_SECRET,
            access_token=X_ACCESS_TOKEN,
            access_token_secret=X_ACCESS_TOKEN_SECRET
        )
        response = client.create_tweet(text=clean_text)
        logging.info(f"Posted to X: {response.data['id']}")
    except Exception as e:
        logging.error(f"Failed to post to X: {str(e)}")

@social_bp.route('/api/test_x_auth', methods=['POST'])
def test_x_auth():
    data = request.json or {}
    if data.get('secret_key') != os.getenv('MANUAL_POST_SECRET'):
        return jsonify({"error": "Unauthorized"}), 401
    try:
        client = tweepy.Client(
            consumer_key=X_API_KEY,
            consumer_secret=X_API_SECRET,
            access_token=X_ACCESS_TOKEN,
            access_token_secret=X_ACCESS_TOKEN_SECRET
        )
        user = client.get_me()
        if user.data:
            return jsonify({"success": True, "message": f"Auth works for user: {user.data.username}"})
        else:
            return jsonify({"error": "No user data returned"}), 403
    except Exception as e:
        logging.error(f"X auth test failed: {str(e)}")
        return jsonify({"error": str(e)}), 403

@social_bp.route('/api/post_to_x', methods=['POST'])
def manual_post_to_x():
    data = request.json or {}
    if data.get('secret_key') != os.getenv('MANUAL_POST_SECRET'):
        return jsonify({"error": "Unauthorized"}), 401
    post_to_x()
    return jsonify({"success": True, "message": "X post triggered manually"})