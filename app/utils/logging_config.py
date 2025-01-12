# app/utils/logging_config.py
import logging
import logging.config
import os
from decouple import config

def setup_logging():
    """Configure logging based on environment."""
    # Get environment variables
    environment = config('ENVIRONMENT', default='production')
    log_level = config('LOG_LEVEL', default='INFO')

    # Convert string log level to logging constant
    numeric_level = getattr(logging, log_level.upper(), logging.INFO)

    # Define formatters based on environment
    if environment == 'development':
        console_formatter = {
            'format': '%(asctime)s - %(name)s - %(levelname)s - [%(filename)s:%(lineno)d] - %(message)s',
            'datefmt': '%Y-%m-%d %H:%M:%S'
        }
        file_formatter = console_formatter
    else:
        console_formatter = {
            'format': '%(levelname)s - %(message)s'
        }
        file_formatter = {
            'format': '%(asctime)s - %(levelname)s - %(message)s',
            'datefmt': '%Y-%m-%d %H:%M:%S'
        }

    # Logging configuration
    log_config = {
        'version': 1,
        'disable_existing_loggers': False,
        'formatters': {
            'console': console_formatter,
            'file': file_formatter
        },
        'handlers': {
            'console': {
                'class': 'logging.StreamHandler',
                'level': 'DEBUG' if environment == 'development' else 'INFO',
                'formatter': 'console',
                'stream': 'ext://sys.stdout'
            },
            'file': {
                'class': 'logging.handlers.RotatingFileHandler',
                'level': 'INFO',
                'formatter': 'file',
                'filename': os.path.join('app_data', 'app.log'),
                'maxBytes': 10485760,  # 10MB
                'backupCount': 5
            }
        },
        'loggers': {
            '': {  # Root logger
                'handlers': ['console', 'file'],
                'level': numeric_level,
                'propagate': True
            },
            'sqlalchemy.engine': {  # SQL logging
                'handlers': ['console', 'file'],
                'level': 'DEBUG' if environment == 'development' else 'WARNING',
                'propagate': False
            }
        }
    }

    # Ensure log directory exists
    os.makedirs('app_data', exist_ok=True)

    # Apply configuration
    logging.config.dictConfig(log_config)

    # Log startup message
    logger = logging.getLogger(__name__)
    logger.info(f'Logging configured for {environment} environment at {log_level} level')