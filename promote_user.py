# promote_user.py
import os
import django

# Настраиваем Django, чтобы можно было работать с моделями
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'legalize_site.settings')
django.setup()

from django.contrib.auth.models import User

# --- ВАЖНО: Укажите здесь email вашего главного аккаунта ---
ADMIN_EMAIL = 'nindse@gmail.com'
# ---------------------------------------------------------

try:
    # Находим вашего пользователя в новой базе данных по email
    user = User.objects.get(email=ADMIN_EMAIL)

    # Даем ему права администратора
    user.is_staff = True
    user.is_superuser = True
    user.save()

    print(f"Пользователь {ADMIN_EMAIL} успешно сделан администратором!")

except User.DoesNotExist:
    print(f"Ошибка: Пользователь с email {ADMIN_EMAIL} не найден в базе данных.")
    print("Пожалуйста, сначала зарегистрируйтесь на сайте с этим email, а потом запустите скрипт еще раз.")