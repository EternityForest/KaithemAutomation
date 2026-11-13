from collections.abc import Awaitable, Callable
from functools import wraps
from typing import ParamSpec, TypeVar
from urllib.parse import urlparse

from quart import Quart, ResponseReturnValue, make_response, request

P = ParamSpec("P")
R = TypeVar("R", bound=ResponseReturnValue)

app = Quart(__name__)


def _get_base_domain(hostname: str) -> str:
    """Extract the base domain (e.g. 'sub.example.com' -> 'example.com')."""
    if not hostname:
        return ""
    host = hostname.split(":")[0].lower()
    parts = host.split(".")
    # Use `tldextract` instead for multi-part TLDs like .co.uk.
    if len(parts) >= 2:
        return ".".join(parts[-2:])
    return host


def _is_allowed_subdomain(origin: str, request_host: str) -> bool:
    """Check if the origin is the base domain or a subdomain of the host."""
    parsed_origin = urlparse(origin)
    origin_host = (parsed_origin.hostname or "").lower()
    req_host = request_host.split(":")[0].lower()

    if not origin_host or not req_host:
        return False

    origin_base = _get_base_domain(origin_host)
    request_base = _get_base_domain(req_host)

    if not origin_base or origin_base != request_base:
        return False

    return origin_host == request_base or origin_host.endswith(
        f".{request_base}"
    )


def allow_request_subdomains(
    allow_credentials: bool = True,
    allow_methods: list[str] | None = None,
    allow_headers: list[str] | None = None,
) -> Callable[
    [Callable[P, Awaitable[R]]],
    Callable[P, Awaitable[ResponseReturnValue]],
]:
    """Allow CORS from any subdomain of the domain being requested."""
    methods_str = ", ".join(
        allow_methods or ["GET", "POST", "PUT", "DELETE", "OPTIONS"]
    )
    headers_str = ", ".join(allow_headers or ["Content-Type", "Authorization"])

    def decorator(
        func: Callable[P, Awaitable[R]],
    ) -> Callable[P, Awaitable[ResponseReturnValue]]:
        @wraps(func)
        async def wrapper(
            *args: P.args, **kwargs: P.kwargs
        ) -> ResponseReturnValue:
            origin = request.headers.get("Origin")
            is_valid_origin = bool(
                origin and _is_allowed_subdomain(origin, request.host)
            )

            # Intercept browser preflight OPTIONS requests automatically
            if request.method == "OPTIONS":
                response = await make_response("", 204)
            else:
                result = await func(*args, **kwargs)
                response = await make_response(result)

            # Attach CORS headers if the origin is the same root domain
            if is_valid_origin and origin:
                headers = response.headers
                headers["Access-Control-Allow-Origin"] = origin
                headers["Access-Control-Allow-Methods"] = methods_str
                headers["Access-Control-Allow-Headers"] = headers_str
                headers["Vary"] = "Origin"
                if allow_credentials:
                    headers["Access-Control-Allow-Credentials"] = "true"

            return response

        return wrapper

    return decorator
