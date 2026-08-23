import os
import logging

class Config:
    # Basic Flask config
    SECRET_KEY = os.environ.get('SECRET_KEY', os.urandom(24))
    
    # Upload settings
    UPLOAD_FOLDER = 'uploads'
    MAX_CONTENT_LENGTH = 50 * 1024 * 1024  # 50MB max file size
    
    # Mail settings
    MAIL_SERVER = os.environ.get('MAIL_SERVER', 'smtp.gmail.com')
    MAIL_PORT = int(os.environ.get('MAIL_PORT', 465))
    MAIL_USE_TLS = os.environ.get('MAIL_USE_TLS', 'False').lower() == 'true'
    MAIL_USE_SSL = os.environ.get('MAIL_USE_SSL', 'True').lower() == 'true'
    MAIL_USERNAME = os.environ.get('MAIL_USERNAME', '')
    MAIL_PASSWORD = os.environ.get('MAIL_PASSWORD', '')
    MAIL_DEFAULT_SENDER = os.environ.get('MAIL_DEFAULT_SENDER', 'no-reply@randomguy.live')
    MAIL_MAX_EMAILS = 5500
    MAIL_TIMEOUT = 10
    
    # OTP settings
    OTP_EXPIRY_MINUTES = 10

    # Configure logging
    LOG_FORMAT = '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    LOG_FILE = 'app.log'
    LOG_LEVEL = logging.INFO

    @staticmethod
    def init_app(app):
        # Set up logging
        logging.basicConfig(
            filename=Config.LOG_FILE,
            level=Config.LOG_LEVEL,
            format=Config.LOG_FORMAT,
            datefmt='%Y-%m-%d %H:%M:%S'
        )
