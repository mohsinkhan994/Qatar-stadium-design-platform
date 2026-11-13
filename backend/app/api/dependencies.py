"""Authentication dependencies shared by API routers."""
import hmac
from fastapi import Header, HTTPException, Request


def kiosk_auth(request: Request, authorization: str | None = Header(default=None)):
    settings = request.app.state.settings
    if settings.kiosk_api_key and not hmac.compare_digest(authorization or "", f"Bearer {settings.kiosk_api_key}"):
        raise HTTPException(401, "Invalid kiosk token")


def admin_auth(request: Request, x_admin_key: str | None = Header(default=None)):
    settings = request.app.state.settings
    if not settings.admin_api_key:
        raise HTTPException(503, "Set ADMIN_API_KEY on the backend to enable staff access")
    if not hmac.compare_digest(x_admin_key or "", settings.admin_api_key):
        raise HTTPException(401, "Invalid staff token")
