"""Middleware for the accounts app."""

import time
from inspect import iscoroutinefunction, markcoroutinefunction

from asgiref.sync import sync_to_async


class SessionTimeoutMiddleware:
    """Middleware to handle per-user session timeout based on inactivity.

    The middleware is declared async-capable so the chain stays on the event
    loop when served through ASGI: a sync-only middleware makes Django bridge
    everything below it through ``AsyncToSync``, which costs a thread hop on
    every request and turns client disconnections into noisy
    ``CancelledError`` tracebacks logged by asyncio.
    """

    async_capable = True
    sync_capable = True

    def __init__(self, get_response):
        self.get_response = get_response
        self.async_mode = iscoroutinefunction(get_response)
        if self.async_mode:
            markcoroutinefunction(self)

    def __call__(self, request):
        if self.async_mode:
            return self.__acall__(request)
        self._refresh_activity(request)
        return self.get_response(request)

    async def __acall__(self, request):
        # The session and the user profile hit the database, so the check runs
        # in a worker thread rather than on the event loop.
        await sync_to_async(self._refresh_activity)(request)
        return await self.get_response(request)

    @staticmethod
    def _refresh_activity(request) -> None:
        """Log the user out when idle for too long, else stamp the session."""
        if not request.user.is_authenticated:
            return

        # Check if this is a session timeout check
        try:
            last_activity = request.session.get("last_activity")
            current_time = int(time.time())

            # Get user's timeout preference (in minutes), default to 15
            timeout_minutes = 15
            try:
                if hasattr(request.user, "profile"):
                    timeout_minutes = request.user.profile.session_timeout
            except Exception:
                pass  # Use default if profile doesn't exist yet

            timeout_seconds = timeout_minutes * 60

            # Check if session has expired
            if last_activity and (current_time - last_activity) > timeout_seconds:
                # Session expired, logout the user
                from django.contrib.auth import logout

                logout(request)
                # Don't update last_activity since we're logging out
            else:
                # Update last activity timestamp
                request.session["last_activity"] = current_time

        except Exception:
            # If anything goes wrong, just continue
            pass
