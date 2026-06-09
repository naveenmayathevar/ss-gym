"""
test_admin.py — Tests for admin-only routes and model helper properties.
"""
import pytest
from app import db
from app.models.fitness import GymClass, Booking
from app.models.user import User
from tests.conftest import login
from datetime import datetime, timedelta


class TestAdminAccess:
    def test_admin_page_blocks_anonymous(self, client):
        """Anonymous users should be redirected away from /admin."""
        res = client.get("/admin", follow_redirects=True)
        assert b"login" in res.data.lower()

    def test_admin_page_blocks_regular_user(self, client, regular_user):
        """Regular users should get a 403 on the admin page."""
        login(client, "testuser@example.com", "password123")
        res = client.get("/admin")
        assert res.status_code == 403

    def test_admin_page_loads_for_admin(self, client, admin_user):
        """Admin users should be able to access the admin page."""
        login(client, "admin@example.com", "adminpass123")
        res = client.get("/admin")
        assert res.status_code == 200

    def test_admin_can_add_class(self, client, app, admin_user):
        """Admin can submit a new gym class via the form."""
        login(client, "admin@example.com", "adminpass123")
        future_time = (datetime.now() + timedelta(days=5)).strftime("%Y-%m-%dT%H:%M")
        res = client.post("/admin", data={
            "title": "Power Lifting",
            "instructor": "Bob Smith",
            "schedule_time": future_time,
            "capacity": "15"
        }, follow_redirects=True)
        assert res.status_code == 200
        with app.app_context():
            cls = GymClass.query.filter_by(title="Power Lifting").first()
            assert cls is not None
            assert cls.capacity == 15

    def test_admin_can_delete_class(self, client, app, admin_user, sample_class):
        """Admin can delete a class and all its bookings."""
        login(client, "admin@example.com", "adminpass123")
        res = client.post(f"/admin/delete/{sample_class.id}", follow_redirects=True)
        assert res.status_code == 200
        with app.app_context():
            assert GymClass.query.get(sample_class.id) is None

    def test_regular_user_cannot_delete_class(self, client, regular_user, sample_class):
        """Regular users should get 403 trying to delete a class."""
        login(client, "testuser@example.com", "password123")
        res = client.post(f"/admin/delete/{sample_class.id}")
        assert res.status_code == 403

    def test_roster_blocked_for_regular_user(self, client, regular_user, sample_class):
        """Regular users cannot view the class roster."""
        login(client, "testuser@example.com", "password123")
        res = client.get(f"/admin/roster/{sample_class.id}")
        assert res.status_code == 403

    def test_roster_accessible_for_admin(self, client, admin_user, sample_class):
        """Admins can view the class roster."""
        login(client, "admin@example.com", "adminpass123")
        res = client.get(f"/admin/roster/{sample_class.id}")
        assert res.status_code == 200


class TestGymClassModel:
    """Unit tests for GymClass model properties — no HTTP requests needed."""

    def test_spots_left_empty_class(self, client, sample_class, app):
        """A class with no bookings should have all spots available."""
        with app.app_context():
            cls = GymClass.query.get(sample_class.id)
            assert cls.spots_left == cls.capacity

    def test_spots_left_after_booking(self, client, app, premium_user, sample_class):
        """spots_left decreases by 1 after a booking is made."""
        with app.app_context():
            cls = GymClass.query.get(sample_class.id)
            initial_spots = cls.spots_left
            user = User.query.get(premium_user.id)
            booking = Booking(user_id=user.id, class_id=cls.id)
            db.session.add(booking)
            db.session.commit()
            db.session.refresh(cls)
            assert cls.spots_left == initial_spots - 1

    def test_fill_percentage_empty(self, client, sample_class, app):
        """An empty class should have 0% fill."""
        with app.app_context():
            cls = GymClass.query.get(sample_class.id)
            assert cls.fill_percentage == 0

    def test_fill_percentage_half_full(self, client, app, sample_class):
        """A class half-booked should show 50% fill."""
        with app.app_context():
            cls = GymClass.query.get(sample_class.id)
            cls.capacity = 4
            db.session.commit()

            for i in range(2):
                u = User(name=f"User{i}", email=f"user{i}@fill.com")
                u.set_password("pass")
                db.session.add(u)
                db.session.flush()
                db.session.add(Booking(user_id=u.id, class_id=cls.id))

            db.session.commit()
            db.session.refresh(cls)
            assert cls.fill_percentage == 50


class TestUserModel:
    def test_password_check(self, client, app, regular_user):
        """check_password should return True for correct password, False otherwise."""
        with app.app_context():
            user = User.query.get(regular_user.id)
            assert user.check_password("password123") is True
            assert user.check_password("wrongpassword") is False

    def test_avatar_returns_gravatar_without_upload(self, client, app, regular_user):
        """Without a custom avatar, avatar() should return a Gravatar URL."""
        with app.app_context():
            user = User.query.get(regular_user.id)
            user.avatar_file = None
            db.session.commit()
            url = user.avatar(80)
            assert "gravatar.com" in url

    def test_avatar_returns_upload_path_with_file(self, client, app, regular_user):
        """With a custom avatar, avatar() should return the /static/uploads path."""
        with app.app_context():
            user = User.query.get(regular_user.id)
            user.avatar_file = "1_profile.jpg"
            db.session.commit()
            url = user.avatar(80)
            assert "/static/uploads/1_profile.jpg" in url