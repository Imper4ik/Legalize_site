from django.contrib.auth.forms import BaseUserCreationForm, UserChangeForm

from .models import User


class EmailUserCreationForm(BaseUserCreationForm):
    class Meta(BaseUserCreationForm.Meta):
        model = User
        fields = ("email", "first_name", "last_name")


class EmailUserChangeForm(UserChangeForm):
    class Meta(UserChangeForm.Meta):
        model = User
        fields = "__all__"

