from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin

from .forms import EmailUserChangeForm, EmailUserCreationForm
from .models import User


@admin.register(User)
class UserAdmin(BaseUserAdmin):
    add_form = EmailUserCreationForm
    form = EmailUserChangeForm
    model = User
    fieldsets = (
        (None, {"fields": ("email", "password")}),
        ("Personal info", {"fields": ("first_name", "last_name")}),
        (
            "Permissions",
            {
                "fields": (
                    "is_active",
                    "is_staff",
                    "is_superuser",
                    "groups",
                    "user_permissions",
                ),
            },
        ),
        ("Important dates", {"fields": ("last_login", "date_joined")}),
    )
    add_fieldsets = (
        (
            None,
            {
                "classes": ("wide",),
                "fields": ("email", "first_name", "last_name", "password1", "password2", "is_staff", "is_superuser"),
            },
        ),
    )
    list_display = ("email", "first_name", "last_name", "is_staff", "is_superuser")
    list_filter = ("is_staff", "is_superuser", "is_active", "groups")
    ordering = ("email",)
    search_fields = ("email", "first_name", "last_name")
    filter_horizontal = ("groups", "user_permissions")

