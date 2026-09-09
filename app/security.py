"""Security headers applied to every response.

The Content-Security-Policy only allows same-origin resources. ``'unsafe-eval'``
is required by Alpine.js (it compiles ``x-data`` expressions with ``new
Function``) and ``'unsafe-inline'`` for styles because Alpine and Chart.js set
inline ``style`` attributes. Frames, objects, base URI and form targets are
locked to the origin. HSTS is only sent when ``ENABLE_HSTS`` is true
(production behind HTTPS); otherwise browsers would cache it for plain HTTP
development hosts.
"""

from __future__ import annotations

from urllib.parse import urlsplit

from flask import Flask, Response, current_app, url_for

CSP_DIRECTIVES: dict[str, str] = {
    "default-src": "'self'",
    "script-src": "'self' 'unsafe-eval'",
    "style-src": "'self' 'unsafe-inline'",
    "img-src": "'self' data: blob:",
    "font-src": "'self' data:",
    "connect-src": "'self'",
    "frame-ancestors": "'none'",
    "base-uri": "'self'",
    "form-action": "'self'",
    "object-src": "'none'",
}
CONTENT_SECURITY_POLICY = "; ".join(f"{name} {value}" for name, value in CSP_DIRECTIVES.items())
HSTS_VALUE = "max-age=31536000; includeSubDomains"
PERMISSIONS_POLICY = "camera=(), microphone=(), geolocation=(), payment=()"


def register_security_headers(app: Flask) -> None:
    """Add the ``after_request`` hook that sets the security headers."""
    app.after_request(_apply_security_headers)


def _apply_security_headers(response: Response) -> Response:
    headers = response.headers
    headers.setdefault("Content-Security-Policy", CONTENT_SECURITY_POLICY)
    headers.setdefault("X-Content-Type-Options", "nosniff")
    headers.setdefault("X-Frame-Options", "DENY")
    headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
    headers.setdefault("Permissions-Policy", PERMISSIONS_POLICY)
    if current_app.config["ENABLE_HSTS"]:
        headers.setdefault("Strict-Transport-Security", HSTS_VALUE)
    return response


def safe_redirect_target(target: str | None, fallback_endpoint: str) -> str:
    """A relative path inside this site, or the fallback endpoint.

    Anything with a scheme or a host (``//evil.example``, ``https://evil``) is
    thrown away: a redirect the visitor did not ask for is a phishing tool.
    """
    if target:
        parts = urlsplit(target)
        if not parts.scheme and not parts.netloc and target.startswith("/"):
            return target
    return url_for(fallback_endpoint)
