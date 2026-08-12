import logging
import sys
from pathlib import Path
from logging.handlers import RotatingFileHandler

def setup_logger(name: str = "adforge", log_level: int = logging.INFO) -> logging.Logger:
    logger = logging.getLogger(name)
    
    # If logger already has handlers, return it to avoid duplicate logs
    if logger.handlers:
        return logger
        
    logger.setLevel(log_level)
    
    # Format: [TIME] [LEVEL] [MODULE] - MESSAGE
    formatter = logging.Formatter(
        fmt="%(asctime)s [%(levelname)s] [%(name)s] - %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S"
    )
    
    # Console Handler
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)
    
    # File Handler
    log_dir = Path(__file__).resolve().parent.parent / "logs"
    log_dir.mkdir(exist_ok=True)
    
    file_handler = RotatingFileHandler(
        log_dir / f"{name}.log", 
        maxBytes=5*1024*1024, # 5MB
        backupCount=3,
        encoding='utf-8'
    )
    file_handler.setFormatter(formatter)
    logger.addHandler(file_handler)
    
    return logger

logger = setup_logger()
