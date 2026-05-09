from __future__ import annotations

import hashlib
from typing import Any, cast, TYPE_CHECKING

from django.contrib.auth.models import AbstractUser, Group, Permission, UserManager as DjangoUserManager
from django.db import models
from django.utils.text import slugify
from django.utils.translation import gettext_lazy as _

if TYPE_CHECKING:
    # Use Any for managers to avoid chasing specific django-stubs locations for RelatedManager
    pass


class EmailUserManager(DjangoUserManager["User"]):
    use_in_migrations = True

    def _resolve_email(self, email: str | None, extra_fields: dict[str, Any]) -> str:
        explicit_username = extra_fields.get("username")
        candidate = email or extra_fields.get("email")
        if not candidate and isinstance(explicit_username, str) and "@" in explicit_username:
            candidate = explicit_username
        if not candidate:
            raise ValueError("The given email must be set")
        return self.normalize_email(str(candidate))

    def _resolve_username(self, email: str, extra_fields: dict[str, Any]) -> str:
        explicit_username = extra_fields.get("username")
        if explicit_username:
            return cast(str, self.model.normalize_username(str(explicit_username)))
        # Use cast to Any then User to call class method without mypy complaining about Manager.model
        return cast(Any, self.model).build_technical_username(email)

    def create_user(self, username: str | None = None, email: str | None = None, password: str | None = None, **extra_fields: Any) -> User:
        extra_fields.setdefault("is_staff", False)
        extra_fields.setdefault("is_superuser", False)
        resolved_email = self._resolve_email(email, extra_fields)
        resolved_username = username or self._resolve_username(resolved_email, extra_fields)
        return super()._create_user(resolved_username, resolved_email, password, **extra_fields)  # type: ignore[misc]

    def create_superuser(self, username: str | None = None, email: str | None = None, password: str | None = None, **extra_fields: Any) -> User:
        extra_fields.setdefault("is_staff", True)
        extra_fields.setdefault("is_superuser", True)

        if extra_fields.get("is_staff") is not True:
            raise ValueError("Superuser must have is_staff=True.")
        if extra_fields.get("is_superuser") is not True:
            raise ValueError("Superuser must have is_superuser=True.")

        resolved_email = self._resolve_email(email, extra_fields)
        resolved_username = username or self._resolve_username(resolved_email, extra_fields)
        return super()._create_user(resolved_username, resolved_email, password, **extra_fields)  # type: ignore[misc]


class User(AbstractUser):
    username = models.CharField(_("technical username"), max_length=150, unique=True, blank=True)
    email = models.EmailField(_("email address"), unique=True)
    
    groups: models.ManyToManyField[Group, User] = models.ManyToManyField(  # type: ignore[assignment]
        Group,
        verbose_name=_("groups"),
        blank=True,
        help_text=_("The groups this user belongs to. A user will get all permissions granted to each of their groups."),
        related_name="user_set",
        related_query_name="user",
        db_table="auth_user_groups",
    )
    user_permissions: models.ManyToManyField[Permission, User] = models.ManyToManyField(  # type: ignore[assignment]
        Permission,
        verbose_name=_("user permissions"),
        blank=True,
        help_text=_("Specific permissions for this user."),
        related_name="user_set",
        related_query_name="user",
        db_table="auth_user_user_permissions",
    )

    USERNAME_FIELD = "email"
    REQUIRED_FIELDS = []
    objects = EmailUserManager()  # type: ignore[misc]

    class Meta:
        db_table = "auth_user"
        verbose_name = _("user")
        verbose_name_plural = _("users")

    @classmethod
    def build_technical_username(cls, email: str) -> str:
        normalized_email = email.strip().casefold()
        local_part = normalized_email.partition("@")[0]
        slug = slugify(local_part) or "user"
        digest = hashlib.sha1(normalized_email.encode("utf-8"), usedforsecurity=False).hexdigest()[:12]
        max_slug_length = 150 - len(digest) - 1
        return f"{slug[:max_slug_length]}-{digest}"

    def clean(self) -> None:
        super().clean()
        self.email = self.__class__.objects.normalize_email(self.email)

    def save(self, *args: Any, **kwargs: Any) -> None:
        if not self.username and self.email:
            self.username = self.build_technical_username(self.email)
        super().save(*args, **kwargs)

    def __str__(self) -> str:
        return self.email
