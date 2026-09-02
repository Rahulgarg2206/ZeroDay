import os

# Configuration settings for the application
class Config:
    SECRET_KEY = os.environ.get('SECRET_KEY') or 'your_secret_key_here'
    DATABASE_PATH = os.environ.get('DATABASE_PATH') or 'path/to/your/database.db'
    
    # Email server configuration
    MAIL_SERVER = 'smtp.randomguy.live'
    MAIL_PORT = 587
    MAIL_USE_TLS = True
    MAIL_USERNAME = 'no-reply@randomguy.live'
    MAIL_PASSWORD = os.environ.get('MAIL_PASSWORD') or 'your_email_password_here'
    MAIL_DEFAULT_SENDER = 'no-reply@randomguy.live'