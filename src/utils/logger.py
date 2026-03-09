import logging
import os
import uuid
from datetime import datetime
from contextvars import ContextVar

run_id: ContextVar[str] = ContextVar("run_id", default="N/A")

class RunIDFilter(logging.Filter):
    def filter(self, record):
        record.run_id = run_id.get()
        return True

def setup_logger():
    os.makedirs("logs", exist_ok=True)
    
    # Console Handler
    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.INFO)
    
    # File Handler
    file_handler = logging.FileHandler(
        f"logs/{datetime.now().strftime('%Y-%m-%d')}.log",
        encoding="utf-8"
    )
    file_handler.setLevel(logging.DEBUG)

    fmt = logging.Formatter(
        "%(asctime)s | RUN:%(run_id)s | %(name)s | %(levelname)s | %(message)s"
    )
    
    console_handler.setFormatter(fmt)
    file_handler.setFormatter(fmt)

    run_filter = RunIDFilter()
    console_handler.addFilter(run_filter)
    file_handler.addFilter(run_filter)

    logger = logging.getLogger()
    logger.setLevel(logging.DEBUG)
    
    # Remove existing handlers to avoid duplicates
    if logger.hasHandlers():
        logger.handlers.clear()
        
    logger.addHandler(console_handler)
    logger.addHandler(file_handler)

    return logger

def get_logger(name: str):
    return logging.getLogger(name)
