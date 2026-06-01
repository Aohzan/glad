"""Middleware for the accounts app."""

import time


class SessionTimeoutMiddleware:
    """Middleware to handle per-user session timeout based on inactivity."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if request.user.is_authenticated:
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

        response = self.get_response(request)
        return response
