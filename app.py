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

