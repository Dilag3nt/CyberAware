from flask import Blueprint, jsonify, request, session
import logging
from datetime import datetime, timezone, timedelta
from psycopg2.extras import DictCursor
from utils import get_db_conn

leaderboard_bp = Blueprint('leaderboard', __name__)

@leaderboard_bp.route('/api/leaderboard', methods=['GET'])
def leaderboard():
    scope = request.args.get('scope', 'weekly')
    with get_db_conn() as conn:
        cur = conn.cursor(cursor_factory=DictCursor)
        user = session.get('user')
        leaders = []
        user_rank = None
        team_stats = None
        if scope == 'team':
            if not user or not user.get('domain'):
                return jsonify({"error": "No team access", "leaders": [], "user_rank": None, "team_stats": None}), 403
            domain = user['domain']
            cur.execute("""
                SELECT users.username, COUNT(DISTINCT scores.quiz_id) as quizzes_taken,
                       COUNT(CASE WHEN scores.score = 69 OR scores.score = 100 THEN 1 END) as perfect_quizzes,
                       AVG(scores.score) as avg_score, SUM(scores.score) as total_score,
                       user_totals.last_quiz
                FROM scores
                JOIN users ON scores.user_id = users.id
                JOIN user_totals ON users.id = user_totals.user_id
                WHERE users.domain = %s AND users.join_team = TRUE AND scores.score > 0
                GROUP BY users.id, user_totals.last_quiz
                ORDER BY total_score DESC, perfect_quizzes DESC, MIN(scores.completed_at) ASC
            """, (domain,))
            leaders = [{"rank": i+1, "username": row['username'], "quizzes_taken": row['quizzes_taken'],
                        "perfect_quizzes": row['perfect_quizzes'], "avg_score": round(row['avg_score'] or 0, 1),
                        "total_score": row['total_score'] or 0, "last_quiz": row['last_quiz'].isoformat() + 'Z' if row['last_quiz'] else None}
                       for i, row in enumerate(cur.fetchall())]
            cur.execute("""
                SELECT SUM(user_totals.total_score) as team_total,
                       AVG((SELECT AVG(score) FROM scores WHERE scores.user_id = users.id AND scores.score > 0)) as team_avg,
                       SUM(user_totals.perfect_quizzes) as team_perfects,
                       COUNT(*) as members
                FROM user_totals
                JOIN users ON user_totals.user_id = users.id
                WHERE users.domain = %s AND users.join_team = TRUE
            """, (domain,))
            ts = cur.fetchone()
            team_stats = {
                "team_total": ts['team_total'] or 0,
                "team_avg": round(ts['team_avg'] or 0, 1),
                "team_perfects": ts['team_perfects'] or 0,
                "members": ts['members'] or 0
            } if ts else None
            if user:
                cur.execute('SELECT total_score, perfect_quizzes FROM user_totals WHERE user_id = %s', (user['id'],))
                totals = cur.fetchone()
                if totals and totals['total_score'] > 0:
                    cur.execute(
                        'SELECT COUNT(*) + 1 as rank FROM user_totals ut JOIN users u ON ut.user_id = u.id '
                        'WHERE u.domain = %s AND u.join_team = TRUE AND (ut.total_score > %s OR (ut.total_score = %s AND ut.perfect_quizzes > %s))',
                        (domain, totals['total_score'], totals['total_score'], totals['perfect_quizzes'])
                    )
                    user_rank = {"rank": cur.fetchone()['rank'], "username": user['username'], "total_score": totals['total_score']}
        elif scope == 'weekly':
            week_start = (datetime.now(timezone.utc) - timedelta(days=datetime.now(timezone.utc).weekday())).replace(hour=0, minute=0, second=0, microsecond=0)
            cur.execute("""
                SELECT users.username, COUNT(DISTINCT scores.quiz_id) as quizzes_taken,
                       COUNT(CASE WHEN scores.score = 69 OR scores.score = 100 THEN 1 END) as perfect_quizzes,
                       AVG(scores.score) as avg_score, SUM(scores.score) as total_score,
                       user_totals.last_quiz
                FROM scores
                JOIN users ON scores.user_id = users.id
                JOIN user_totals ON users.id = user_totals.user_id
                WHERE scores.completed_at >= %s AND scores.score > 0 AND users.join_public = TRUE
                GROUP BY users.id, user_totals.last_quiz
                ORDER BY total_score DESC, perfect_quizzes DESC, MIN(scores.completed_at) ASC
            """, (week_start,))
            leaders = [{"rank": i+1, "username": row['username'], "quizzes_taken": row['quizzes_taken'],
                        "perfect_quizzes": row['perfect_quizzes'], "avg_score": round(row['avg_score'], 1),
                        "total_score": row['total_score'], "last_quiz": row['last_quiz'].isoformat() + 'Z' if row['last_quiz'] else None}
                       for i, row in enumerate(cur.fetchall())]
        else:  # all-time
            cur.execute("""
                SELECT users.username, COUNT(DISTINCT scores.quiz_id) as quizzes_taken,
                       user_totals.perfect_quizzes, COALESCE(AVG(scores.score), 0) as avg_score,
                       user_totals.total_score, user_totals.last_quiz
                FROM user_totals
                JOIN users ON user_totals.user_id = users.id
                LEFT JOIN scores ON users.id = scores.user_id
                WHERE user_totals.total_score > 0 AND users.join_public = TRUE
                GROUP BY users.id, user_totals.perfect_quizzes, user_totals.total_score, user_totals.last_quiz
                ORDER BY user_totals.total_score DESC, user_totals.perfect_quizzes DESC, user_totals.last_quiz ASC
            """)
            leaders = [{"rank": i+1, "username": row['username'], "quizzes_taken": row['quizzes_taken'],
                        "perfect_quizzes": row['perfect_quizzes'], "avg_score": round(row['avg_score'], 1),
                        "total_score": row['total_score'], "last_quiz": row['last_quiz'].isoformat() + 'Z' if row['last_quiz'] else None}
                       for i, row in enumerate(cur.fetchall())]
        if scope != 'team' and user:
            cur.execute(
                'SELECT total_score, perfect_quizzes FROM user_totals WHERE user_id = %s',
                (user['id'],)
            )
            totals = cur.fetchone()
            if totals and totals['total_score'] > 0:
                cur.execute(
                    'SELECT COUNT(*) + 1 as rank FROM user_totals ut JOIN users u ON ut.user_id = u.id '
                    'WHERE u.join_public = TRUE AND (ut.total_score > %s OR '
                    '(ut.total_score = %s AND ut.perfect_quizzes > %s))',
                    (totals['total_score'], totals['total_score'], totals['perfect_quizzes'])
                )
                user_rank = {"rank": cur.fetchone()['rank'], "username": user['username'],
                             "total_score": totals['total_score']}
        return jsonify({"leaders": leaders, "user_rank": user_rank, "team_stats": team_stats})