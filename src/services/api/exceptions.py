"""Custom exceptions for API services."""


class AuthenticationError(Exception):
    """Raised when authentication fails or token is invalid."""

    def __init__(self, message="Authentication failed"):
        self.message = message
        super().__init__(self.message)


class APIError(Exception):
    """Raised when API calls fail."""

    def __init__(self, message="API request failed", status_code=None):
        self.message = message
        self.status_code = status_code
        super().__init__(self.message)


class ProjectNotFoundError(APIError):
    """Raised when a project is not found."""

    def __init__(self, project_id):
        super().__init__(f"Project with ID '{project_id}' not found", 404)
