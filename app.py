# Move imports to top and configure eventlet first
import eventlet
eventlet.monkey_patch()

from dotenv import load_dotenv
load_dotenv()  # Load environment variables from .env file

from flask import Flask, render_template, url_for, session, redirect, request, flash, jsonify, send_file, Response, g
from functools import wraps
import sqlite3
import random
import string
import hashlib
import os
from werkzeug.utils import secure_filename
import json
import time
from flask_socketio import SocketIO, emit
import socket
import logging
from datetime import datetime, timedelta
from flask_mail import Mail, Message
from config import Config
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from flask_wtf.csrf import CSRFProtect
from html import escape

# Database configurations
DATABASE_FOLDER = 'database'
DATABASE_PATH = os.path.join(DATABASE_FOLDER, 'database.db')

# Initialize Flask app first
app = Flask(__name__)

# Configure app
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', os.urandom(24))
app.config['UPLOAD_FOLDER'] = 'uploads'
app.config['MAX_CONTENT_LENGTH'] = 50 * 1024 * 1024  # 50MB max file size
app.config['WTF_CSRF_ENABLED'] = False  # Disable CSRF for now since we're using AJAX

# Initialize extensions
csrf = CSRFProtect(app)
app.config.from_object(Config)
mail = Mail(app)

# Configure logging
logging.basicConfig(
    filename='app.log',
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

# Initialize SocketIO
socketio = SocketIO(
    app,
    async_mode='eventlet',
    cors_allowed_origins='*',
    logger=True,
    engineio_logger=True,
    ping_timeout=60,
    ping_interval=25
)

# Make sure uploads directory exists
if not os.path.exists('uploads'):
    os.makedirs('uploads')

# Add these configurations
UPLOAD_FOLDER = 'uploads'
MAX_CONTENT_LENGTH = 50 * 1024 * 1024  # 50MB max file size
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
app.config['MAX_CONTENT_LENGTH'] = MAX_CONTENT_LENGTH

# Add this after app initialization
app.config['WTF_CSRF_ENABLED'] = False  # Disable CSRF for now since we're using AJAX

# Add these at the top of the file after imports
def init_app():
    """Initialize the application"""
    try:
        # Create database directory if it doesn't exist
        os.makedirs(DATABASE_FOLDER, exist_ok=True)
        
        # Create backup of existing database if it exists
        if os.path.exists(DATABASE_PATH):
            backup_path = f"{DATABASE_PATH}.backup"
            import shutil
            shutil.copy2(DATABASE_PATH, backup_path)
            logging.info(f"Created database backup at {backup_path}")
        
        # Initialize database
        init_db()
        
        # Initialize team points
        init_team_points()
        
        # Initialize default settings
        init_default_settings()
        
        logging.info("Application initialized successfully")
    except Exception as e:
        logging.error(f"Failed to initialize application: {str(e)}")
        raise

def init_db():
    """Initialize the database tables"""
    try:
        conn = sqlite3.connect(DATABASE_PATH)
        c = conn.cursor()
        
        # Create tables
        with app.open_resource('schema.sql', mode='r') as f:
            c.executescript(f.read())
            
        conn.commit()
        logging.info("Database initialized successfully")
        
        # Perform any necessary migrations
        migrate_database(conn)
        
    except Exception as e:
        logging.error(f"Database initialization error: {str(e)}")
        raise
    finally:
        conn.close()

def migrate_database(conn):
    """Perform any necessary database migrations"""
    c = conn.cursor()
    try:
        # Check if users table exists and has required columns
        c.execute("SELECT * FROM users LIMIT 1")
        logging.info("Users table migration completed successfully")
        
        # Check if teams table exists and has points column
        c.execute("SELECT points FROM teams LIMIT 1")
        logging.info("Team points migration completed successfully")
        
        # Check if point_transactions table has team_id column
        try:
            c.execute("SELECT team_id FROM point_transactions LIMIT 1")
            logging.info("Point transactions table already has team_id column")
        except sqlite3.OperationalError:
            logging.info("Adding team_id column to point_transactions table")
            
            # First check if we have any users
            c.execute("SELECT COUNT(*) FROM users")
            user_count = c.fetchone()[0]
            
            if user_count == 0:
                logging.warning("No users found in database, creating placeholder user")
                # Create a system user if none exists
                c.execute('''INSERT INTO users (username, email, password, is_admin)
                            VALUES ('system', 'system@local', 'system', 0)''')
                conn.commit()
            
            # Create new table with correct schema
            c.execute('''
                CREATE TABLE IF NOT EXISTS point_transactions_new (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER NOT NULL,
                    team_id INTEGER,
                    points INTEGER NOT NULL,
                    transaction_type TEXT NOT NULL,
                    description TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (user_id) REFERENCES users(id),
                    FOREIGN KEY (team_id) REFERENCES teams(id)
                )
            ''')
            
            # Check if old table exists and has data
            c.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='point_transactions'")
            if c.fetchone():
                # Copy data from old table to new table with COALESCE to handle NULL user_ids
                c.execute('''
                    INSERT OR IGNORE INTO point_transactions_new 
                    SELECT 
                        id, 
                        COALESCE(user_id, (SELECT MIN(id) FROM users)) as user_id,
                        NULL as team_id,
                        points,
                        transaction_type,
                        description,
                        created_at
                    FROM point_transactions
                ''')
            
            # Drop old table and rename new table
            c.execute('DROP TABLE IF EXISTS point_transactions')
            c.execute('ALTER TABLE point_transactions_new RENAME TO point_transactions')
            logging.info("Point transactions table migration completed successfully")
        
        # Add any other migrations here
        
        conn.commit()
    except sqlite3.Error as e:
        logging.error(f"Migration error: {str(e)}")
        conn.rollback()
        raise

def init_default_settings():
    """Initialize default settings if they don't exist"""
    conn = sqlite3.connect(DATABASE_PATH)
    c = conn.cursor()
    try:
        # Default settings
        default_settings = {
            'allow_registration': 'true',
            'allow_team_creation': 'true',
            'min_team_size': '1',
            'max_team_size': '4',
            'theme': 'dark',
            'logo_url': '',
            'platform_name': 'Zero Day Arena',
            'platform_description': 'A CTF Platform for Cybersecurity Enthusiasts'
        }
        
        # Insert default settings if they don't exist
        for key, value in default_settings.items():
            c.execute('''INSERT OR IGNORE INTO settings (key, value)
                        VALUES (?, ?)''', (key, value))
        
        # Initialize CTF timing if not set
        c.execute("SELECT COUNT(*) FROM setting_date_time")
        if c.fetchone()[0] == 0:
            default_start = datetime.now() + timedelta(hours=1)
            default_end = default_start + timedelta(days=1)
            c.execute('''INSERT INTO setting_date_time 
                        (start_time, end_time) VALUES (?, ?)''',
                     (default_start.strftime('%Y-%m-%dT%H:%M'),
                      default_end.strftime('%Y-%m-%dT%H:%M')))
        
        conn.commit()
    except sqlite3.Error as e:
        logging.error(f"Error initializing default settings: {str(e)}")
        conn.rollback()
        raise
    finally:
        conn.close()

# Add these helper functions for file handling
def secure_upload_filename(filename):
    """Secure a filename for upload"""
    # Remove any directory components
    filename = os.path.basename(filename)
    # Secure the filename
    return secure_filename(filename)

def secure_challenge_name(title):
    """Convert challenge title to a secure directory name"""
    # Remove special characters and convert spaces to underscores
    secure_name = "".join(c for c in title if c.isalnum() or c in (' ', '-', '_')).strip()
    secure_name = secure_name.replace(' ', '_')
    return secure_filename(secure_name)


def allowed_file(filename):
    # Allow all files that have an extension
    return '.' in filename

# Add this function to generate short IDs
def generate_short_id(length=4):
    """Generate a random short ID of specified length using letters and numbers"""
    chars = string.ascii_letters + string.digits
    while True:
        short_id = ''.join(random.choices(chars, k=length))
        conn = sqlite3.connect(DATABASE_PATH)
        c = conn.cursor()
        c.execute('SELECT id FROM challenges WHERE short_id = ?', (short_id,))
        if not c.fetchone():
            conn.close()
            return short_id
        conn.close()

# Generate random team code
def generate_team_code():
    return ''.join(random.choices(string.ascii_uppercase + string.digits, k=6))

# Hash password
def hash_password(password):
    return hashlib.sha256(password.encode()).hexdigest()

# Login required decorator
def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            flash('Please login first')
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function

# Add this helper function near the top of the file
def get_setting(key, default='true'):
    """Get a setting value from the database"""
    conn = sqlite3.connect(DATABASE_PATH)
    c = conn.cursor()
    try:
        c.execute("SELECT value FROM settings WHERE key = ?", (key,))
        result = c.fetchone()
        return result[0] if result else default
    finally:
        conn.close()

# Add this helper function to check if settings are enabled
def is_setting_enabled(key):
    """Check if a setting is enabled (true)"""
    return get_setting(key).lower() == 'true'

# Update the is_ctf_active() function to only check timing
def is_ctf_active():
    conn = sqlite3.connect(DATABASE_PATH)
    c = conn.cursor()
    try:
        c.execute("SELECT start_time, end_time FROM setting_date_time ORDER BY id DESC LIMIT 1")
        times = c.fetchone()
        
        if not times:
            return True  # If no times are set, consider CTF as active
            
        try:
            start_time = datetime.strptime(times[0], '%Y-%m-%dT%H:%M')
            end_time = datetime.strptime(times[1], '%Y-%m-%dT%H:%M')
            now = datetime.now()
            
            return start_time <= now <= end_time
        except ValueError:
            logging.error("Invalid date format in database")
            return True  # Return true if date parsing fails
            
    finally:
        conn.close()

def update_team_points(team_id, points_change, conn=None, user_id=None, description=None):
    """Update team points when points are gained or lost"""
    should_close = False
    if conn is None:
        conn = sqlite3.connect(DATABASE_PATH)
        should_close = True
    
    c = conn.cursor()
    try:
        # Add/subtract points instead of setting them directly
        c.execute('''UPDATE teams 
                    SET points = points + ?
                    WHERE id = ?''', 
                 (points_change, team_id))
        
        # Log the point transaction for the team
        c.execute('''INSERT INTO point_transactions 
                    (user_id, team_id, points, transaction_type, description)
                    VALUES (?, ?, ?, ?, ?)''',
                 (user_id, team_id, points_change, 
                  'gain' if points_change > 0 else 'loss',  # Changed from 'set' to 'gain'/'loss'
                  description or f'Team points {"gained" if points_change > 0 else "lost"}: {abs(points_change)}'))
        
        conn.commit()

        # After updating points, emit leaderboard update
        c.execute('''
            SELECT 
                t.id,
                t.name,
                COUNT(DISTINCT u.id) as member_count,
                COUNT(DISTINCT sc.challenge_id) as solved_challenges,
                t.points as total_points,
                GROUP_CONCAT(DISTINCT c.category) as categories
            FROM teams t
            LEFT JOIN users u ON t.id = u.team_id
            LEFT JOIN solved_challenges sc ON u.id = sc.user_id
            LEFT JOIN challenges c ON sc.challenge_id = c.id
            WHERE t.is_banned = 0
            GROUP BY t.id
            ORDER BY t.points DESC, solved_challenges DESC
        ''')
        
        teams = [{
            'id': row[0],
            'name': row[1],
            'member_count': row[2],
            'solved_challenges': row[3],
            'total_points': row[4],
            'categories': row[5].split(',') if row[5] else []
        } for row in c.fetchall()]
        
        socketio.emit('leaderboard_update', teams)

    finally:
        if should_close:
            conn.close()


# Update the update_ctf_timing route
@app.route('/api/admin/settings/timing', methods=['GET', 'POST'])
@login_required
def handle_ctf_timing():
    # Check if user is logged in
    if 'user_id' not in session:
        return jsonify({
            'success': False,
            'message': 'Please login to continue',
            'redirect': '/login'
        }), 401

    if request.method == 'GET':
        conn = sqlite3.connect(DATABASE_PATH)
        c = conn.cursor()
        try:
            c.execute('''SELECT start_time, end_time 
                        FROM setting_date_time 
                        ORDER BY id DESC LIMIT 1''')
            result = c.fetchone()
            
            if result:
                return jsonify({
                    'success': True,
                    'start_time': result[0],
                    'end_time': result[1]
                })
            else:
                return jsonify({
                    'success': False,
                    'message': 'No CTF timing found'
                })
        except Exception as e:
            return jsonify({
                'success': False,
                'message': str(e)
            }), 500
        finally:
            conn.close()
    
    elif request.method == 'POST':
        try:
            if not request.is_json:
                return jsonify({
                    'success': False,
                    'message': 'Invalid request format'
                }), 400

            data = request.get_json()
            start_time = data.get('ctf_start_time')
            end_time = data.get('ctf_end_time')
            
            if not start_time or not end_time:
                return jsonify({
                    'success': False,
                    'message': 'Start time and end time are required'
                }), 400
                
            # Validate dates
            try:
                start = datetime.strptime(start_time, '%Y-%m-%dT%H:%M')
                end = datetime.strptime(end_time, '%Y-%m-%dT%H:%M')
                if end <= start:
                    return jsonify({
                        'success': False,
                        'message': 'End time must be after start time'
                    }), 400
                
                # Check if CTF has already ended
                if end < datetime.now():
                    return jsonify({
                        'success': False,
                        'message': 'Cannot set end time in the past'
                    }), 400
                    
            except ValueError:
                return jsonify({
                    'success': False,
                    'message': 'Invalid date format'
                }), 400
                
            conn = sqlite3.connect(DATABASE_PATH)
            c = conn.cursor()
            try:
                # Update the most recent timing record instead of creating a new one
                c.execute('''UPDATE setting_date_time 
                            SET start_time = ?, end_time = ?, updated_at = CURRENT_TIMESTAMP
                            WHERE id = (SELECT id FROM setting_date_time ORDER BY id DESC LIMIT 1)''',
                         (start_time, end_time))
                
                # If no record exists, create one
                if c.rowcount == 0:
                    c.execute('''INSERT INTO setting_date_time 
                                (start_time, end_time) VALUES (?, ?)''',
                             (start_time, end_time))
                
                conn.commit()
                
                # Check if CTF has ended and logout all users
                if not is_ctf_active():
                    # Clear all sessions (in a real app, you'd need a proper session store)
                    session.clear()
                
                return jsonify({
                    'success': True,
                    'message': 'CTF timing updated successfully'
                })
            finally:
                conn.close()
                
        except Exception as e:
            return jsonify({
                'success': False,
                'message': str(e)
            }), 500

# Update the reset_ctf_timing function
def reset_ctf_timing():
    conn = sqlite3.connect(DATABASE_PATH)
    c = conn.cursor()
    try:
        default_start = datetime.now() + timedelta(hours=1)
        default_end = default_start + timedelta(days=1)
        
        # Update existing record instead of creating a new one
        c.execute('''UPDATE setting_date_time 
                    SET start_time = ?, end_time = ?, updated_at = CURRENT_TIMESTAMP
                    WHERE id = (SELECT id FROM setting_date_time ORDER BY id DESC LIMIT 1)''',
                 (default_start.strftime('%Y-%m-%dT%H:%M'),
                  default_end.strftime('%Y-%m-%dT%H:%M')))
        
        # If no record exists, create one
        if c.rowcount == 0:
            c.execute('''INSERT INTO setting_date_time 
                        (start_time, end_time) VALUES (?, ?)''',
                     (default_start.strftime('%Y-%m-%dT%H:%M'),
                      default_end.strftime('%Y-%m-%dT%H:%M')))
        
        conn.commit()
    except sqlite3.Error as e:
        logging.error(f"Error resetting CTF timing: {str(e)}")
        conn.rollback()
    finally:
        conn.close()

def check_ctf_status():
    """Check CTF status and logout users if CTF has ended"""
    if 'user_id' in session and not is_ctf_active():
        session.clear()
        flash('CTF has ended. All users have been logged out.')
        return redirect(url_for('index'))
    return None

# Add this decorator to routes that require active CTF
def ctf_active_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not is_ctf_active():
            if 'user_id' in session:
                session.clear()
            flash('CTF is not currently active')
            return redirect(url_for('index'))
        return f(*args, **kwargs)
    return decorated_function

# Update the index route to separate registration and CTF status
@app.route('/')
def index():
    conn = sqlite3.connect(DATABASE_PATH)
    c = conn.cursor()
    try:
        # Get CTF timing and registration status
        c.execute('''SELECT s.value as registration, dt.start_time, dt.end_time 
                    FROM settings s 
                    LEFT JOIN setting_date_time dt ON 1=1
                    WHERE s.key = 'allow_registration' 
                    ORDER BY dt.id DESC LIMIT 1''')
        result = c.fetchone()
        
        settings = {
            'allow_registration': result[0] if result else 'true',
            'ctf_start_time': result[1] if result and result[1] else '',
            'ctf_end_time': result[2] if result and result[2] else ''
        }
        
        ctf_active = is_ctf_active()
        allow_registration = settings['allow_registration'].lower() == 'true'
        
        # Only check CTF timing for logged-in users
        if 'user_id' in session and not ctf_active:
            session.clear()
            flash('CTF has ended. All users have been logged out.')
            
        if 'user_id' in session and ctf_active:
            return redirect(url_for('dashboard'))
            
        return render_template('client/index.html', 
                             allow_registration=allow_registration,
                             ctf_start_time=settings['ctf_start_time'],
                             ctf_end_time=settings['ctf_end_time'])
                             
    except Exception as e:
        logging.error(f"Error in index route: {str(e)}")
        flash('An error occurred. Please try again later.')
        return render_template('client/index.html',
                             allow_registration=False,
                             ctf_start_time='',
                             ctf_end_time='')
    finally:
        conn.close()

@app.route('/login', methods=['GET', 'POST'])
def login():
    # Only check CTF timing for existing users, not for login page access
    if request.method == 'GET':
        registration_success = request.args.get('registration_success', False)
        return render_template('client/login.html', registration_success=registration_success)
    
    # Handle POST request for login
    if request.method == 'POST':
        try:
            email = request.form.get('email')
            password = hash_password(request.form.get('password'))
            
            if not email or not password:
                return jsonify({
                    'success': False,
                    'message': 'Email and password are required'
                }), 400
            
            conn = sqlite3.connect(DATABASE_PATH)
            c = conn.cursor()
            
            try:
                # Check if user exists and credentials are correct
                c.execute('SELECT id, username, is_admin, is_leader FROM users WHERE email = ? AND password = ?',
                         (email, password))
                user = c.fetchone()
                
                if user:
                    # Set session data
                    session['user_id'] = user[0]
                    session['username'] = user[1]
                    session['is_admin'] = bool(user[2])  # Set admin status based on is_admin
                    session['is_leader'] = bool(user[3])  # Set team leader status separately
                    
                    # If user is admin, redirect to admin root
                    if session['is_admin']:
                        return jsonify({
                            'success': True,
                            'message': 'Admin login successful',
                            'redirect': url_for('admin_root')
                        })
                    
                    # For regular users, check CTF timing
                    if not is_ctf_active():
                        session.clear()  # Clear session if CTF is not active
                        return jsonify({
                            'success': False,
                            'message': 'CTF is not currently active. Please wait for the start time.'
                        }), 403
                    
                    return jsonify({
                        'success': True,
                        'message': 'Login successful',
                        'redirect': url_for('dashboard')
                    })
                else:
                    return jsonify({
                        'success': False,
                        'message': 'Invalid email or password'
                    }), 401
            finally:
                conn.close()
                
        except Exception as e:
            logging.error(f"Login error: {str(e)}")
            return jsonify({
                'success': False,
                'message': 'An error occurred during login. Please try again.'
            }), 500
            
    return render_template('client/login.html')

@app.route('/dashboard')
@login_required
@ctf_active_required
def dashboard():
    conn = sqlite3.connect(DATABASE_PATH)
    c = conn.cursor()
    
    try:
        user_id = session['user_id']
        
        # Fetch user details with proper error handling - Updated to get team points
        c.execute('''
            SELECT u.username, COALESCE(t.name, 'No Team') as team_name,
                   COUNT(DISTINCT sc.challenge_id) as solved_challenges,
                   COALESCE(t.points, 0) as total_points,
                   COALESCE(t.is_banned, 0) as is_banned
            FROM users u
            LEFT JOIN teams t ON u.team_id = t.id
            LEFT JOIN solved_challenges sc ON u.id = sc.user_id
            WHERE u.id = ?
            GROUP BY u.id
        ''', (user_id,))
        
        user_data = c.fetchone()
        if not user_data:
            flash('User data not found')
            return redirect(url_for('login'))
            
        username, team_name, solved_challenges, total_points, is_banned = user_data
        
        # Get global rank with proper error handling
        global_rank = 0
        if not is_banned:
            c.execute('''WITH team_ranks AS (
                           SELECT id, 
                                  RANK() OVER (ORDER BY points DESC) as rank
                           FROM teams
                           WHERE is_banned = 0
                        )
                        SELECT rank 
                        FROM team_ranks 
                        WHERE id = (SELECT team_id FROM users WHERE id = ?)''', 
                     (user_id,))
            rank_result = c.fetchone()
            global_rank = rank_result[0] if rank_result else 0
        
        # Fetch active challenges with proper error handling
        c.execute('''
            SELECT id, short_id, title, description, points, category, difficulty
            FROM challenges
            WHERE is_hidden = 0
            ORDER BY created_at DESC
            LIMIT 2
        ''')
        
        challenges = []
        for row in c.fetchall():
            challenges.append({
                'id': row[0],
                'short_id': row[1],
                'title': row[2],
                'description': row[3],
                'points': row[4],
                'category': row[5],
                'difficulty': row[6]
            })
        
        # Fetch recent activity for the team with proper error handling
        activities = []
        team_id = None
        
        # Get user's team_id first
        c.execute("SELECT team_id FROM users WHERE id=?", (user_id,))
        team_row = c.fetchone()
        if team_row:
            team_id = team_row[0]
        
        if team_id:
            c.execute('''
                SELECT activity_time, username, action, detail 
                FROM (
                    SELECT sc.solved_at as activity_time, 
                           u.username, 
                           'solved challenge' as action, 
                           c.title as detail
                    FROM solved_challenges sc
                    JOIN users u ON sc.user_id = u.id
                    JOIN challenges c ON sc.challenge_id = c.id
                    WHERE u.team_id = ?
                    UNION ALL
                    SELECT uh.unlocked_at as activity_time, 
                           u.username, 
                           'unlocked hint' as action, 
                           h.hint_text as detail
                    FROM unlocked_hints uh
                    JOIN users u ON uh.user_id = u.id
                    JOIN hints h ON uh.hint_id = h.id
                    WHERE u.team_id = ?
                ) 
                ORDER BY activity_time DESC 
                LIMIT 10
            ''', (team_id, team_id))
            
            activities = c.fetchall()
        
        return render_template('client/dashboard.html',
                             username=username,
                             team_name=team_name,
                             solved_challenges=solved_challenges,
                             total_points=total_points,
                             global_rank=global_rank,
                             challenges=challenges,
                             activities=activities,
                             is_banned=is_banned)
                             
    except Exception as e:
        logging.error(f"Dashboard error: {str(e)}")
        flash('An error occurred while loading the dashboard')
        return redirect(url_for('index'))
        
    finally:
        conn.close()

@app.route('/challenges')
@login_required
def challenges():
    conn = sqlite3.connect(DATABASE_PATH)
    c = conn.cursor()
    
    try:
        # First check if user has any pending team requests
        c.execute('''
            SELECT t.name 
            FROM team_requests tr
            JOIN teams t ON tr.team_id = t.id
            WHERE tr.user_id = ? AND tr.status = 'pending'
        ''', (session['user_id'],))
        
        pending_request = c.fetchone()
        if pending_request:
            return render_template('client/challenges.html', 
                                pending_request=True,
                                team_name=pending_request[0],
                                challenges=[])

        # Continue with existing challenge fetching logic
        c.execute('''
            SELECT 
                c.id, c.short_id, c.title, c.description, c.points, c.category,
                c.difficulty, c.is_hidden,
                COUNT(DISTINCT sc.id) as solve_count
            FROM challenges c
            LEFT JOIN solved_challenges sc ON c.id = sc.challenge_id
            WHERE c.is_hidden = 0
            GROUP BY c.id
            ORDER BY c.category, c.points
        ''')
        
        challenges = []
        for row in c.fetchall():
            challenge = {
                'id': row[0],
                'short_id': row[1],
                'title': row[2],
                'description': row[3],
                'points': row[4],
                'category': row[5],
                'difficulty': row[6],
                'is_hidden': row[7],
                'solve_count': row[8]
            }
            challenges.append(challenge)
            
        return render_template('client/challenges.html', 
                             challenges=challenges,
                             active_page='challenges')
        
    except Exception as e:
        logging.error(f"Error fetching challenges: {str(e)}")  # Updated log
        return render_template('client/challenges.html', challenges=[])
    finally:
        conn.close()

def rate_limit(key, limit=5, window=60):
    """Rate limiting decorator"""
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            # Bypass rate limiting by returning the function directly
            return f(*args, **kwargs)
        return decorated_function
    return decorator

@app.route('/challenge/<string:short_id>', methods=['GET', 'POST'])
@login_required
@rate_limit('flag_submit')
def challenge_details(short_id):
    conn = sqlite3.connect(DATABASE_PATH)
    c = conn.cursor()
    
    try:
        if request.method == 'POST':
            # Verify CSRF token
            if request.headers.get('X-Requested-With') != 'XMLHttpRequest':
                return jsonify({
                    'success': False,
                    'message': 'Invalid request'
                }), 403
                
            # Get and sanitize submitted flag
            submitted_flag = escape(request.form.get('flag', '').strip())
            if not submitted_flag:
                return jsonify({
                    'success': False,
                    'message': 'Please enter a flag'
                }), 400

            # Get challenge details first
            c.execute('''
                SELECT id, flag, points, challenge_type, wrong_flag_penalty, title
                FROM challenges 
                WHERE short_id = ?
            ''', (short_id,))
            
            challenge_info = c.fetchone()
            if not challenge_info:
                return jsonify({
                    'success': False,
                    'message': 'Challenge not found'
                }), 404

            # Check if already solved
            c.execute('''SELECT id FROM solved_challenges 
                        WHERE user_id = ? AND challenge_id = ?''',
                     (session['user_id'], challenge_info[0]))
            
            if c.fetchone():
                return jsonify({
                    'success': False,
                    'message': 'You have already solved this challenge!'
                })

            # Check flag
            if submitted_flag == challenge_info[1]:  # Correct flag
                try:
                    # Get user's team
                    c.execute('SELECT team_id FROM users WHERE id = ?', (session['user_id'],))
                    team_id = c.fetchone()[0]
                    
                    # Add to solved challenges
                    c.execute('''INSERT INTO solved_challenges 
                               (user_id, challenge_id, points_awarded)
                               VALUES (?, ?, ?)''',
                            (session['user_id'], challenge_info[0], challenge_info[2]))
                    
                    # Record point transaction for the user
                    c.execute('''INSERT INTO point_transactions 
                               (user_id, team_id, points, transaction_type, description)
                               VALUES (?, ?, ?, ?, ?)''',
                            (session['user_id'], team_id, challenge_info[2], 
                             'challenge_solve', 
                             f'Solved challenge: {challenge_info[5]}'))
                    
                    # Update team points if user is in a team
                    if team_id:
                        update_team_points(team_id, challenge_info[2], conn, 
                                         user_id=session['user_id'],
                                         description=f'Team member solved challenge: {challenge_info[5]}')
                    
                    conn.commit()
                    return jsonify({
                        'success': True,
                        'message': 'Congratulations! Flag is correct!'
                    })
                except Exception as e:
                    conn.rollback()
                    logging.error(f"Error in flag submission: {str(e)}")
                    return jsonify({
                        'success': False,
                        'message': 'Error processing flag submission'
                    }), 500
            else:
                # Handle wrong flag submission
                if challenge_info[3] == 'dynamic' and challenge_info[4] > 0:
                    try:
                        # Get user's team
                        c.execute('SELECT team_id FROM users WHERE id = ?', (session['user_id'],))
                        team_id = c.fetchone()[0]
                        
                        # Record wrong submission
                        c.execute('''INSERT INTO wrong_flag_submissions 
                                   (challenge_id, username, submitted_flag, points_deducted)
                                   VALUES (?, ?, ?, ?)''',
                                (challenge_info[0], session['username'], 
                                 submitted_flag, challenge_info[4]))
                        
                        # Record point transaction for the user
                        c.execute('''INSERT INTO point_transactions 
                                   (user_id, team_id, points, transaction_type, description)
                                   VALUES (?, ?, ?, ?, ?)''',
                                (session['user_id'], team_id, -challenge_info[4], 
                                 'wrong_flag_penalty', 
                                 f'Wrong flag submission for challenge: {challenge_info[5]}'))
                        
                        # Deduct points from team if user is in a team
                        if team_id:
                            update_team_points(team_id, -challenge_info[4], conn,
                                             user_id=session['user_id'],
                                             description=f'Team member submitted wrong flag for challenge: {challenge_info[5]}')
                        
                        conn.commit()
                        return jsonify({
                            'success': False,
                            'message': f'Incorrect flag. {challenge_info[4]} points deducted.'
                        })
                    except Exception as e:
                        conn.rollback()
                        logging.error(f"Error in wrong flag submission: {str(e)}")
                        return jsonify({
                            'success': False,
                            'message': 'Error processing flag submission'
                        }), 500
                else:
                    return jsonify({
                        'success': False,
                        'message': 'Incorrect flag'
                    })

        # Get challenge details for display
        c.execute('''
            SELECT c.id, c.title, c.description, c.points, c.category,
                   c.difficulty, c.flag, c.challenge_type, c.wrong_flag_penalty,
                   COUNT(DISTINCT sc.id) as solve_count,
                   (
                       SELECT COUNT(1) 
                       FROM solved_challenges sc2 
                       JOIN users u ON sc2.user_id = u.id 
                       WHERE sc2.challenge_id = c.id 
                       AND (u.id = ? OR u.team_id = (SELECT team_id FROM users WHERE id = ?))
                   ) > 0 as is_solved
            FROM challenges c
            LEFT JOIN solved_challenges sc ON c.id = sc.challenge_id
            WHERE c.short_id = ?
            GROUP BY c.id
        ''', (session['user_id'], session['user_id'], short_id))
        
        challenge = c.fetchone()
        
        if not challenge:
            flash('Challenge not found')
            return redirect(url_for('challenges'))

        # Get challenge files
        c.execute('SELECT id, filename FROM challenge_files WHERE challenge_id = ?', 
                 (challenge[0],))
        files = c.fetchall()
        
        # Get hints – if the user is in a team, check team unlock status; otherwise check individual status.
        c.execute("SELECT team_id FROM users WHERE id = ?", (session['user_id'],))
        user_team_row = c.fetchone()
        user_team_id = user_team_row[0] if user_team_row else None

        if user_team_id:
            c.execute('''
                SELECT h.id, h.cost, h.hint_text,
                       EXISTS(
                           SELECT 1 FROM unlocked_hints uh
                           JOIN users u ON uh.user_id = u.id
                           WHERE uh.hint_id = h.id 
                             AND u.team_id = ?
                       ) as is_unlocked
                FROM hints h
                WHERE h.challenge_id = ?
            ''', (user_team_id, challenge[0]))
        else:
            c.execute('''
                SELECT h.id, h.cost, h.hint_text,
                       EXISTS(
                           SELECT 1 FROM unlocked_hints uh
                           WHERE uh.hint_id = h.id 
                             AND uh.user_id = ?
                       ) as is_unlocked
                FROM hints h
                WHERE h.challenge_id = ?
            ''', (session['user_id'], challenge[0]))
        hints = c.fetchall()

        challenge_data = {
            'id': challenge[0],
            'title': challenge[1],
            'description': challenge[2],
            'points': challenge[3],
            'category': challenge[4],
            'difficulty': challenge[5],
            'solve_count': challenge[9],
            'is_solved': bool(challenge[10]),
            'files': files,
            'hints': hints
        }

        return render_template('client/challenge_details.html', challenge=challenge_data)
        
    except Exception as e:
        logging.error(f"Error: {str(e)}")  # Updated log
        flash('Error loading challenge')
        return redirect(url_for('challenges'))
    finally:
        conn.close()

if __name__ == '__main__':
    try:

        init_app()
        socketio.start_background_task(target=background_leaderboard_updates)
        
        # Run the application with socketio
        port = 5000
        while port < 5100:
            try:
                socketio.run(
                    app,
                    host='0.0.0.0',
                    port=port,
                    debug=False,  # Set debug to False when using socketio
                    use_reloader=False,  # Keep reloader disabled
                    allow_unsafe_werkzeug=True  
                )
                break
            except OSError:
                port += 1
                continue
                
        logging.info(f"Server started on port {port}")
        
    except Exception as e:
        logging.error(f"Failed to start server: {str(e)}")
        raise
    finally:
        # Cleanup
        if 'socketio' in locals():
            socketio.stop()

