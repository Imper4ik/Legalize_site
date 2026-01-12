"""
Настройки для тестовой среды.
Используют SQLite для быстрого выполнения тестов.
"""

from .base import *

# Переопределяем DEBUG для тестов
DEBUG = True

# Используем SQLite для тестов (быстрее PostgreSQL)
DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.sqlite3',
        'NAME': ':memory:',  # In-memory база для ускорения тестов
    }
}

# Упрощенное хеширование паролей для ускорения тестов
PASSWORD_HASHERS = [
    'django.contrib.auth.hashers.MD5PasswordHasher',
]

# Отключаем email для тестов
EMAIL_BACKEND = 'django.core.mail.backends.locmem.EmailBackend'

# Отключаем миграции для ускорения (опционально)
# class DisableMigrations:
#     def __contains__(self, item):
#         return True
#     def __getitem__(self, item):
#         return None
# MIGRATION_MODULES = DisableMigrations()
