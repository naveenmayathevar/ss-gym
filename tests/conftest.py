"""
conftest.py — Pytest fixtures shared across all test files.
This file is automatically loaded by pytest before any tests run.
"""
import sys
import os

# Add the project root to sys.path so `from app import ...` works
# regardless of where pytest is invoked from (repo root, CI, subdirectory).
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest
from app import create_app, db
from app.models.user import User
from app.models.fitness import GymClass, Booking
from datetime import datetime, timedelta


class TestConfig:
    """Isolated config for tests — uses in-memory SQLite, never touches production DB."""
    TESTING = True
    SQLALCHEMY_DATABASE_URI = "sqlite:///:memory:"
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    SECRET_KEY = "test-secret-key-not-for-production"
    WTF_CSRF_ENABLED = False
    # Stripe test keys (no real charges possible with these)
    STRIPE_SECRET_KEY = "sk_test_fake_key_for_testing"
    STRIPE_PUBLIC_KEY = "pk_test_fake_key_for_testing"
    LOGIN_DISABLED = False


@pytest.fixture(scope="session")
def app():
    """Create the Flask app once for the entire test session."""
    flask_app = create_app(TestConfig)
    yield flask_app


@pytest.fixture(scope="function")
def client(app):
    """
    Gives each test a fresh test client AND a clean database.
    'scope=function' means the DB is wiped between every single test — no bleed-over.
    """
    with app.app_context():
        db.create_all()
        yield app.test_client()
        db.session.remove()
        db.drop_all()


@pytest.fixture
def regular_user(client, app):
    """A standard, non-admin, non-premium user."""
    with app.app_context():
        user = User(name="Test User", email="testuser@example.com")
        user.set_password("password123")
        db.session.add(user)
        db.session.commit()
        # Re-fetch to avoid DetachedInstanceError in tests
        return User.query.filter_by(email="testuser@example.com").first()


@pytest.fixture
def admin_user(client, app):
    """An admin user."""
    with app.app_context():
        user = User(name="Admin User", email="admin@example.com", role="admin")
        user.set_password("adminpass123")
        db.session.add(user)
        db.session.commit()
        return User.query.filter_by(email="admin@example.com").first()


@pytest.fixture
def premium_user(client, app):
    """A premium member."""
    with app.app_context():
        user = User(name="Premium User", email="premium@example.com", is_premium=True)
        user.set_password("premiumpass123")
        db.session.add(user)
        db.session.commit()
        return User.query.filter_by(email="premium@example.com").first()


@pytest.fixture
def sample_class(client, app):
    """A gym class scheduled in the future."""
    with app.app_context():
        gym_class = GymClass(
            title="Morning Yoga",
            instructor="Jane Doe",
            schedule_time=datetime.now() + timedelta(days=7),
            capacity=10
        )
        db.session.add(gym_class)
        db.session.commit()
        return GymClass.query.filter_by(title="Morning Yoga").first()


def login(client, email, password):
    """Helper function — logs in a user and returns the response."""
    return client.post("/auth/login", data={
        "email": email,
        "password": password
    }, follow_redirects=True)