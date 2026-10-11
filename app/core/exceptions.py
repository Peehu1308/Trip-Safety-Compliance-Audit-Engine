class AppError(Exception):
    def __init__(self, code: str, message: str, http_status: int = 500):
        self.code = code
        self.message = message
        self.http_status = http_status
        super().__init__(message)

class NotFound(AppError):
    def __init__(self, message: str = "Resource not found"):
        super().__init__("NOT_FOUND", message, 404)

class Conflict(AppError):
    def __init__(self, message: str = "Conflict"):
        super().__init__("CONFLICT", message, 409)

class Forbidden(AppError):
    def __init__(self, message: str = "Forbidden"):
        super().__init__("FORBIDDEN", message, 403)

class Unauthorized(AppError):
    def __init__(self, message: str = "Unauthorized"):
        super().__init__("UNAUTHORIZED", message, 401)

class ValidationFailed(AppError):
    def __init__(self, message: str = "Validation failed"):
        super().__init__("VALIDATION_FAILED", message, 422)

class StopFrozen(AppError):
    def __init__(self, message: str = "Stop is frozen"):
        super().__init__("STOP_FROZEN", message, 423)

class TooManyRequests(AppError):
    def __init__(self, message: str = "Too many requests"):
        super().__init__("TOO_MANY_REQUESTS", message, 429)
