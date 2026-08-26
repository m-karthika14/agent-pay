"""
Purpose: Unit tests for app.mcp.server's DNS-rebinding transport security
settings (plan.md Section 17).

The MCP Streamable HTTP transport validates every request's Host/Origin
header before it reaches any tool. Its own default only allowlists
localhost, which made every real request to the deployed backend fail with
HTTP 421 "Invalid Host header" once it left localhost -- this proves the
fix: the deployed Render hostname is now accepted, and an arbitrary/
untrusted hostname is still rejected (DNS-rebinding protection itself
stays on, not disabled).

Tests go through TransportSecurityMiddleware.validate_request() -- the
SDK's real, public validation entrypoint -- against a synthetic Starlette
Request built from a bare ASGI scope, rather than a full HTTP round-trip:
DNS-rebinding validation is a pure function of the Host/Origin header
strings with no need for a real network hop (and, per
tests/integration/test_mcp_tools.py's own _mcp_client_session() comment,
an in-process ASGITransport doesn't reliably simulate a spoofable Host
header anyway).
"""
from starlette.requests import Request

from app.mcp.server import _mcp_transport_security
from mcp.server.transport_security import TransportSecurityMiddleware


def _request_with_headers(headers: dict[str, str]) -> Request:
    """Build a minimal Starlette Request carrying only the given headers."""
    scope = {
        "type": "http",
        "method": "GET",
        "path": "/",
        "headers": [(key.lower().encode(), value.encode()) for key, value in headers.items()],
    }
    return Request(scope)


def _middleware() -> TransportSecurityMiddleware:
    return TransportSecurityMiddleware(_mcp_transport_security())


async def test_dns_rebinding_protection_stays_enabled() -> None:
    """Must never be silently disabled -- that would accept a request claiming to be any host."""
    assert _mcp_transport_security().enable_dns_rebinding_protection is True


async def test_deployed_render_hostname_is_accepted() -> None:
    request = _request_with_headers({"host": "agentpay-backend-wd5u.onrender.com"})
    assert await _middleware().validate_request(request) is None


async def test_deployed_render_hostname_with_port_is_accepted() -> None:
    request = _request_with_headers({"host": "agentpay-backend-wd5u.onrender.com:443"})
    assert await _middleware().validate_request(request) is None


async def test_local_dev_hosts_are_still_accepted() -> None:
    for host in ("localhost:8000", "localhost:5173", "127.0.0.1:8000"):
        request = _request_with_headers({"host": host})
        assert await _middleware().validate_request(request) is None, host


async def test_unrelated_hostname_is_rejected() -> None:
    """DNS-rebinding protection must still reject any host that was never allowlisted."""
    for host in ("evil-attacker.example.com", "agentpay-backend-wd5u.onrender.com.evil.com", "onrender.com"):
        request = _request_with_headers({"host": host})
        response = await _middleware().validate_request(request)
        assert response is not None, host
        assert response.status_code == 421


async def test_missing_host_header_is_rejected() -> None:
    request = _request_with_headers({})
    response = await _middleware().validate_request(request)
    assert response is not None
    assert response.status_code == 421


async def test_configured_cors_origin_is_accepted() -> None:
    """allowed_origins is reused from CORS_ORIGINS -- whatever that's set to must be allowed here too."""
    trusted_origin = _mcp_transport_security().allowed_origins[0]
    request = _request_with_headers({"host": "agentpay-backend-wd5u.onrender.com", "origin": trusted_origin})
    assert await _middleware().validate_request(request) is None


async def test_unrelated_origin_is_rejected() -> None:
    request = _request_with_headers(
        {"host": "agentpay-backend-wd5u.onrender.com", "origin": "https://attacker.example.com"}
    )
    response = await _middleware().validate_request(request)
    assert response is not None
    assert response.status_code == 403
