"""
Session Management Service for TestAgent Tool

This module provides centralized authentication token management
following the Singleton pattern to ensure consistent access across
the application.
"""

import json
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, Optional

from services.logging_config import get_logger

logger = get_logger("session")


class SessionManager:
    """
    Singleton session manager for handling authentication tokens and user state.

    This class ensures that authentication tokens are properly managed,
    stored securely, and accessible throughout the application lifecycle.
    """

    _instance: Optional["SessionManager"] = None
    _initialized: bool = False

    def __new__(cls) -> "SessionManager":
        """Ensure only one instance of SessionManager exists."""
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self):
        """Initialize the session manager (only once)."""
        if not self._initialized:
            self._access_token: Optional[str] = None
            self._user_info: Optional[Dict[str, Any]] = None
            self._token_expires_at: Optional[datetime] = None
            self._session_file = self._get_session_file_path()
            self._load_session()
            SessionManager._initialized = True

    def _get_session_file_path(self) -> Path:
        """Get the path for storing session data."""
        # Store in user's app data directory
        app_data_dir = Path.home() / ".testagent"
        app_data_dir.mkdir(exist_ok=True)
        return app_data_dir / "session.json"

    def _load_session(self) -> None:
        """Load existing session from disk if available."""
        try:
            if self._session_file.exists():
                with open(self._session_file, "r", encoding="utf-8") as f:
                    session_data = json.load(f)

                # Check if token is still valid
                expires_str = session_data.get("expires_at")
                if expires_str:
                    expires_at = datetime.fromisoformat(expires_str)
                    if expires_at > datetime.now():
                        self._access_token = session_data.get("access_token")
                        self._user_info = session_data.get("user_info")
                        self._token_expires_at = expires_at
                    else:
                        # Token expired, clear it
                        self._clear_session_file()
        except (json.JSONDecodeError, FileNotFoundError, KeyError) as e:
            # If there's any issue loading session, start fresh
            logger.warning("Could not load session data: %s", e)
            self._clear_session_file()

    def _save_session(self) -> None:
        """Save current session to disk."""
        try:
            session_data = {
                "access_token": self._access_token,
                "user_info": self._user_info,
                "expires_at": (
                    self._token_expires_at.isoformat()
                    if self._token_expires_at
                    else None
                ),
                "saved_at": datetime.now().isoformat(),
            }

            with open(self._session_file, "w", encoding="utf-8") as f:
                json.dump(session_data, f, indent=2)

        except Exception as e:
            logger.warning("Could not save session data: %s", e)

    def _clear_session_file(self) -> None:
        """Clear the session file from disk."""
        try:
            if self._session_file.exists():
                self._session_file.unlink()
        except Exception as e:
            logger.warning("Could not clear session file: %s", e)

    def set_access_token(
        self,
        token: str,
        user_info: Optional[Dict[str, Any]] = None,
        expires_in_hours: int = 24,
    ) -> None:
        """
        Set the access token and related user information.

        Args:
            token: The access token string
            user_info: Optional user information dictionary
            expires_in_hours: Token expiry time in hours (default 24)
        """
        self._access_token = token
        self._user_info = user_info or {}
        self._token_expires_at = datetime.now() + timedelta(hours=expires_in_hours)
        self._save_session()

    def get_access_token(self) -> Optional[str]:
        """
        Get the current access token if valid.

        Returns:
            The access token string if valid, None otherwise
        """
        if self._access_token and self._is_token_valid():
            return self._access_token
        return None

    def _is_token_valid(self) -> bool:
        """Check if the current token is still valid."""
        if not self._token_expires_at:
            return False
        return datetime.now() < self._token_expires_at

    def get_user_info(self) -> Optional[Dict[str, Any]]:
        """
        Get the current user information.

        Returns:
            User information dictionary if available, None otherwise
        """
        if self._is_token_valid():
            return self._user_info
        return None

    def is_authenticated(self) -> bool:
        """
        Check if user is currently authenticated with a valid token.

        Returns:
            True if authenticated with valid token, False otherwise
        """
        return self.get_access_token() is not None

    def logout(self) -> None:
        """Clear all session data and logout the user."""
        self._access_token = None
        self._user_info = None
        self._token_expires_at = None
        self._clear_session_file()

    def get_auth_headers(self) -> Dict[str, str]:
        """
        Get authorization headers for API requests.

        Returns:
            Dictionary with authorization headers if token is valid,
            empty dict otherwise
        """
        token = self.get_access_token()
        if token:
            return {
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json",
            }
        return {"Content-Type": "application/json"}

    def refresh_token_if_needed(self) -> bool:
        """
        Check if token needs refresh and handle it.

        Returns:
            True if token is valid or refreshed successfully, False otherwise
        """
        if not self._token_expires_at:
            return False

        # Check if token expires within next 30 minutes
        if datetime.now() + timedelta(minutes=30) >= self._token_expires_at:
            # Token needs refresh - for now just return False
            # In a real implementation, you would call the refresh endpoint
            logger.info("Token needs refresh - please re-authenticate")
            return False

        return True


# Global session manager instance
session_manager = SessionManager()
