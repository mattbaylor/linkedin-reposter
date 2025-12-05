"""Enhanced logging configuration for LinkedIn Reposter."""
import logging
import sys
from typing import Optional
from datetime import datetime


class ColoredFormatter(logging.Formatter):
    """Custom formatter with color coding and emojis for different log levels."""
    
    # ANSI color codes
    COLORS = {
        'DEBUG': '\033[36m',      # Cyan
        'INFO': '\033[32m',       # Green
        'WARNING': '\033[33m',    # Yellow
        'ERROR': '\033[31m',      # Red
        'CRITICAL': '\033[35m',   # Magenta
        'RESET': '\033[0m'        # Reset
    }
    
    # Emojis for log levels
    EMOJIS = {
        'DEBUG': '🔍',
        'INFO': 'ℹ️ ',
        'WARNING': '⚠️ ',
        'ERROR': '❌',
        'CRITICAL': '🔥'
    }
    
    def format(self, record):
        # Add color and emoji
        color = self.COLORS.get(record.levelname, self.COLORS['RESET'])
        emoji = self.EMOJIS.get(record.levelname, '')
        reset = self.COLORS['RESET']
        
        # Format the message
        record.emoji = emoji
        record.color = color
        record.reset = reset
        
        return super().format(record)


def setup_logging(log_level: str = "INFO", log_file: Optional[str] = None) -> None:
    """
    Configure application-wide logging.
    
    Args:
        log_level: Logging level (DEBUG, INFO, WARNING, ERROR, CRITICAL)
        log_file: Optional file path to write logs to
    """
    # Get root logger
    root_logger = logging.getLogger()
    root_logger.setLevel(getattr(logging, log_level.upper()))
    
    # Remove existing handlers
    root_logger.handlers.clear()
    
    # Console handler with colors
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(getattr(logging, log_level.upper()))
    
    console_format = '%(color)s%(emoji)s %(asctime)s - %(name)s - %(levelname)s%(reset)s - %(message)s'
    console_formatter = ColoredFormatter(
        console_format,
        datefmt='%Y-%m-%d %H:%M:%S'
    )
    console_handler.setFormatter(console_formatter)
    root_logger.addHandler(console_handler)
    
    # File handler (if specified)
    if log_file:
        file_handler = logging.FileHandler(log_file)
        file_handler.setLevel(logging.DEBUG)  # Always log everything to file
        
        file_format = '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
        file_formatter = logging.Formatter(
            file_format,
            datefmt='%Y-%m-%d %H:%M:%S'
        )
        file_handler.setFormatter(file_formatter)
        root_logger.addHandler(file_handler)
    
    # Reduce noise from third-party libraries
    logging.getLogger('httpx').setLevel(logging.WARNING)
    logging.getLogger('httpcore').setLevel(logging.WARNING)
    logging.getLogger('urllib3').setLevel(logging.WARNING)
    logging.getLogger('sqlalchemy.engine').setLevel(logging.WARNING)
    
    # Set our app loggers to be more verbose in debug mode
    if log_level.upper() == 'DEBUG':
        logging.getLogger('app').setLevel(logging.DEBUG)
        logging.getLogger('sqlalchemy.engine').setLevel(logging.INFO)


def log_operation_start(logger: logging.Logger, operation: str, **kwargs) -> None:
    """
    Log the start of an operation with context.
    
    Args:
        logger: Logger instance
        operation: Name of the operation
        **kwargs: Additional context to log
    """
    context = ' '.join([f"{k}={v}" for k, v in kwargs.items()])
    logger.info(f"▶️  Starting: {operation} {context}")


def log_operation_success(logger: logging.Logger, operation: str, duration: Optional[float] = None, **kwargs) -> None:
    """
    Log successful completion of an operation.
    
    Args:
        logger: Logger instance
        operation: Name of the operation
        duration: Optional duration in seconds
        **kwargs: Additional context to log
    """
    context = ' '.join([f"{k}={v}" for k, v in kwargs.items()])
    duration_str = f" (took {duration:.2f}s)" if duration else ""
    logger.info(f"✅ Completed: {operation}{duration_str} {context}")


def log_operation_error(logger: logging.Logger, operation: str, error: Exception, **kwargs) -> None:
    """
    Log an operation error with full context.
    
    Args:
        logger: Logger instance
        operation: Name of the operation
        error: Exception that occurred
        **kwargs: Additional context to log
    """
    context = ' '.join([f"{k}={v}" for k, v in kwargs.items()])
    logger.error(f"❌ Failed: {operation} - {type(error).__name__}: {error} {context}", exc_info=True)


def log_database_operation(logger: logging.Logger, operation: str, table: str, record_id: Optional[int] = None, **kwargs) -> None:
    """
    Log a database operation.
    
    Args:
        logger: Logger instance
        operation: Type of operation (INSERT, UPDATE, DELETE, SELECT)
        table: Table name
        record_id: Optional record ID
        **kwargs: Additional context
    """
    context = ' '.join([f"{k}={v}" for k, v in kwargs.items()])
    id_str = f" id={record_id}" if record_id else ""
    logger.debug(f"🗄️  DB {operation}: {table}{id_str} {context}")


def log_api_call(logger: logging.Logger, method: str, url: str, status_code: Optional[int] = None, **kwargs) -> None:
    """
    Log an external API call.
    
    Args:
        logger: Logger instance
        method: HTTP method
        url: API endpoint
        status_code: Response status code (if available)
        **kwargs: Additional context
    """
    context = ' '.join([f"{k}={v}" for k, v in kwargs.items()])
    status_str = f" → {status_code}" if status_code else ""
    logger.info(f"🌐 API {method} {url}{status_str} {context}")


def log_workflow_step(logger: logging.Logger, step: str, post_id: Optional[int] = None, **kwargs) -> None:
    """
    Log a workflow step for a post.
    
    Args:
        logger: Logger instance
        step: Workflow step name
        post_id: Optional post ID being processed
        **kwargs: Additional context
    """
    context = ' '.join([f"{k}={v}" for k, v in kwargs.items()])
    post_str = f"[Post {post_id}]" if post_id else ""
    logger.info(f"📋 Workflow {post_str}: {step} {context}")
