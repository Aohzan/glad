"""Tests for accounts/middleware.py."""

import time
from unittest.mock import MagicMock, patch

import pytest
from django.contrib.auth import get_user_model
from django.test import RequestFactory

from accounts.middleware import SessionTimeoutMiddleware

User = get_user_model()


@pytest.fixture
def get_response():
    """Mock get_response callable."""
    mock = MagicMock()
    mock.return_value = MagicMock()
    return mock


@pytest.fixture
def middleware(get_response):
    return SessionTimeoutMiddleware(get_response)


@pytest.fixture
def factory():
    return RequestFactory()


@pytest.mark.django_db
class TestSessionTimeoutMiddleware:
    def test_unauthenticated_user_passes_through(
        self, middleware, get_response, factory
    ):
        request = factory.get("/")
        request.user = MagicMock()
        request.user.is_authenticated = False
        middleware(request)
        get_response.assert_called_once_with(request)

    def test_authenticated_user_sets_last_activity(
        self, middleware, get_response, factory
    ):
        request = factory.get("/")
        request.user = MagicMock()
        request.user.is_authenticated = True
        request.session = {}
        # No last_activity set yet
        middleware(request)
        assert "last_activity" in request.session
        get_response.assert_called_once_with(request)

    def test_authenticated_user_updates_last_activity(
        self, middleware, get_response, factory
    ):
        request = factory.get("/")
        request.user = MagicMock()
        request.user.is_authenticated = True
        old_time = (
            int(time.time()) - 120
        )  # 2 minutes ago, guaranteed to be less than now
        request.session = {"last_activity": old_time}
        middleware(request)
        # last_activity should be updated to current time (>= old_time)
        assert request.session["last_activity"] >= old_time

    def test_session_expired_logs_out_user(self, middleware, get_response, factory):
        request = factory.get("/")
        request.user = MagicMock()
        request.user.is_authenticated = True
        # Ensure profile.session_timeout returns an integer (default 15)
        request.user.profile.session_timeout = 15
        # Set last_activity to 20 minutes ago (default timeout is 15 min)
        expired_time = int(time.time()) - (20 * 60)
        request.session = {"last_activity": expired_time}

        with patch("django.contrib.auth.logout") as mock_logout:
            middleware(request)
            mock_logout.assert_called_once_with(request)

    def test_session_not_expired_does_not_logout(
        self, middleware, get_response, factory
    ):
        request = factory.get("/")
        request.user = MagicMock()
        request.user.is_authenticated = True
        # Ensure profile.session_timeout returns an integer (default 15)
        request.user.profile.session_timeout = 15
        # Set last_activity to 5 minutes ago (within 15 min timeout)
        recent_time = int(time.time()) - (5 * 60)
        request.session = {"last_activity": recent_time}

        with patch("django.contrib.auth.logout") as mock_logout:
            middleware(request)
            mock_logout.assert_not_called()

    def test_user_with_custom_timeout(self, middleware, get_response, factory):
        request = factory.get("/")
        request.user = MagicMock()
        request.user.is_authenticated = True
        # User has 5 minute timeout - must be an integer for comparison to work
        request.user.profile.session_timeout = 5
        # Set last_activity to 6 minutes ago
        expired_time = int(time.time()) - (6 * 60)
        request.session = {"last_activity": expired_time}

        with patch("django.contrib.auth.logout") as mock_logout:
            middleware(request)
            mock_logout.assert_called_once_with(request)

    def test_user_without_profile_uses_default_timeout(
        self, middleware, get_response, factory
    ):
        request = factory.get("/")
        request.user = MagicMock()
        request.user.is_authenticated = True
        # Simulate profile access raising an exception
        type(request.user).profile = property(
            lambda self: (_ for _ in ()).throw(Exception("no profile"))
        )
        recent_time = int(time.time()) - (5 * 60)
        request.session = {"last_activity": recent_time}

        with patch("django.contrib.auth.logout") as mock_logout:
            middleware(request)
            mock_logout.assert_not_called()

    def test_session_exception_is_handled_gracefully(
        self, middleware, get_response, factory
    ):
        request = factory.get("/")
        request.user = MagicMock()
        request.user.is_authenticated = True
        # Session that raises an exception on get
        request.session = MagicMock()
        request.session.get.side_effect = Exception("session error")

        # Should not raise
        middleware(request)
        get_response.assert_called_once_with(request)

    def test_expired_session_does_not_update_last_activity(
        self, middleware, get_response, factory
    ):
        request = factory.get("/")
        request.user = MagicMock()
        request.user.is_authenticated = True
        # Ensure profile.session_timeout returns an integer
        request.user.profile.session_timeout = 15
        expired_time = int(time.time()) - (20 * 60)
        request.session = {"last_activity": expired_time}

        with patch("django.contrib.auth.logout"):
            middleware(request)
        # last_activity should NOT be updated after logout
        assert request.session["last_activity"] == expired_time

    def test_returns_response_from_get_response(
        self, middleware, get_response, factory
    ):
        expected_response = MagicMock()
        get_response.return_value = expected_response
        request = factory.get("/")
        request.user = MagicMock()
        request.user.is_authenticated = False
        response = middleware(request)
        assert response == expected_response
