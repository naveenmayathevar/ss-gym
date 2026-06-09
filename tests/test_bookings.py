"""
test_bookings.py — Tests for class listing, booking, and cancellation.
"""
import pytest
from app import db
from app.models.fitness import GymClass, Booking
from app.models.user import User
from tests.conftest import login
from datetime import datetime, timedelta


class TestClassListing:
    def test_classes_page_loads(self, client):
        """GET /classes should always return 200, even when empty."""
        res = client.get("/classes")
        assert res.status_code == 200

    def test_classes_shows_available_class(self, client, sample_class):
        """A class added to the DB should appear on the /classes page."""
        res = client.get("/classes")
        assert b"Morning Yoga" in res.data

    def test_classes_search(self, client, sample_class):
        """Searching for a class title should return matching results."""
        res = client.get("/classes?q=Yoga")
        assert b"Morning Yoga" in res.data

    def test_classes_search_no_results(self, client, sample_class):
        """Searching for something that doesn't exist should return empty results."""
        res = client.get("/classes?q=Zumba")
        assert b"Morning Yoga" not in res.data


class TestBooking:
    def test_booking_requires_login(self, client, sample_class):
        """Unauthenticated users should be redirected to login when booking."""
        res = client.post(f"/book/{sample_class.id}", follow_redirects=True)
        assert b"login" in res.data.lower()

    def test_premium_user_can_book(self, client, app, premium_user, sample_class):
        """Premium members can book classes without class passes."""
        login(client, "premium@example.com", "premiumpass123")
        res = client.post(f"/book/{sample_class.id}", follow_redirects=True)
        assert res.status_code == 200
        with app.app_context():
            booking = Booking.query.filter_by(
                user_id=premium_user.id, class_id=sample_class.id
            ).first()
            assert booking is not None

    def test_user_with_pass_can_book(self, client, app, regular_user, sample_class):
        """A user with class passes can book, and one pass is deducted."""
        with app.app_context():
            user = User.query.get(regular_user.id)
            user.class_passes = 3
            db.session.commit()

        login(client, "testuser@example.com", "password123")
        client.post(f"/book/{sample_class.id}", follow_redirects=True)

        with app.app_context():
            user = User.query.get(regular_user.id)
            assert user.class_passes == 2  # One was deducted

    def test_user_without_pass_cannot_book(self, client, app, regular_user, sample_class):
        """A non-premium user with 0 passes should be blocked from booking."""
        # regular_user starts with 0 passes, not premium
        login(client, "testuser@example.com", "password123")
        res = client.post(f"/book/{sample_class.id}", follow_redirects=True)
        assert res.status_code == 200
        with app.app_context():
            booking = Booking.query.filter_by(
                user_id=regular_user.id, class_id=sample_class.id
            ).first()
            assert booking is None

    def test_double_booking_blocked(self, client, app, premium_user, sample_class):
        """A user cannot book the same class twice."""
        login(client, "premium@example.com", "premiumpass123")
        client.post(f"/book/{sample_class.id}", follow_redirects=True)
        client.post(f"/book/{sample_class.id}", follow_redirects=True)  # Second time

        with app.app_context():
            count = Booking.query.filter_by(
                user_id=premium_user.id, class_id=sample_class.id
            ).count()
            assert count == 1  # Only one booking, not two

    def test_full_class_cannot_be_booked(self, client, app, sample_class):
        """A class at full capacity should reject new bookings."""
        # Fill the class to capacity (10) with dummy users
        with app.app_context():
            gym_class = GymClass.query.get(sample_class.id)
            gym_class.capacity = 1
            db.session.commit()

            # Create a user to fill the spot
            filler = User(name="Filler", email="filler@test.com")
            filler.set_password("pass")
            db.session.add(filler)
            db.session.commit()

            booking = Booking(user_id=filler.id, class_id=sample_class.id)
            db.session.add(booking)
            db.session.commit()

        # Now try to book as premium_user — should fail
        premium = User(name="Late User", email="late@test.com", is_premium=True)
        with app.app_context():
            premium.set_password("pass")
            db.session.add(premium)
            db.session.commit()

        login(client, "late@test.com", "pass")
        res = client.post(f"/book/{sample_class.id}", follow_redirects=True)
        assert b"fully booked" in res.data


class TestCancellation:
    def test_user_can_cancel_own_booking(self, client, app, premium_user, sample_class):
        """A user can cancel their own booking."""
        login(client, "premium@example.com", "premiumpass123")
        client.post(f"/book/{sample_class.id}", follow_redirects=True)

        with app.app_context():
            booking = Booking.query.filter_by(
                user_id=premium_user.id, class_id=sample_class.id
            ).first()
            booking_id = booking.id

        res = client.post(f"/cancel_booking/{booking_id}", follow_redirects=True)
        assert res.status_code == 200
        with app.app_context():
            assert Booking.query.get(booking_id) is None

    def test_user_cannot_cancel_others_booking(self, client, app, premium_user, regular_user, sample_class):
        """A user should not be able to cancel someone else's booking."""
        # Premium user books the class
        with app.app_context():
            booking = Booking(user_id=premium_user.id, class_id=sample_class.id)
            db.session.add(booking)
            db.session.commit()
            booking_id = booking.id

        # Give regular_user a pass and log in as them
        with app.app_context():
            user = User.query.get(regular_user.id)
            user.class_passes = 1
            db.session.commit()

        login(client, "testuser@example.com", "password123")
        res = client.post(f"/cancel_booking/{booking_id}", follow_redirects=True)

        with app.app_context():
            # Booking should still exist
            assert Booking.query.get(booking_id) is not None