"""Shared test fixtures for the clients app."""
from __future__ import annotations

import pytest
from django.test import Client as DjangoClient

from clients.models import Client
from clients.tests.factories import create_admin_user, create_manager_user, create_staff_user


@pytest.fixture
def staff_user(db):
    """Return a staff user with the 'Staff' role."""
    return create_staff_user()


@pytest.fixture
def admin_user(db):
    """Return a staff user with the 'Admin' role."""
    return create_admin_user()


@pytest.fixture
def manager_user(db):
    """Return a staff user with the 'Manager' role."""
    return create_manager_user()


@pytest.fixture
def logged_in_staff(staff_user):
    """Return a Django test client already authenticated as a Staff user."""
    client = DjangoClient()
    client.force_login(staff_user)
    client._staff_user = staff_user  # expose for assertions
    return client


@pytest.fixture
def logged_in_admin(admin_user):
    """Return a Django test client already authenticated as an Admin user."""
    client = DjangoClient()
    client.force_login(admin_user)
    client._admin_user = admin_user
    return client


@pytest.fixture
def sample_client(db):
    """Return a minimal Client record for testing."""
    return Client.objects.create(
        first_name="Test",
        last_name="Client",
        email="testclient@example.com",
        phone="+48123456789",
        citizenship="Poland",
        application_purpose="work",
    )
