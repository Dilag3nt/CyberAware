from flask import Blueprint, jsonify, request, session
import logging
from datetime import datetime, timezone
from psycopg2.extras import DictCursor
from utils import get_db_conn, save_quiz_count

quiz_bp = Blueprint('quiz', __name__)

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

@quiz_bp.route('/api/update_quiz_count', methods=['GET', 'POST'])
def update_quiz_count():
    with get_db_conn() as conn:
        cur = conn.cursor()
        cur.execute("SELECT count FROM quiz_counts WHERE id = 1")
        current_count = cur.fetchone()[0]
        if request.method == 'POST':
            new_count = current_count + 1
            cur.execute("UPDATE quiz_counts SET count = %s WHERE id = 1", (new_count,))
            conn.commit()
            logging.info(f"Updated quiz count to {new_count}")
            return jsonify({"count": new_count})
        else:  # GET
            return jsonify({"count": current_count})

@quiz_bp.route('/api/quiz_history', methods=['GET'])
def quiz_history():
    user = session.get('user')
    if not user:
        return jsonify({"error": "Unauthorized"}), 401
    page = request.args.get('page', 1, type=int)
    limit = 25
    offset = (page - 1) * limit
    with get_db_conn() as conn:
        try:
            cur = conn.cursor(cursor_factory=DictCursor)
            cur.execute("""
                SELECT quiz.created_at AS quiz_date, scores.completed_at AS taken, scores.score
                FROM scores
                JOIN quiz ON scores.quiz_id = quiz.id
                WHERE scores.user_id = %s
                ORDER BY scores.completed_at DESC
                LIMIT %s OFFSET %s
            """, (user['id'], limit, offset))
            history = cur.fetchall()
            history_data = []
            for row in history:
                logging.debug(f"Raw quiz history row: quiz_date={row['quiz_date']}, taken={row['taken']}, score={row['score']}")
                quiz_date_str = row['quiz_date'].isoformat().replace('+00:00', '') + 'Z' if row['quiz_date'] else 'Unknown'
                taken_str = row['taken'].isoformat().replace('+00:00', '') + 'Z' if row['taken'] else 'Unknown'
                history_data.append({
                    "quiz_date": quiz_date_str,
                    "taken": taken_str,
                    "score": row['score'] or 0,
                    "status": 'Pass' if (row['score'] <= 69 and row['score'] >= 48) or (row['score'] > 69 and row['score'] >= 80) else 'Fail',
                    "is_perfect": row['score'] == 69 or row['score'] == 100
                })
            cur.execute("SELECT COUNT(*) FROM scores WHERE user_id = %s", (user['id'],))
            total = cur.fetchone()[0]
            total_pages = (total + limit - 1) // limit
            logging.debug(f"Quiz history response: {history_data}")
            return jsonify({
                "history": history_data,
                "total": total,
                "page": page,
                "limit": limit,
                "total_pages": total_pages
            })
        except Exception as e:
            logging.error(f"Quiz history API error: {str(e)}")
            return jsonify({"error": "Failed to load quiz history"}), 500