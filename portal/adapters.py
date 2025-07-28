# portal/adapters.py

from allauth.account.adapter import DefaultAccountAdapter
from django.utils.text import slugify


class CustomAccountAdapter(DefaultAccountAdapter):

    def populate_username(self, request, user):
        """
        Создает уникальный username из email, чтобы избежать конфликтов.
        """
        email = user.email
        username = slugify(email.split('@')[0])

        # Убеждаемся, что username уникален
        original_username = username
        i = 1
        while user.__class__.objects.filter(username=username).exists():
            username = f"{original_username}{i}"
            i += 1

        user.username = username