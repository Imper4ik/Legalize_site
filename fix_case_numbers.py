import os
import sys
import django

# Setup Django environment
sys.path.append(os.path.dirname(os.path.abspath(__file__)))
from legalize_site.env import load_env
load_env()

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "legalize_site.settings.development")
django.setup()

if os.environ.get("ALLOW_PRODUCTION_DATA_MUTATION") != "yes":
    raise SystemExit(
        "Refusing to mutate data. Set ALLOW_PRODUCTION_DATA_MUTATION=yes only for a reviewed maintenance run."
    )

from django.db import connection

print("--- Clearing Case Numbers with raw SQL to prevent Decryption Crashes on Production ---")

with connection.cursor() as cursor:
    # 1. Update case_number to empty string for Daria and all prod-test- clients
    cursor.execute("""
        UPDATE clients_client 
        SET case_number = '' 
        WHERE id IN (1, 50084, 50085, 50086, 50087)
    """)
    rows_updated = cursor.rowcount
    print(f"Successfully cleared case_number for {rows_updated} records.")

print("--- Done ---")
