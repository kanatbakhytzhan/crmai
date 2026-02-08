"""
Centralized error handling with consistent response format and request_id tracking.
"""
import uuid
from typing import Optional, Dict, Any
from fastapi import Request, status
from fastapi.responses import JSONResponse
from pydantic import BaseModel


class ErrorResponse(BaseModel):
    """Consistent error response format for all API endpoints."""
    ok: bool = False
    code: str
    message: str
    details: Optional[Dict[str, Any]] = None
    request_id: str


class APIError(Exception):
    """Base exception for API errors with consistent format."""
    
    def __init__(
        self,
        code: str,
        message: str,
        status_code: int = status.HTTP_400_BAD_REQUEST,
        details: Optional[Dict[str, Any]] = None,
    ):
        self.code = code
        self.message = message
        self.status_code = status_code
        self.details = details
        super().__init__(message)


class LeadNotFoundError(APIError):
    """Lead not found error."""
    
    def __init__(self, lead_id: int, details: Optional[Dict[str, Any]] = None):
        super().__init__(
            code="LEAD_NOT_FOUND",
            message=f"Lead with ID {lead_id} not found",
            status_code=status.HTTP_404_NOT_FOUND,
            details=details,
        )


class UnauthorizedError(APIError):
    """Unauthorized access error."""
    
    def __init__(self, message: str = "Not authenticated", details: Optional[Dict[str, Any]] = None):
        super().__init__(
            code="UNAUTHORIZED",
            message=message,
            status_code=status.HTTP_401_UNAUTHORIZED,
            details=details,
        )


class ForbiddenError(APIError):
    """Forbidden access error."""
    
    def __init__(self, message: str = "Forbidden", details: Optional[Dict[str, Any]] = None):
        super().__init__(
            code="FORBIDDEN",
            message=message,
            status_code=status.HTTP_403_FORBIDDEN,
            details=details,
        )


class ValidationError(APIError):
    """Validation error."""
    
    def __init__(self, message: str, details: Optional[Dict[str, Any]] = None):
        super().__init__(
            code="VALIDATION_ERROR",
            message=message,
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            details=details,
        )


class InvalidStatusError(ValidationError):
    """Invalid status value error."""
    
    def __init__(self, status_value: str, allowed: list[str]):
        super().__init__(
            message=f"Invalid status '{status_value}'. Allowed: {', '.join(allowed)}",
            details={"status": status_value, "allowed": allowed},
        )


def get_request_id(request: Request) -> str:
    """Get or generate request_id for the current request."""
    if hasattr(request.state, "request_id"):
        return request.state.request_id
    request_id = str(uuid.uuid4())
    request.state.request_id = request_id
    return request_id


def create_error_response(
    request: Request,
    code: str,
    message: str,
    status_code: int = status.HTTP_400_BAD_REQUEST,
    details: Optional[Dict[str, Any]] = None,
) -> JSONResponse:
    """Create a consistent error response with request_id."""
    request_id = get_request_id(request)
    error = ErrorResponse(
        ok=False,
        code=code,
        message=message,
        details=details,
        request_id=request_id,
    )
    return JSONResponse(
        status_code=status_code,
        content=error.model_dump(exclude_none=True),
    )


def create_success_response(
    request: Request,
    data: Dict[str, Any],
) -> Dict[str, Any]:
    """Add request_id to success response."""
    request_id = get_request_id(request)
    return {
        **data,
        "request_id": request_id,
    }
