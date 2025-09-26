from flask import Blueprint, jsonify, session, request, render_template, redirect, url_for, make_response
import logging
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
            if not profile['join_public'] and (not user or user.get('username') != username):
                logging.info(f"Profile access denied: {username} is private (join_public={profile['join_public']})")
                response = make_response(render_template('index.html', quiz_count=quiz_count, user=user, profile_error="This profile is private"))
                response.headers['Cache-Control'] = 'no-cache, no-store, must-revalidate'
                return response
            rank = 'Unranked'
            if profile['total_score'] and profile['total_score'] > 0:
                try:
                    logging.debug("Executing rank query")
                    cur.execute(
                        'SELECT COUNT(*) + 1 as rank FROM user_totals ut JOIN users u ON ut.user_id = u.id '
                        'WHERE u.join_public = TRUE AND (ut.total_score > %s OR '
                        '(ut.total_score = %s AND ut.perfect_quizzes > %s))',
                        (profile['total_score'], profile['total_score'], profile['perfect_quizzes'])
                    )
                    rank_row = cur.fetchone()
                    rank = rank_row['rank'] if rank_row else 'Unranked'
                    logging.debug(f"Rank: {rank}")
                except Exception as e:
                    logging.error(f"Error calculating rank: {str(e)}")
                    rank = 'Unranked'
            last_quiz = profile['last_quiz']
            last_quiz_str = "None"
            if last_quiz:
                try:
                    edt_timezone = timezone(timedelta(hours=-4))
                    last_quiz_edt = last_quiz.astimezone(edt_timezone)
                    last_quiz_str = last_quiz_edt.strftime('%A, %B %d, %Y at %I:%M:%S %p')
                    logging.debug(f"Last quiz formatted: {last_quiz_str}")
                except Exception as e:
                    logging.error(f"Error formatting last_quiz: {str(e)}")
                    last_quiz_str = "Unknown"
            avg_score = profile['avg_score'] or 0
            if profile['quizzes_taken'] and profile['quizzes_taken'] > 0 and avg_score == 0:
                avg_score = profile['total_score'] / profile['quizzes_taken']
            profile_data = {
                "username": profile['username'] or "Unknown",
                "bio": profile['bio'] or "No bio yet",
                "domain": profile['domain'] or "None",
                "join_team": profile['join_team'] or False,
                "join_public": profile['join_public'] or False,
                "rank": rank,
                "total_score": profile['total_score'] or 0,
                "quizzes_taken": profile['quizzes_taken'] or 0,
                "avg_score": round(avg_score, 1) if avg_score else 0,
                "perfect_quizzes": profile['perfect_quizzes'] or 0,
                "last_quiz": last_quiz_str
            }
            logging.debug(f"Profile data prepared: {profile_data}")
            quiz_history = []
            if user and user.get('username') == username:
                try:
                    logging.debug(f"Executing quiz history query for user_id: {profile['id']}")
                    cur.execute("""
                        SELECT completed_at, score
                        FROM scores
                        WHERE user_id = %s
                        ORDER BY completed_at DESC
                        LIMIT 10
                    """, (profile['id'],))
                    quiz_history = cur.fetchall()
                    quiz_history = [{
                        "quiz_date": row['completed_at'].strftime('%m/%d/%Y %I:%M %p') if row['completed_at'] else 'Unknown',
                        "taken": row['completed_at'].strftime('%m/%d/%Y %I:%M %p') if row['completed_at'] else 'Unknown',
                        "score": row['score'] or 0,
                        "status": 'Pass' if (row['score'] <= 69 and row['score'] >= 48) or (row['score'] > 69 and row['score'] >= 80) else 'Fail',
                        "is_perfect": row['score'] == 69 or row['score'] == 100
                    } for row in quiz_history]
                    logging.debug(f"Quiz history: {quiz_history}")
                except Exception as e:
                    logging.error(f"Error fetching quiz history: {str(e)}")
                    quiz_history = []
            if not profile_data:
                logging.error("Profile data is empty")
                response = make_response(render_template('index.html', quiz_count=quiz_count, user=user, profile_error="Profile data unavailable"))
                response.headers['Cache-Control'] = 'no-cache, no-store, must-revalidate'
                return response
            response = make_response(render_template('index.html', quiz_count=quiz_count, user=user, profile_data=profile_data, quiz_history=quiz_history))
            response.headers['Cache-Control'] = 'no-cache, no-store, must-revalidate'
            logging.debug("Rendering template with profile_data and quiz_history")
            return response
        except Exception as e:
            logging.error(f"Error in profile endpoint: {str(e)}")
            response = make_response(render_template('index.html', quiz_count=quiz_count, user=user, profile_error="Error loading profile data"))
            response.headers['Cache-Control'] = 'no-cache, no-store, must-revalidate'
            return response

@profile_bp.route('/api/profile/<username>')
def api_profile(username):
    user = session.get('user')
    logging.debug(f"API profile request for username: {username}, session user: {user}")
    with get_db_conn() as conn:
        try:
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
                         user_totals.last_quiz, user_totals.quizzes_taken, users.domain,
                         users.join_team, users.join_public
            """, (username,))
            profile = cur.fetchone()
            logging.debug(f"Profile query result: {profile}")
            if not profile:
                return jsonify({"error": "User not found"}), 404
            if not profile['join_public'] and (not user or user.get('username') != username):
                return jsonify({"error": "This profile is private"}), 403
            rank = 'Unranked'
            if profile['total_score'] and profile['total_score'] > 0:
                try:
                    logging.debug("Executing rank query")
                    cur.execute(
                        'SELECT COUNT(*) + 1 as rank FROM user_totals ut JOIN users u ON ut.user_id = u.id '
                        'WHERE u.join_public = TRUE AND (ut.total_score > %s OR '
                        '(ut.total_score = %s AND ut.perfect_quizzes > %s))',
                        (profile['total_score'], profile['total_score'], profile['perfect_quizzes'])
                    )
                    rank_row = cur.fetchone()
                    rank = rank_row['rank'] if rank_row else 'Unranked'
                    logging.debug(f"Rank: {rank}")
                except Exception as e:
                    logging.error(f"Error calculating rank: {str(e)}")
                    rank = 'Unranked'
            last_quiz = profile['last_quiz']
            last_quiz_str = None
            if last_quiz:
                try:
                    last_quiz_str = last_quiz.isoformat() + 'Z'
                    logging.debug(f"Last quiz ISO: {last_quiz_str}")
                except Exception as e:
                    logging.error(f"Error formatting last_quiz: {str(e)}")
                    last_quiz_str = None
            avg_score = profile['avg_score'] or 0
            if profile['quizzes_taken'] and profile['quizzes_taken'] > 0 and avg_score == 0:
                avg_score = profile['total_score'] / profile['quizzes_taken']
            profile_data = {
                "username": profile['username'] or "Unknown",
                "bio": profile['bio'] or "No bio yet",
                "domain": profile['domain'] or "None",
                "join_team": profile['join_team'] or False,
                "join_public": profile['join_public'] or False,
                "rank": rank,
                "total_score": profile['total_score'] or 0,
                "quizzes_taken": profile['quizzes_taken'] or 0,
                "avg_score": round(avg_score, 1) if avg_score else 0,
                "perfect_quizzes": profile['perfect_quizzes'] or 0,
                "last_quiz": last_quiz_str
            }
            return jsonify({"profile_data": profile_data})
        except Exception as e:
            logging.error(f"API profile endpoint error: {str(e)}")
            return jsonify({"error": "Failed to load profile"}), 500

@profile_bp.route('/api/check_username', methods=['POST'])
def check_username():
    user = session.get('user')
    if not user:
        return jsonify({"error": "Not logged in"}), 401
    data = request.json
    username = bleach.clean(data.get('username', '').strip()[:30], tags=[], strip=True)
    if len(username) < 5 or len(username) > 30 or not re.match(r'^[a-zA-Z0-9_]+$', username):
        return jsonify({"error": "Username must be 5-30 chars, alphanumeric or underscore"}), 400
    with get_db_conn() as conn:
        cur = conn.cursor()
        cur.execute("SELECT id FROM users WHERE username = %s AND id != %s", (username, user['id']))
        if cur.fetchone():
            return jsonify({"error": "Username already taken"}), 400
        return jsonify({"success": True})

@profile_bp.route('/api/update_profile', methods=['POST'])
def update_profile():
    user = session.get('user')
    if not user:
        return jsonify({"error": "Not logged in"}), 401
    data = request.json
    username = bleach.clean(data.get('username', '').strip()[:30], tags=[], strip=True)
    bio = bleach.clean(data.get('bio', '').strip()[:100], tags=[], strip=True)
    join_team = data.get('join_team', False)
    join_public = data.get('join_public', False)
    if len(username) < 5 or len(username) > 30 or not re.match(r'^[a-zA-Z0-9_]+$', username):
        return jsonify({"error": "Username must be 5-30 chars, alphanumeric or underscore"}), 400
    if len(bio) > 100:
        return jsonify({"error": "Bio must be 100 chars or less"}), 400
    with get_db_conn() as conn:
        cur = conn.cursor()
        try:
            cur.execute(
                'UPDATE users SET username = %s, bio = %s, join_team = %s, join_public = %s WHERE id = %s',
                (username, bio, join_team, join_public, user['id'])
            )
            conn.commit()
            if cur.rowcount == 0:
                return jsonify({"error": "User not found"}), 404
            session['user']['username'] = username
            session['user']['bio'] = bio
            session['user']['join_team'] = join_team
            session['user']['join_public'] = join_public
            return jsonify({"success": True, "username": username, "bio": bio, "join_team": join_team, "join_public": join_public})
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