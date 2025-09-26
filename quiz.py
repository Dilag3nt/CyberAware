import logging
import json
from flask import Blueprint, jsonify, request, session
from datetime import datetime, timezone
from utils import get_db_conn
from psycopg2.extras import DictCursor

quiz_bp = Blueprint('quiz', __name__)

@quiz_bp.route('/api/quiz', methods=['GET'])
def get_quiz():
    try:
        with get_db_conn() as conn:
            cur = conn.cursor(cursor_factory=DictCursor)
            cur.execute("""
                SELECT id, question, options, correct, explanation
                FROM quiz
                ORDER BY created_at DESC
                LIMIT 5
            """)
            quiz = [{"id": row['id'], "question": row['question'], "options": json.loads(row['options']), "correct": row['correct'], "explanation": row['explanation']} for row in cur.fetchall()]
            logging.debug(f"Serving quiz: {quiz}")
            return jsonify(quiz)
    except Exception as e:
        logging.error(f"Error in /api/quiz: {e}")
        return jsonify({"error": "Failed to load quiz questions"}), 500

@quiz_bp.route('/api/submit_quiz/<int:quiz_id>', methods=['POST'])
def submit_quiz(quiz_id):
    user = session.get('user')
    data = request.get_json()
    score = data.get('score', 0)
    if not isinstance(score, int) or score < 0 or score > 100:
        logging.error(f"Invalid score {score} for quiz {quiz_id} by user {user['username'] if user else 'anonymous'}")
        return jsonify({"error": "Invalid score", "message": "Error: Invalid score provided."}), 400
    if not user:
        logging.debug(f"Anonymous user attempted to submit quiz {quiz_id}")
        return jsonify({"success": True, "saved": False, "message": "Sign in to save your score for the leaderboard!"}), 200
    with get_db_conn() as conn:
        cur = conn.cursor(cursor_factory=DictCursor)
        cur.execute("SELECT MAX(timestamp) as latest_timestamp FROM headlines")
        latest_headline = cur.fetchone()
        latest_timestamp = latest_headline['latest_timestamp'] if latest_headline and latest_headline['latest_timestamp'] else datetime.now(timezone.utc)
        cur.execute("""
            SELECT COUNT(*) as count
            FROM scores
            WHERE user_id = %s AND completed_at >= %s
        """, (user['id'], latest_timestamp))
        result = cur.fetchone()
        if result['count'] > 0:
            logging.debug(f"User {user['username']} already submitted a score since latest headline timestamp {latest_timestamp} for quiz {quiz_id}")
            return jsonify({"success": True, "saved": False, "message": "Quiz already taken—check back for new content."}), 200
        cur.execute(
            "INSERT INTO scores (user_id, quiz_id, score, completed_at) VALUES (%s, %s, %s, %s)",
            (user['id'], quiz_id, score, datetime.now(timezone.utc))
        )
        cur.execute(
            "SELECT SUM(score) as total_score, COUNT(DISTINCT quiz_id) as quizzes_taken, "
            "SUM(CASE WHEN score = 69 OR score = 100 THEN 1 ELSE 0 END) as perfect_quizzes "
            "FROM scores WHERE user_id = %s",
            (user['id'],)
        )
        totals = cur.fetchone()
        cur.execute(
            "INSERT INTO user_totals (user_id, total_score, perfect_quizzes, last_quiz, quizzes_taken) "
            "VALUES (%s, %s, %s, %s, %s) "
            "ON CONFLICT (user_id) DO UPDATE SET "
            "total_score = EXCLUDED.total_score, perfect_quizzes = EXCLUDED.perfect_quizzes, "
            "last_quiz = EXCLUDED.last_quiz, quizzes_taken = EXCLUDED.quizzes_taken",
            (user['id'], totals['total_score'], totals['perfect_quizzes'], datetime.now(timezone.utc), totals['quizzes_taken'])
        )
        conn.commit()
        logging.info(f"Quiz {quiz_id} score {score} saved for user {user['username']}")
        return jsonify({"success": True, "saved": True, "message": "Score saved! Check the leaderboard."}), 200