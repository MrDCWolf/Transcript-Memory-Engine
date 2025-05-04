"""Logging configuration for the Transcript Memory Engine application.
"""

import logging
import sys

# Define log level based on environment (e.g., from settings, but hardcoded for now)
# TODO: Make log level configurable via Settings
LOG_LEVEL = logging.DEBUG # Or logging.INFO in production

# Define logging format
LOG_FORMAT = "%(asctime)s - %(name)s:%(lineno)d - %(levelname)s - %(message)s"
DATE_FORMAT = "%Y-%m-%d %H:%M:%S"

# Basic formatter
formatter = logging.Formatter(LOG_FORMAT, datefmt=DATE_FORMAT)

# Console handler
console_handler = logging.StreamHandler(sys.stdout)
console_handler.setFormatter(formatter)
console_handler.setLevel(LOG_LEVEL)

# Define the dictionary configuration
LOGGING_CONFIG = {
    "version": 1,
    "disable_existing_loggers": False, # Keep existing loggers (e.g., uvicorn)
    "formatters": {
        "default": {
            "format": LOG_FORMAT,
            "datefmt": DATE_FORMAT,
        },
    },
    "handlers": {
        "console": {
            "level": LOG_LEVEL,
            "class": "logging.StreamHandler",
            "formatter": "default",
            "stream": "ext://sys.stdout", # Redirect to stdout
        },
        # Add file handler here if needed later
        # "file": {
        #     "level": LOG_LEVEL,
        #     "class": "logging.handlers.RotatingFileHandler",
        #     "formatter": "default",
        #     "filename": "./logs/app.log", # Configure path
        #     "maxBytes": 10485760,  # 10MB
        #     "backupCount": 3,
        #     "encoding": "utf8"
        # }
    },
    "loggers": {
        # Root logger configuration
        "": { 
            "handlers": ["console"], # Add "file" here to also log to file
            "level": LOG_LEVEL,
            "propagate": True, # Allow propagation to higher-level loggers
        },
        # Specific logger levels (optional)
        "uvicorn.error": {
            "level": logging.INFO, # Uvicorn error logs
            "handlers": ["console"],
            "propagate": False,
        },
        "uvicorn.access": {
            "level": logging.WARNING, # Reduce verbosity of access logs
            "handlers": ["console"], 
            "propagate": False,
        },
        "httpx": {
             "level": logging.WARNING, # Reduce verbosity from httpx library
             "handlers": ["console"],
             "propagate": False,
        },
        "chromadb": {
            "level": logging.WARNING, # Reduce verbosity from chromadb library
            "handlers": ["console"],
            "propagate": False,
        },
        "sentence_transformers": {
            "level": logging.WARNING, # Reduce verbosity from sentence_transformers
            "handlers": ["console"],
            "propagate": False,
        }
        # Add other library-specific levels as needed
    }
} 