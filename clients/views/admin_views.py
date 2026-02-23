import logging
import subprocess
import os
from django.conf import settings
from django.contrib import messages
from django.contrib.admin.views.decorators import staff_member_required
from django.core.management import call_command
from django.shortcuts import redirect

logger = logging.getLogger(__name__)

@staff_member_required
def update_translations_view(request):
    """
    A view accessible only by staff/admin.
    It programmatically runs:
      1. makemessages
      2. python fix_po.py (to remove duplicates)
      3. compilemessages
    """
    try:
        # 1. makemessages
        logger.info("Running makemessages...")
        call_command(
            'makemessages',
            locale=['ru', 'en', 'pl'],
            ignore=['venv', 'env', '.venv', 'frontend', 'frontend/node_modules/*'],
            all=True
        )

        # 2. fix_po.py
        # We need to run the python script we created to clean up duplicates
        # so msgmerge/compilemessages doesn't crash
        fix_po_path = os.path.join(settings.BASE_DIR, 'fix_po.py')
        if os.path.exists(fix_po_path):
            logger.info("Running fix_po.py...")
            subprocess.run(['python', fix_po_path], check=True, cwd=settings.BASE_DIR)

        # 3. compilemessages
        logger.info("Running compilemessages...")
        call_command(
            'compilemessages',
            ignore=['venv', 'env', '.venv', 'frontend', 'frontend/node_modules/*']
        )

        messages.success(request, "Переводы успешно обновлены и скомпилированы!")
    except Exception as e:
        logger.exception("Error updating translations")
        messages.error(request, f"Ошибка при обновлении переводов: {e}")

    # Перенаправляем обратно на ту же страницу, с которой был сделан запрос
    redirect_url = request.META.get('HTTP_REFERER', '/admin/')
    return redirect(redirect_url)
