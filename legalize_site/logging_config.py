"""
Настройки логирования для Django проекта.

Логи пишутся в:
- stdout/stderr для Railway (автоматически собирается)
- файлы logs/ для локальной разработки
"""

import os
from pathlib import Path

# Build paths
BASE_DIR = Path(__file__).resolve().parent.parent


def get_logging_config(debug=False):
    """
    Конфигурация логирования.
    
    Args:
        debug: Если True, логи более подробные (DEBUG level)
    """
    
    # Создаем директорию для логов (только локально)
    logs_dir = BASE_DIR / 'logs'
    if not logs_dir.exists() and not os.getenv('RAILWAY_ENVIRONMENT'):
        logs_dir.mkdir(exist_ok=True)
    
    log_level = 'DEBUG' if debug else 'INFO'
    
    config = {
        'version': 1,
        'disable_existing_loggers': False,
        
        # Форматы
        'formatters': {
            'verbose': {
                'format': '[{levelname}] {asctime} {name} {module}.{funcName}: {message}',
                'style': '{',
                'datefmt': '%Y-%m-%d %H:%M:%S',
            },
            'simple': {
                'format': '[{levelname}] {message}',
                'style': '{',
            },
            'json': {
                '()': 'pythonjsonlogger.jsonlogger.JsonFormatter',
                'format': '%(asctime)s %(name)s %(levelname)s %(message)s',
            } if not debug else {
                'format': '[{levelname}] {asctime} {name}: {message}',
                'style': '{',
            },
        },
        
        # Обработчики
        'handlers': {
            'console': {
                'level': log_level,
                'class': 'logging.StreamHandler',
                'formatter': 'verbose',
            },
            'file_app': {
                'level': 'INFO',
                'class': 'logging.handlers.RotatingFileHandler',
                'filename': logs_dir / 'app.log' if not os.getenv('RAILWAY_ENVIRONMENT') else '/dev/null',
                'maxBytes': 1024 * 1024 * 10,  # 10 MB
                'backupCount': 5,
                'formatter': 'verbose',
            },
            'file_errors': {
                'level': 'ERROR',
                'class': 'logging.handlers.RotatingFileHandler',
                'filename': logs_dir / 'errors.log' if not os.getenv('RAILWAY_ENVIRONMENT') else '/dev/null',
                'maxBytes': 1024 * 1024 * 10,  # 10 MB
                'backupCount': 5,
                'formatter': 'verbose',
            },
            'file_security': {
                'level': 'WARNING',
                'class': 'logging.handlers.RotatingFileHandler',
                'filename': logs_dir / 'security.log' if not os.getenv('RAILWAY_ENVIRONMENT') else '/dev/null',
                'maxBytes': 1024 * 1024 * 10,  # 10 MB
                'backupCount': 5,
                'formatter': 'verbose',
            },
        },
        
        # Логгеры
        'loggers': {
            # Django
            'django': {
                'handlers': ['console', 'file_app'],
                'level': 'INFO',
                'propagate': False,
            },
            'django.request': {
                'handlers': ['console', 'file_errors'],
                'level': 'ERROR',
                'propagate': False,
            },
            'django.security': {
                'handlers': ['console', 'file_security'],
                'level': 'WARNING',
                'propagate': False,
            },
            'django.db.backends': {
                'handlers': ['console'],
                'level': 'DEBUG' if debug else 'INFO',
                'propagate': False,
            },
            
            # Наше приложение
            'clients': {
                'handlers': ['console', 'file_app', 'file_errors'],
                'level': log_level,
                'propagate': False,
            },
            'submissions': {
                'handlers': ['console', 'file_app', 'file_errors'],
                'level': log_level,
                'propagate': False,
            },
            'core': {
                'handlers': ['console', 'file_app', 'file_errors'],
                'level': log_level,
                'propagate': False,
            },
            
            # Root logger
            '': {
                'handlers': ['console', 'file_app'],
                'level': log_level,
            },
        },
    }
    
    return config


# Примеры использования в коде:
"""
# В любом файле проекта:

import logging

logger = logging.getLogger(__name__)

# Информационные сообщения
logger.info("Client created", extra={
    'client_id': client.id,
    'email': client.email,
    'purpose': client.application_purpose
})

# Предупреждения
logger.warning("Payment overdue", extra={
    'payment_id': payment.id,
    'days_overdue': days
})

# Ошибки
logger.error("OCR failed", extra={
    'document_id': doc.id,
    'error': str(e)
}, exc_info=True)

# Критические ошибки
logger.critical("Database connection lost!", exc_info=True)

# Debug (только в DEBUG=True)
logger.debug("Query executed", extra={
    'query': query,
    'duration_ms': duration
})
"""
