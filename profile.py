import logging
from flask import Blueprint, jsonify, session, request, render_template, redirect, url_for, make_response
import bleach
import re
from datetime import timezone, timedelta
from psycopg2.extras import DictCursor
from utils import get_db_conn, load_quiz_count

profile_bp = Blueprint('profile', __name__)

@profile_bp.route('/profile')
def profile_redirect():
    user = session.get('user')
    logging.debug(f"Profile redirect accessed, session user: {user}")
    if not user:
        logging.debug("No user in session, showing login error")
        response = make_response(render_template('index.html', quiz_count=0, user=None, profile_error="Please log in to view your profile"))
        response.headers['Cache-Control'] = 'no-cache, no-store, must-revalidate'
        return response
    logging.debug(f"Redirecting to /profile/{user['username']}")
    response = redirect(url_for('profile.profile', username=user['username']))
    response.headers['Cache-Control'] = 'no-cache, no-store, must-revalidate'
    return response

@profile_bp.route('/profile/<username>')
def profile(username):
    user = session.get('user')
    logging.debug(f"Profile request for username: {username}, session user: {user}")
    with get_db_conn() as conn:
        try:
            cur = conn.cursor(cursor_factory=DictCursor)
            logging.debug("Executing quiz count query")
            cur.execute("SELECT count FROM quiz_counts WHERE id = 1")
            quiz_count_row = cur.fetchone()
            quiz_count = quiz_count_row[0] if quiz_count_row else 0
            logging.debug(f"Quiz count: {quiz_count}")
            logging.debug(f"Executing profile query for username: {username}")
            cur.execute("""
                SELECT users.id, users.username, users.bio, users.domain, users.join_team, users.join_public,
                       user_totals.total_score, user_totals.perfect_quizzes,
                       user_totals.last_quiz, user_totals.quizzes_taken,
                       COALESCE(AVG(scores.score), 0) as avg_score
                FROM users
                LEFT JOIN user_totals ON users.id = user_totals.user_id
                LEFT JOIN scores ON users.id = scores.user_id
                WHERE users.username = %s
                GROUP BY users.id, user_totals.total_score, user_totals.perfect_quizzes,
                         user_totals.last_quiz, user_totals.quizzes_taken, users.domain,
                         users.join_team, users.join_public
            """, (username,))
            profile = cur.fetchone()
            logging.debug(f"Profile query result: {profile}")
            if not profile:
                logging.error(f"User not found: {username}")
                response = make_response(render_template('index.html', quiz_count=quiz_count, user=user, profile_error="User not found"))
                response.headers['Cache-Control'] = 'no-cache, no-store, must-revalidate'
                return response
            profile_data = {
                "username": profile['username'],
                "bio": profile['bio'],
                "domain": profile['domain'],
                "join_team": profile['join_team'],
                "join_public": profile['join_public'],
                "total_score": profile['total_score'] or 0,
                "perfect_quizzes": profile['perfect_quizzes'] or 0,
                "last_quiz": profile['last_quiz'].isoformat() + 'Z' if profile['last_quiz'] else None,
                "quizzes_taken": profile['quizzes_taken'] or 0,
                "avg_score": round(profile['avg_score'], 1)
            }
            logging.debug(f"Profile data: {profile_data}")
            cur.execute("""
                SELECT RANK() OVER (ORDER BY ut.total_score DESC, ut.perfect_quizzes DESC, ut.last_quiz ASC) as rank
                FROM user_totals ut
                JOIN users u ON ut.user_id = u.id
                WHERE u.join_public = TRUE
            """)
            ranks = cur.fetchall()
            rank_map = {r['rank']: r for r in ranks}
            profile_data['rank'] = rank_map.get(profile['id'], {}).get('rank', 'Unranked') if ranks else 'Unranked'
            response = make_response(render_template('index.html', quiz_count=quiz_count, user=user, profile_data=profile_data))
            response.headers['Cache-Control'] = 'no-cache, no-store, must-revalidate'
            return response
        except Exception as e:
            logging.error(f"Error loading profile for {username}: {e}")
            response = make_response(render_template('index.html', quiz_count=quiz_count, user=user, profile_error="Error loading profile"))
            response.headers['Cache-Control'] = 'no-cache, no-store, must-revalidate'
            return response

@profile_bp.route('/api/profile/<username>', methods=['GET'])
def get_profile(username):
    with get_db_conn() as conn:
        cur = conn.cursor(cursor_factory=DictCursor)
        cur.execute("""
            SELECT users.id, users.username, users.bio, users.domain, users.join_team, users.join_public,
                   user_totals.total_score, user_totals.perfect_quizzes,
                   user_totals.last_quiz, user_totals.quizzes_taken,
                   COALESCE(AVG(scores.score), 0) as avg_score
            FROM users
            LEFT JOIN user_totals ON users.id = user_totals.user_id
            LEFT JOIN scores ON users.id = scores.user_id
            WHERE users.username = %s
            GROUP BY users.id, user_totals.total_score, user_totals.perfect_quizzes,
                     user_totals.last_quiz, user_totals.quizzes_taken
        """, (username,))
        profile = cur.fetchone()
        if not profile:
            return jsonify({"error": "User not found"}), 404
        profile_data = {
            "username": profile['username'],
            "bio": profile['bio'],
            "domain": profile['domain'],
            "join_team": profile['join_team'],
            "join_public": profile['join_public'],
            "total_score": profile['total_score'] or 0,
            "perfect_quizzes": profile['perfect_quizzes'] or 0,
            "last_quiz": profile['last_quiz'].isoformat() + 'Z' if profile['last_quiz'] else None,
            "quizzes_taken": profile['quizzes_taken'] or 0,
            "avg_score": round(profile['avg_score'], 1)
        }
        cur.execute("""
            SELECT COUNT(*) + 1 as rank FROM user_totals ut JOIN users u ON ut.user_id = u.id
            WHERE u.join_public = TRUE AND (ut.total_score > %s OR
            (ut.total_score = %s AND ut.perfect_quizzes > %s) OR
            (ut.total_score = %s AND ut.perfect_quizzes = %s AND ut.last_quiz > %s))
        """, (profile['total_score'], profile['total_score'], profile['perfect_quizzes'],
              profile['total_score'], profile['perfect_quizzes'], profile['last_quiz']))
        rank_row = cur.fetchone()
        profile_data['rank'] = rank_row['rank'] if rank_row['rank'] != 1 or profile['total_score'] > 0 else 'Unranked'
        return jsonify({"profile_data": profile_data})

@profile_bp.route('/api/check_username', methods=['POST'])
def check_username():
    data = request.json
    username = data.get('username')
    if not username:
        return jsonify({"error": "Username required"}), 400
    with get_db_conn() as conn:
        cur = conn.cursor()
        cur.execute("SELECT COUNT(*) FROM users WHERE username = %s", (username,))
        exists = cur.fetchone()[0] > 0
        if exists:
            return jsonify({"error": "Username taken"}), 409
        return jsonify({"available": True})

@profile_bp.route('/api/update_profile', methods=['POST'])
def update_profile():
    user = session.get('user')
    if not user:
        return jsonify({"error": "Not logged in"}), 401
    data = request.json
    username = data.get('username')
    bio = bleach.clean(data.get('bio', ''), tags=[], strip=True)
    join_team = data.get('join_team', False)
    join_public = data.get('join_public', True)
    if not re.match(r'^[a-zA-Z0-9_]{5,30}$', username):
        return jsonify({"error": "Invalid username"}), 400
    if len(bio) > 100:
        return jsonify({"error": "Bio too long"}), 400
    with get_db_conn() as conn:
        cur = conn.cursor(cursor_factory=DictCursor)
        try:
            cur.execute(
                'UPDATE users SET username = %s, bio = %s, join_team = %s, join_public = %s WHERE id = %s RETURNING username',
                (username, bio, join_team, join_public, user['id'])
            )
            updated = cur.fetchone()
            if cur.rowcount == 0:
                return jsonify({"error": "User not found"}), 404
            conn.commit()
            session['user']['username'] = updated['username']
            return jsonify({"success": True, "username": updated['username']})
        except psycopg2.errors.UniqueViolation:
            conn.rollback()
            return jsonify({"error": "Username already taken"}), 400

@profile_bp.route('/api/update_team_status', methods=['PATCH'])
def update_team_status():
    user = session.get('user')
    if not user:
        logging.error("No user in session for /api/update_team_status")
        return jsonify({"error": "Not logged in"}), 401
    data = request.json
    join_team = data.get('join_team', False)
    logging.debug(f"Updating join_team to {join_team} for user_id {user['id']}")
    with get_db_conn() as conn:
        cur = conn.cursor(cursor_factory=DictCursor)
        try:
            cur.execute(
                'UPDATE users SET join_team = %s WHERE id = %s RETURNING domain',
                (join_team, user['id'])
            )
            updated = cur.fetchone()
            if cur.rowcount == 0:
                logging.error(f"User not found for id {user['id']} in /api/update_team_status")
                return jsonify({"error": "User not found"}), 404
            conn.commit()
            logging.info(f"Successfully updated join_team to {join_team} for user_id {user['id']}")
            session['user']['domain'] = updated['domain']
            return jsonify({"success": True, "join_team": join_team})
        except psycopg2.Error as e:
            conn.rollback()
            logging.error(f"Database error updating join_team for user_id {user['id']}: {e}")
            return jsonify({"error": "Database error"}), 500

@profile_bp.route('/api/update_public_status', methods=['PATCH'])
def update_public_status():
    user = session.get('user')
    if not user:
        logging.error("No user in session for /api/update_public_status")
        return jsonify({"error": "Not logged in"}), 401
    data = request.json
    join_public = data.get('join_public', True)
    logging.debug(f"Updating join_public to {join_public} for user_id {user['id']}")
    with get_db_conn() as conn:
        cur = conn.cursor(cursor_factory=DictCursor)
        try:
            cur.execute(
                'UPDATE users SET join_public = %s WHERE id = %s',
                (join_public, user['id'])
            )
            if cur.rowcount == 0:
                logging.error(f"User not found for id {user['id']} in /api/update_public_status")
                return jsonify({"error": "User not found"}), 404
            conn.commit()
            logging.info(f"Successfully updated join_public to {join_public} for user_id {user['id']}")
            session['user']['join_public'] = join_public
            return jsonify({"success": True, "join_public": join_public})
        except psycopg2.Error as e:
            conn.rollback()
            logging.error(f"Database error updating join_public for user_id {user['id']}: {e}")
            return jsonify({"error": "Database error"}), 500