import logging
import os
from datetime import datetime
from pathlib import Path


class LoggerConfig:
    """Configuration for logging setup"""
    # Log level: DEBUG, INFO, WARNING, ERROR, CRITICAL
    LOG_LEVEL = logging.INFO
    
    # Log format with more details
    LOG_FORMAT = (
        "[ %(asctime)s ] | %(name)s | %(levelname)-8s | "
        "%(filename)s:%(funcName)s:%(lineno)d | %(message)s"
    )
    
    # Date format for log file and timestamps
    DATE_FORMAT = "%Y-%m-%d %H:%M:%S"
    
    # Log directory
    LOGS_DIR = os.path.join(os.getcwd(), "logs")


def setup_logger(name: str = None, log_level: int = None) -> logging.Logger:
    """
    Set up a logger with file and console handlers.
    
    Args:
        name (str): Logger name (typically __name__)
        log_level (int): Logging level (default: INFO)
    
    Returns:
        logging.Logger: Configured logger instance
    
    Example:
        logger = setup_logger(__name__)
        logger.info("Application started")
    """
    # Use provided log level or default
    level = log_level or LoggerConfig.LOG_LEVEL
    
    # Create logger
    logger = logging.getLogger(name or __name__)
    logger.setLevel(level)
    
    # Avoid duplicate handlers if logger already configured
    if logger.handlers:
        return logger
    
    # Create logs directory
    logs_dir = Path(LoggerConfig.LOGS_DIR)
    logs_dir.mkdir(parents=True, exist_ok=True)
    
    # Generate log file path with timestamp
    timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    log_file = logs_dir / f"app_{timestamp}.log"
    
    # Create formatter
    formatter = logging.Formatter(
        LoggerConfig.LOG_FORMAT,
        datefmt=LoggerConfig.DATE_FORMAT
    )
    
    # File handler - logs all messages
    try:
        file_handler = logging.FileHandler(log_file, encoding='utf-8')
        file_handler.setLevel(level)
        file_handler.setFormatter(formatter)
        logger.addHandler(file_handler)
    except Exception as e:
        print(f"Error setting up file handler: {e}")
    
    # Console handler - logs all to console
    console_handler = logging.StreamHandler()
    console_handler.setLevel(level)
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)
    
    # Prevent propagation to root logger
    logger.propagate = False
    
    return logger


# Initialize default logger for module-level logging
logger = setup_logger("churn_prediction")
