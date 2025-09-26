import os
import secrets
import logging
from flask import Flask, session, render_template
from flask_cors import CORS
from dotenv import load_dotenv
from content import content_bp
from auth import auth_bp
from profile import profile_bp
from leaderboard import leaderboard_bp
from social import social_bp
from quiz import quiz_bp
from phish import phish_bp
from db_init import init_db

load_dotenv()
app = Flask(__name__, static_folder='dist')
app.secret_key = os.getenv('SECRET_KEY', secrets.token_hex(16))
CORS(app, origins=[os.getenv('ALLOWED_ORIGIN', '*')])

# Register Blueprints
app.register_blueprint(content_bp)
app.register_blueprint(auth_bp)
app.register_blueprint(profile_bp)
app.register_blueprint(leaderboard_bp)
app.register_blueprint(social_bp)
app.register_blueprint(quiz_bp)
app.register_blueprint(phish_bp)

# Initialize database and scheduler
init_db()
from content import refresh_database, start_scheduler
refresh_database()
start_scheduler()

@app.route('/')
def index():
    from flask import make_response
    from utils import load_quiz_count
    import logging
    logging.basicConfig(
        level=logging.DEBUG,
        format='%(asctime)s %(levelname)s: %(message)s',
        handlers=[logging.StreamHandler()],
        force=True
    )
    user = session.get('user')
    logging.debug(f"Root route accessed, session user: {user}")
    try:
        quiz_count = load_quiz_count()
        logging.debug(f"Quiz count: {quiz_count}")
        response = make_response(render_template('index.html', quiz_count=quiz_count, user=user))
        response.headers['Cache-Control'] = 'no-cache, no-store, must-revalidate'
        return response
    except Exception as e:
        logging.error(f"Error in root route: {e}")
        response = make_response(render_template('index.html', quiz_count=0, user=user, error="Error loading home page"))
        response.headers['Cache-Control'] = 'no-cache, no-store, must-revalidate'
        return response

@app.route('/home')
def home():
    return index()

@app.route('/profile')
def profile_page():
    return index()

@app.route('/profile/<username>')
def profile_page_username(username):
    return index()

@app.route('/leaderboard')
def leaderboard_page():
    return index()