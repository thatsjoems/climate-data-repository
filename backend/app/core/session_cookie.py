"""
The refresh token travels in a cookie the page's scripts cannot read (observation O2 of docs/PENTEST_CHECKLIST.md).

Before, both tokens were kept in the browser's localStorage, so a cross-site-scripting flaw anywhere in the page could have copied them. Now:
  * the REFRESH token (the long-lived one) is set by the server as an HttpOnly cookie: JavaScript can neither read nor copy it;
  * the ACCESS token (15 minutes) is returned in the answer and kept by the page in memory only; a page reload gets a new one with the cookie.

The cookie is
  * HttpOnly      - not readable by scripts;
  * Secure        - sent over HTTPS only (always in production; development over plain http cannot set it);
  * SameSite=Strict - never sent with a request that starts on another site, which is also the main defence against cross-site request forgery;
  * Path=/api/auth  - sent only to the sign-in endpoints, never with ordinary data requests.
As a second defence, the two endpoints that use the cookie (refresh and logout) also require the header X-CDR-Client: web, which a form or a link on
another site cannot add.
"""
from fastapi import HTTPException, Request, Response, status

from app.core.config import settings
from app.core.startup_checks import is_production

REFRESH_COOKIE = "cdr_refresh"
CLIENT_HEADER = "x-cdr-client"
CLIENT_VALUE = "web"


def _path() -> str:
    return f"{settings.API_V1_PREFIX}/auth"


def _secure() -> bool:
    configured = settings.REFRESH_COOKIE_SECURE
    return configured if configured is not None else is_production(settings.ENVIRONMENT)


def set_refresh_cookie(response: Response, raw_token: str) -> None:
    response.set_cookie(
        key=REFRESH_COOKIE,
        value=raw_token,
        max_age=settings.REFRESH_TOKEN_EXPIRE_DAYS * 24 * 3600,
        path=_path(),
        httponly=True,
        secure=_secure(),
        samesite="strict",
    )


def clear_refresh_cookie(response: Response) -> None:
    response.delete_cookie(key=REFRESH_COOKIE, path=_path(), httponly=True, secure=_secure(), samesite="strict")


def read_refresh_cookie(request: Request) -> str | None:
    return request.cookies.get(REFRESH_COOKIE) or None


def require_web_client(request: Request) -> None:
    """Refuses a request to a cookie endpoint that does not carry the header only our own page adds."""
    if request.headers.get(CLIENT_HEADER) != CLIENT_VALUE:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="This request must come from the application")
