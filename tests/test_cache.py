"""
tests/test_cache.py

Tests for Redis cache behavior:
- Cache hit (returns cached data, skips DB)
- Cache miss (queries DB, stores result)
- Cache invalidation (after booking, cancelling, admin add/delete)
- Redis unavailable fallback (app still works)
"""
import json
import pytest
from unittest.mock import patch, MagicMock
from datetime import datetime, timedelta

from app import create_app, db
from app.models.fitness import GymClass, Booking
from app.models.user import User
from app.services import cache


# ── Shared test config ─────────────────────────────────────────────────────────

class CacheTestConfig:
    TESTING = True
    SQLALCHEMY_DATABASE_URI = "sqlite:///:memory:"
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    SECRET_KEY = "test-secret-key"
    WTF_CSRF_ENABLED = False
    STRIPE_SECRET_KEY = "sk_test_fake"
    STRIPE_PUBLIC_KEY = "pk_test_fake"
    LOGIN_DISABLED = False


@pytest.fixture(scope="module")
def app():
    flask_app = create_app(CacheTestConfig)
    yield flask_app


@pytest.fixture(autouse=True)
def clean_db(app):
    """Fresh DB for every test."""
    with app.app_context():
        db.create_all()
        yield
        db.session.remove()
        db.drop_all()


@pytest.fixture
def client(app):
    return app.test_client()


@pytest.fixture
def future_class(app):
    """A gym class scheduled one week from now."""
    with app.app_context():
        gc = GymClass(
            title="Spin Class",
            instructor="Bob",
            schedule_time=datetime.now() + timedelta(days=7),
            capacity=10,
        )
        db.session.add(gc)
        db.session.commit()
        return GymClass.query.filter_by(title="Spin Class").first()


@pytest.fixture
def regular_user(app):
    with app.app_context():
        user = User(name="Test User", email="test@example.com", class_passes=5)
        user.set_password("password123")
        db.session.add(user)
        db.session.commit()
        return User.query.filter_by(email="test@example.com").first()


@pytest.fixture
def admin_user(app):
    with app.app_context():
        user = User(name="Admin", email="admin@example.com", role="admin")
        user.set_password("adminpass")
        db.session.add(user)
        db.session.commit()
        return User.query.filter_by(email="admin@example.com").first()


def login(client, email, password):
    return client.post("/auth/login", data={"email": email, "password": password},
                       follow_redirects=True)


# ── 1. Cache miss: first request hits the DB ──────────────────────────────────

class TestCacheMiss:

    def test_api_classes_miss_queries_db(self, client, future_class):
        """On a cold cache, /api/classes should return data from the DB."""
        with patch.object(cache, 'get_class_list', return_value=None) as mock_get, \
             patch.object(cache, 'set_class_list', return_value=True) as mock_set:

            response = client.get('/api/classes')

        assert response.status_code == 200
        data = response.get_json()
        assert isinstance(data, list)
        assert len(data) == 1
        assert data[0]['title'] == 'Spin Class'

        # Cache was checked (miss) then populated
        mock_get.assert_called_once()
        mock_set.assert_called_once()

    def test_api_class_detail_miss_queries_db(self, client, future_class, app):
        """On a cold cache, /api/classes/<id> should return data from the DB."""
        with app.app_context():
            class_id = GymClass.query.first().id

        with patch.object(cache, 'get_class_detail', return_value=None), \
             patch.object(cache, 'set_class_detail', return_value=True) as mock_set:

            response = client.get(f'/api/classes/{class_id}')

        assert response.status_code == 200
        data = response.get_json()
        assert data['title'] == 'Spin Class'
        mock_set.assert_called_once_with(class_id, data)

    def test_api_capacity_miss_queries_db(self, client, future_class, app):
        """On a cold cache, /api/classes/<id>/capacity should query the DB."""
        with app.app_context():
            class_id = GymClass.query.first().id

        with patch.object(cache, 'get_class_capacity', return_value=None), \
             patch.object(cache, 'set_class_capacity', return_value=True) as mock_set:

            response = client.get(f'/api/classes/{class_id}/capacity')

        assert response.status_code == 200
        data = response.get_json()
        assert data['spots_left'] == 10   # Full capacity, no bookings
        mock_set.assert_called_once_with(class_id, 10)


# ── 2. Cache hit: second request skips the DB ─────────────────────────────────

class TestCacheHit:

    def test_api_classes_hit_skips_db(self, client):
        """When cache has data, /api/classes should NOT touch the DB."""
        fake_data = [{'id': 99, 'title': 'Cached Yoga', 'capacity': 5, 'spots_left': 5}]

        with patch.object(cache, 'get_class_list', return_value=fake_data) as mock_get, \
             patch('app.models.fitness.GymClass.query') as mock_query:

            response = client.get('/api/classes')

        assert response.status_code == 200
        data = response.get_json()
        assert data[0]['title'] == 'Cached Yoga'

        mock_get.assert_called_once()
        mock_query.assert_not_called()   # DB was never touched

    def test_api_class_detail_hit_skips_db(self, client):
        """When cache has detail, the DB should not be queried."""
        fake_detail = {'id': 99, 'title': 'Cached Pilates', 'spots_left': 3}

        with patch.object(cache, 'get_class_detail', return_value=fake_detail), \
             patch('app.models.fitness.GymClass.query') as mock_query:

            response = client.get('/api/classes/99')

        assert response.status_code == 200
        assert response.get_json()['title'] == 'Cached Pilates'
        mock_query.assert_not_called()

    def test_api_capacity_hit_skips_db(self, client):
        """When capacity is cached, the DB should not be queried."""
        with patch.object(cache, 'get_class_capacity', return_value=7), \
             patch('app.models.fitness.GymClass.query') as mock_query:

            response = client.get('/api/classes/1/capacity')

        assert response.status_code == 200
        assert response.get_json()['spots_left'] == 7
        mock_query.assert_not_called()


# ── 3. Cache invalidation ─────────────────────────────────────────────────────

class TestCacheInvalidation:

    def test_booking_invalidates_cache(self, client, future_class, regular_user, app):
        """Booking a class should invalidate that class's cache entries."""
        with app.app_context():
            class_id = GymClass.query.first().id

        login(client, "test@example.com", "password123")

        with patch.object(cache, 'invalidate_class_cache') as mock_invalidate:
            response = client.post(f'/book/{class_id}', follow_redirects=True)

        assert response.status_code == 200
        mock_invalidate.assert_called_once_with(class_id=class_id)

    def test_cancel_booking_invalidates_cache(self, client, future_class, regular_user, app):
        """Cancelling a booking should invalidate cache for that class."""
        with app.app_context():
            class_id = GymClass.query.first().id
            user_id = User.query.filter_by(email="test@example.com").first().id
            booking = Booking(user_id=user_id, class_id=class_id)
            db.session.add(booking)
            db.session.commit()
            booking_id = Booking.query.first().id

        login(client, "test@example.com", "password123")

        with patch.object(cache, 'invalidate_class_cache') as mock_invalidate:
            response = client.post(f'/cancel_booking/{booking_id}', follow_redirects=True)

        assert response.status_code == 200
        mock_invalidate.assert_called_once_with(class_id=class_id)

    def test_admin_add_class_invalidates_cache(self, client, admin_user):
        """Adding a class via admin panel should invalidate the class list cache."""
        login(client, "admin@example.com", "adminpass")

        with patch.object(cache, 'invalidate_class_cache') as mock_invalidate:
            response = client.post('/admin', data={
                'title': 'New HIIT',
                'instructor': 'Jane',
                'schedule_time': '2027-01-15T09:00',
                'capacity': '15',
            }, follow_redirects=True)

        assert response.status_code == 200
        mock_invalidate.assert_called_once_with()   # No class_id — whole list changed

    def test_admin_delete_class_invalidates_cache(self, client, future_class, admin_user, app):
        """Deleting a class should invalidate its specific cache entries."""
        with app.app_context():
            class_id = GymClass.query.first().id

        login(client, "admin@example.com", "adminpass")

        with patch.object(cache, 'invalidate_class_cache') as mock_invalidate:
            response = client.post(f'/admin/delete/{class_id}', follow_redirects=True)

        assert response.status_code == 200
        mock_invalidate.assert_called_once_with(class_id=class_id)


# ── 4. Redis unavailable fallback ─────────────────────────────────────────────

class TestRedisFallback:

    def test_app_works_when_redis_is_down(self, client, future_class):
        """If Redis is completely unavailable, the API should still return DB data."""
        # Simulate Redis being down: all cache operations return None/False
        with patch.object(cache, 'get_class_list', return_value=None), \
             patch.object(cache, 'set_class_list', return_value=False):

            response = client.get('/api/classes')

        assert response.status_code == 200
        data = response.get_json()
        assert len(data) == 1
        assert data[0]['title'] == 'Spin Class'

    def test_cache_get_returns_none_on_error(self):
        """cache.get() should return None (not raise) when Redis errors."""
        mock_redis = MagicMock()
        mock_redis.get.side_effect = Exception("Connection refused")

        with patch('app.services.cache._redis', return_value=mock_redis):
            result = cache.get('some:key')

        assert result is None

    def test_cache_set_returns_false_on_error(self):
        """cache.set() should return False (not raise) when Redis errors."""
        mock_redis = MagicMock()
        mock_redis.setex.side_effect = Exception("Connection refused")

        with patch('app.services.cache._redis', return_value=mock_redis):
            result = cache.set('some:key', {'data': 1})

        assert result is False

    def test_cache_delete_returns_false_on_error(self):
        """cache.delete() should return False (not raise) when Redis errors."""
        mock_redis = MagicMock()
        mock_redis.delete.side_effect = Exception("Connection refused")

        with patch('app.services.cache._redis', return_value=mock_redis):
            result = cache.delete('some:key')

        assert result is False

    def test_invalidate_does_not_raise_when_redis_down(self):
        """invalidate_class_cache() should never raise even if Redis is down."""
        with patch.object(cache, 'delete', return_value=False):
            try:
                cache.invalidate_class_cache(class_id=1)
            except Exception as e:
                pytest.fail(f"invalidate_class_cache raised unexpectedly: {e}")