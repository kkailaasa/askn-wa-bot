import structlog
import logging
from typing import Union
from logging.handlers import RotatingFileHandler
from pathlib import Path

def configure_logging(debug: bool = False) -> Union[structlog.BoundLogger, logging.Logger]:
    """Configure logging for the application"""
    # Create logs directory if it doesn't exist
    Path("logs").mkdir(exist_ok=True)

    # Set up basic logging configuration
    logging.basicConfig(
        level=logging.DEBUG if debug else logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        handlers=[
            RotatingFileHandler(
                'logs/app.log',
                maxBytes=10000000,  # 10MB
                backupCount=5
            ),
            logging.StreamHandler()
        ]
    )

    # Configure structlog
    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.processors.add_log_level,
            structlog.processors.StackInfoRenderer(),
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.processors.format_exc_info,
            structlog.processors.JSONRenderer()
        ],
        wrapper_class=structlog.make_filtering_bound_logger(
            logging.DEBUG if debug else logging.INFO
        ),
        context_class=dict,
        logger_factory=structlog.PrintLoggerFactory(),
        cache_logger_on_first_use=True
    )

    return structlog.get_logger()
