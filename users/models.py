from __future__ import annotations

import hashlib

from django.contrib.auth.models import AbstractUser, Group, Permission, UserManager as DjangoUserManager
from django.db import models
from django.utils.text import slugify
from django.utils.translation import gettext_lazy as _


class EmailUserManager(DjangoUserManager):
    use_in_migrations = True

    def _resolve_email(self, email: str | None, extra_fields: dict[str, object]) -> str:
        explicit_username = extra_fields.get("username")
        candidate = email or extra_fields.get("email")
        if not candidate and isinstance(explicit_username, str) and "@" in explicit_username:
            candidate = explicit_username
        if not candidate:
            raise ValueError("The given email must be set")
        return self.normalize_email(str(candidate))

    def _resolve_username(self, email: str, extra_fields: dict[str, object]) -> str:
        explicit_username = extra_fields.get("username")
        if explicit_username:
            return self.model.normalize_username(str(explicit_username))
        return self.model.build_technical_username(email)

    def create_user(self, email: str | None = None, password: str | None = None, **extra_fields):
        extra_fields.setdefault("is_staff", False)
        extra_fields.setdefault("is_superuser", False)
        resolved_email = self._resolve_email(email, extra_fields)
        resolved_username = self._resolve_username(resolved_email, extra_fields)
        return super()._create_user(resolved_username, resolved_email, password, **extra_fields)

    def create_superuser(self, email: str | None = None, password: str | None = None, **extra_fields):
        extra_fields.setdefault("is_staff", True)
        extra_fields.setdefault("is_superuser", True)

        if extra_fields.get("is_staff") is not True:
            raise ValueError("Superuser must have is_staff=True.")
        if extra_fields.get("is_superuser") is not True:
            raise ValueError("Superuser must have is_superuser=True.")

        resolved_email = self._resolve_email(email, extra_fields)
        resolved_username = self._resolve_username(resolved_email, extra_fields)
        return super()._create_user(resolved_username, resolved_email, password, **extra_fields)


class User(AbstractUser):
    username = models.CharField(_("technical username"), max_length=150, unique=True, blank=True)
    email = models.EmailField(_("email address"), unique=True)
    groups = models.ManyToManyField(
        Group,
        verbose_name=_("groups"),
        blank=True,
        help_text=_("The groups this user belongs to. A user will get all permissions granted to each of their groups."),
        related_name="user_set",
        related_query_name="user",
        db_table="auth_user_groups",
    )
    user_permissions = models.ManyToManyField(
        Permission,
        verbose_name=_("user permissions"),
        blank=True,
        help_text=_("Specific permissions for this user."),
        related_name="user_set",
        related_query_name="user",
        db_table="auth_user_user_permissions",
    )

    USERNAME_FIELD = "email"
    REQUIRED_FIELDS: list[str] = []

    objects = EmailUserManager()

    class Meta:
        db_table = "auth_user"
        verbose_name = _("user")
        verbose_name_plural = _("users")

    @classmethod
    def build_technical_username(cls, email: str) -> str:
        normalized_email = email.strip().casefold()
        local_part = normalized_email.partition("@")[0]
        slug = slugify(local_part) or "user"
        digest = hashlib.sha1(normalized_email.encode("utf-8")).hexdigest()[:12]
        max_slug_length = 150 - len(digest) - 1
        return f"{slug[:max_slug_length]}-{digest}"

    def clean(self):
        super().clean()
        self.email = self.__class__.objects.normalize_email(self.email)

    def save(self, *args, **kwargs):
        if not self.username and self.email:
            self.username = self.build_technical_username(self.email)
        super().save(*args, **kwargs)

    def __str__(self) -> str:
        return self.email

