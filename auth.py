import os
from flask import Blueprint, redirect, url_for, session, request, make_response, render_template, jsonify
import secrets
import logging
import jwt
import requests
from utils import get_db_conn, generate_username, load_quiz_count
from psycopg2.extras import DictCursor

auth_bp = Blueprint('auth', __name__)

def init_oauth(oauth):
    global google, microsoft
    google = oauth.register(
        name='google',
        client_id=os.getenv('GOOGLE_CLIENT_ID'),
        client_secret=os.getenv('GOOGLE_CLIENT_SECRET'),
        server_metadata_url='https://accounts.google.com/.well-known/openid-configuration',
        client_kwargs={'scope': 'openid email profile'}
    )
    microsoft = oauth.register(
        name='microsoft',
        client_id=os.getenv('MICROSOFT_CLIENT_ID'),
        client_secret=os.getenv('MICROSOFT_CLIENT_SECRET'),
        server_metadata_url='https://login.microsoftonline.com/common/v2.0/.well-known/openid-configuration',
        client_kwargs={'scope': 'openid email profile'},
        authorize_params={'prompt': 'select_account'},
        jwks_uri='https://login.microsoftonline.com/common/discovery/v2.0/keys'
    )

@auth_bp.route('/login')
def login_page():
    return_to = request.args.get('return_to', 'home')
    response = make_response(render_template('index.html', quiz_count=load_quiz_count(), user=None, login_options=True, return_to=return_to))
    response.headers['Cache-Control'] = 'no-cache, no-store, must-revalidate'
    return response

@auth_bp.route('/login/<provider>')
def login(provider):
    return_to = request.args.get('return_to', 'home')
    if provider == 'google':
        nonce = secrets.token_urlsafe(16)
        session['google_nonce'] = nonce
        session['return_to'] = return_to
        return google.authorize_redirect(url_for('auth.auth_callback', provider='google', _external=True), nonce=nonce)
    elif provider == 'microsoft':
        nonce = secrets.token_urlsafe(16)
        session['microsoft_nonce'] = nonce
        session['return_to'] = return_to
        return microsoft.authorize_redirect(url_for('auth.auth_callback', provider='microsoft', _external=True), nonce=nonce)
    return redirect(url_for('index'))

@auth_bp.route('/auth/<provider>')
def auth_callback(provider):
    try:
        if provider == 'google':
            token = google.authorize_access_token()
            nonce = session.pop('google_nonce', None)
            user_info = google.parse_id_token(token, nonce=nonce)
            social_id = user_info['sub']
            name = user_info.get('name', '')
            email = user_info.get('email', '')
            logging.debug(f"Google user info: {user_info}")
        elif provider == 'microsoft':
            token = microsoft.authorize_access_token()
            nonce = session.pop('microsoft_nonce', None)
            user_info = microsoft.parse_id_token(token, nonce=nonce)
            social_id = user_info['oid']
            name = user_info.get('name', '')
            email = user_info.get('email') or user_info.get('upn') or user_info.get('preferred_username', '')
            logging.debug(f"Microsoft user info: {user_info}")
        else:
            return redirect(url_for('index'))
        domain = None
        if email:
            try:
                full_domain = email.split('@')[1].lower()
                domain = full_domain
            except IndexError:
                pass
        username = generate_username()
        with get_db_conn() as conn:
            cur = conn.cursor(cursor_factory=DictCursor)
            cur.execute('SELECT id, username, domain FROM users WHERE social_id = %s AND provider = %s', (social_id, provider))
            user = cur.fetchone()
            if not user:
                cur.execute(
                    'INSERT INTO users (social_id, provider, username, bio, domain) VALUES (%s, %s, %s, %s, %s) RETURNING id, username, domain',
                    (social_id, provider, username, '', domain)
                )
                user = cur.fetchone()
                user_id = user['id']
                cur.execute('INSERT INTO user_totals (user_id, total_score, perfect_quizzes) VALUES (%s, 0, 0)', (user_id,))
                conn.commit()
            else:
                cur.execute(
                    'UPDATE users SET domain = %s WHERE id = %s RETURNING id, username, domain',
                    (domain, user['id'])
                )
                user = cur.fetchone()
                conn.commit()
            session['user'] = {'id': user['id'], 'username': user['username'], 'provider': provider, 'domain': user['domain']}
        return_to = session.pop('return_to', 'home')
        if return_to == 'leaderboard':
            return redirect(url_for('leaderboard_page'))
        elif return_to == 'profile':
            return redirect(url_for('profile', username=user['username']))
        else:
            return redirect(url_for('index'))
    except Exception as e:
        logging.error(f"Auth error for {provider}: {e}")
        return redirect(url_for('index'))

@auth_bp.route('/logout')
def logout():
    session.pop('user', None)
    response = redirect(url_for('index'))
    response.set_cookie('clearLocalStorage', 'true', max_age=60)
    response.headers['Cache-Control'] = 'no-cache, no-store, must-revalidate'
    return response

@auth_bp.route('/api/user_status', methods=['GET'])
def user_status():
    user = session.get('user')
    return jsonify({"user": user})

@auth_bp.route('/api/user_team_status', methods=['GET'])
def user_team_status():
    user = session.get('user')
    if not user:
        logging.debug("No user in session for /api/user_team_status")
        return jsonify({"has_team": False})
    try:
        with get_db_conn() as conn:
            cur = conn.cursor(cursor_factory=DictCursor)
            cur.execute("SELECT domain, join_team FROM users WHERE id = %s", (user['id'],))
            row = cur.fetchone()
            if row:
                domain, join_team = row['domain'], row['join_team']
                has_team = bool(domain and join_team)
                return jsonify({"has_team": has_team, "domain": domain})
            else:
                logging.error(f"User not found for id {user['id']} in /api/user_team_status")
                return jsonify({"has_team": False}), 404
    except Exception as e:
        logging.error(f"Error in /api/user_team_status for user_id {user.get('id', 'unknown')}: {e}")
        return jsonify({"error": "Internal server error"}), 500