import os
import django
from django.conf import settings

# Configure Django settings
import sys

# Add project root to sys.path
sys.path.append('e:\\Anigravity\\Legalize_site')

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'legalize_site.settings')
django.setup()

from clients.models import Client

try:
    client = Client.objects.get(pk=3)
    print(f"Client ID: {client.id}")
    print(f"Status (raw): '{client.status}'")
    print(f"Status (display): '{client.get_status_display()}'")
except Client.DoesNotExist:
    print("Client 3 not found.")
except Exception as e:
    print(f"Error: {e}")
