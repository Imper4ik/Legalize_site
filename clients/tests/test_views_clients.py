from django.test import TestCase, Client as DjangoClient
from django.urls import reverse
from django.contrib.auth import get_user_model

from clients.models import Client, Payment, Document, Reminder
from clients.forms import ClientForm

User = get_user_model()



