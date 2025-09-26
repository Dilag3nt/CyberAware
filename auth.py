from flask import Blueprint, redirect, url_for, session, request, make_response, render_template
from authlib.integrations.flask_client import OAuth
import secrets
import logging
import jwt
import requests
from utils import get_db_conn, generate_username, load_quiz_count

auth_bp = Blueprint('auth', __name__)

oauth = OAuth()
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

@auth_bp.after_request
def apply_csp(response):
    response.headers['Content-Security-Policy'] = (
        "default-src 'self'; "
        "script-src 'self' 'unsafe-eval' 'unsafe-inline' https://cdn.jsdelivr.net https://cdnjs.cloudflare.com; "
        "script-src-attr 'self' 'unsafe-inline'; "
        "style-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net https://cdnjs.cloudflare.com; "
        "font-src 'self' https://cdnjs.cloudflare.com; "
        "connect-src 'self' https://api.x.ai https://feeds.feedburner.com https://krebsonsecurity.com https://www.darkreading.com https://isc.sans.edu https://www.bleepingcomputer.com https://accounts.google.com https://login.microsoftonline.com https://cdn.jsdelivr.net https://cdnjs.cloudflare.com;"
    )
    logging.debug(f"Applied CSP: {response.headers['Content-Security-Policy']}")
    return response

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

@auth_bp.route('/auth/<provider>/callback')
def auth_callback(provider):
    try:
        if provider == 'google':
            token = google.authorize_access_token()
            nonce = session.pop('google_nonce', None)
            if not nonce:
                logging.error("No nonce found in session for Google OAuth")
                return redirect(url_for('index'))
            user_info = google.parse_id_token(token, nonce=nonce)
            social_id = user_info['sub']
            email = user_info.get('email', '')
        elif provider == 'microsoft':
            code = request.args.get('code')
            if not code:
                logging.error("No code provided in Microsoft OAuth callback")
                return redirect(url_for('index'))
            nonce = session.pop('microsoft_nonce', None)
            if not nonce:
                logging.error("No nonce found in session for Microsoft OAuth")
                return redirect(url_for('index'))
            try:
                from authlib.integrations.requests_client import OAuth2Session
                temp_client = OAuth2Session(
                    os.getenv('MICROSOFT_CLIENT_ID'),
                    os.getenv('MICROSOFT_CLIENT_SECRET')
                )
                token_endpoint = 'https://login.microsoftonline.com/common/oauth2/v2.0/token'
                redirect_uri = url_for('auth.auth_callback', provider='microsoft', _external=True)
                token = temp_client.fetch_token(
                    token_endpoint,
                    grant_type='authorization_code',
                    code=code,
                    redirect_uri=redirect_uri
                )
            except Exception as e:
                logging.error(f"Microsoft token fetch failed: {e}")
                return redirect(url_for('index'))
            try:
                id_token = token.get('id_token')
                if not id_token:
                    logging.error("No ID token provided in Microsoft OAuth response")
                    return redirect(url_for('index'))
                jwks = requests.get('https://login.microsoftonline.com/common/discovery/v2.0/keys').json()
                decoded_header = jwt.get_unverified_header(id_token)
                kid = decoded_header.get('kid')
                key = next((k for k in jwks['keys'] if k['kid'] == kid), None)
                if not key:
                    logging.error(f"No matching JWK found for kid: {kid}")
                    return redirect(url_for('index'))
                from jwt.algorithms import RSAAlgorithm
                public_key = RSAAlgorithm.from_jwk(key)
                user_info = jwt.decode(
                    id_token,
                    public_key,
                    algorithms=['RS256'],
                    audience=os.getenv('MICROSOFT_CLIENT_ID'),
                    options={'verify_nbf': False, 'verify_iss': False}
                )
                if user_info.get('nonce') != nonce:
                    logging.error(f"Nonce mismatch: expected {nonce}, got {user_info.get('nonce')}")
                    return redirect(url_for('index'))
                logging.info(f"Microsoft ID token claims: {user_info}")
            except Exception as e:
                logging.error(f"Microsoft ID token validation failed: {e}")
                return redirect(url_for('index'))
            social_id = user_info['sub']
            email = user_info.get('email') or user_info.get('upn') or user_info.get('preferred_username', '')
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
            cur = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
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
        return jsonify({"has_team": False})
    with get_db_conn() as conn:
        cur = conn.cursor()
        cur.execute("SELECT domain, join_team FROM users WHERE id = %s", (user['id'],))
        row = cur.fetchone()
        if row:
            domain, join_team = row
            has_team = bool(domain and join_team)
            return jsonify({"has_team": has_team, "domain": domain})
    return jsonify({"has_team": False})