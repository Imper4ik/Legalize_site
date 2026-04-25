import logging
import subprocess
import os
from django.conf import settings
from django.contrib import messages
from django.contrib.admin.views.decorators import staff_member_required
from django.core.management import call_command
from django.http import HttpResponseForbidden
from django.http import Http404
from django.shortcuts import redirect
from django.utils.translation import gettext as _
from django.views.decorators.http import require_POST
from django.views.decorators.csrf import csrf_protect
from django.utils.http import url_has_allowed_host_and_scheme

logger = logging.getLogger(__name__)

@staff_member_required
@require_POST
@csrf_protect
def update_translations_view(request):
    """
    A view accessible only by superusers.
    It programmatically runs:
      1. makemessages
      2. python fix_po.py (to remove duplicates)
      3. compilemessages
    """
    if not getattr(settings, "ENABLE_TRANSLATION_TOOLING", False):
        raise Http404("Not found")

    if not request.user.is_superuser:
        return HttpResponseForbidden(_("Только суперпользователи могут обновлять переводы."))

    try:
        # 1. makemessages
        logger.info("Running makemessages...")
        call_command(
            'makemessages',
            locale=['ru', 'en', 'pl'],
            ignore=['venv', 'env', '.venv', 'frontend', 'frontend/node_modules/*'],
            all=True
        )

        # 2. fix_po_dupes.py
        # We need to run the python script we created to clean up duplicates
        # so msgmerge/compilemessages doesn't crash
        fix_po_path = os.path.join(settings.BASE_DIR, 'fix_po_dupes.py')
        if os.path.exists(fix_po_path):
            logger.info("Running fix_po_dupes.py...")
            subprocess.run(['python', fix_po_path], check=True, cwd=settings.BASE_DIR)

        # 3. compilemessages
        logger.info("Running compilemessages...")
        call_command(
            'compilemessages',
            ignore=['venv', 'env', '.venv', 'frontend', 'frontend/node_modules/*']
        )

        messages.success(request, _("Переводы успешно обновлены и скомпилированы!"))
    except Exception as e:
        logger.exception("Error updating translations")
        messages.error(request, _("Ошибка при обновлении переводов: %(err)s") % {"err": e})

    redirect_url = request.META.get('HTTP_REFERER')
    if not url_has_allowed_host_and_scheme(
        url=redirect_url,
        allowed_hosts={request.get_host()},
        require_https=request.is_secure()
    ):
        redirect_url = '/admin/'

    return redirect(redirect_url)
