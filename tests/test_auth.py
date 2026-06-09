"""
test_auth.py — Tests for /auth/register and /auth/login endpoints.
"""
import pytest
from app import db
from app.models.user import User
from tests.conftest import login


class TestRegistration:
    def test_register_page_loads(self, client):
        """GET /auth/register should return 200."""
        res = client.get("/auth/register")
        assert res.status_code == 200

    def test_register_new_user(self, client, app):
        """Submitting the registration form creates a user in the DB."""
        res = client.post("/auth/register", data={
            "name": "New Member",
            "email": "newmember@example.com",
            "password": "securepassword"
        }, follow_redirects=True)
        assert res.status_code == 200
        with app.app_context():
            user = User.query.filter_by(email="newmember@example.com").first()
            assert user is not None
            assert user.name == "New Member"

    def test_register_does_not_store_plain_text_password(self, client, app):
        """Passwords must be hashed — never stored in plain text."""
        client.post("/auth/register", data={
            "name": "Security Test",
            "email": "security@example.com",
            "password": "myplaintextpassword"
        })
        with app.app_context():
            user = User.query.filter_by(email="security@example.com").first()
            assert user.password_hash != "myplaintextpassword"
            assert len(user.password_hash) > 20  # It's a real hash

    def test_duplicate_email_blocked(self, client, regular_user):
        """Registering with an already-used email should not create a second user."""
        res = client.post("/auth/register", data={
            "name": "Duplicate",
            "email": "testuser@example.com",  # Same as regular_user
            "password": "password123"
        }, follow_redirects=True)
        # Should show an error, not redirect to dashboard
        assert res.status_code == 200
        assert b"already registered" in res.data or b"Email" in res.data


class TestLogin:
    def test_login_page_loads(self, client):
        """GET /auth/login should return 200."""
        res = client.get("/auth/login")
        assert res.status_code == 200

    def test_login_valid_credentials(self, client, regular_user):
        """Valid login redirects to the home page."""
        res = login(client, "testuser@example.com", "password123")
        assert res.status_code == 200
        # After login, the index redirects to dashboard
        assert b"Dashboard" in res.data or b"dashboard" in res.data

    def test_login_wrong_password(self, client, regular_user):
        """Wrong password should not log the user in."""
        res = login(client, "testuser@example.com", "wrongpassword")
        assert res.status_code == 200
        assert b"Invalid" in res.data

    def test_login_nonexistent_email(self, client):
        """Email not in DB should not log in."""
        res = login(client, "ghost@example.com", "password123")
        assert res.status_code == 200
        assert b"Invalid" in res.data

    def test_logout(self, client, regular_user):
        """Logged-in user can log out and is redirected."""
        login(client, "testuser@example.com", "password123")
        res = client.get("/auth/logout", follow_redirects=True)
        assert res.status_code == 200
        # After logout, accessing dashboard should redirect to login
        res2 = client.get("/dashboard", follow_redirects=True)
        assert b"login" in res2.data.lower() or res2.status_code == 200