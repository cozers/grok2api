"""HTTP session builder for reverse-proxy requests."""

import asyncio
from typing import Any
from urllib.parse import urlparse

from app.platform.config.snapshot import get_config
from app.platform.errors import UpstreamError
from app.control.proxy.models import ProxyLease
from app.dataplane.proxy.adapters.profile import resolve_proxy_profile

try:
    from curl_cffi.const import CurlOpt
except Exception:  # FreeBSD builds run without curl_cffi.
    CurlOpt = None  # type: ignore[assignment]


def _skip_proxy_ssl(proxy_url: str) -> bool:
    if not proxy_url:
        return False
    cfg = get_config()
    return cfg.get_bool("proxy.egress.skip_ssl_verify", False)


def normalize_proxy_url(url: str) -> str:
    """Normalize SOCKS schemes for consistent DNS-over-proxy behaviour."""
    if not url:
        return url
    scheme = urlparse(url).scheme.lower()
    if scheme == "socks":
        return "socks5h://" + url[len("socks://") :]
    if scheme == "socks5":
        return "socks5h://" + url[len("socks5://") :]
    if scheme == "socks4":
        return "socks4a://" + url[len("socks4://") :]
    return url


def build_session_kwargs(
    *,
    lease: ProxyLease | None = None,
    browser_override: str | None = None,
    extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Build kwargs suitable for the preferred HTTP session implementation."""
    kwargs: dict[str, Any] = dict(extra or {})

    # Browser impersonation.
    if not kwargs.get("impersonate"):
        browser = browser_override or resolve_proxy_profile(lease).browser
        if browser:
            kwargs["impersonate"] = browser

    # Proxy URL.
    proxy_url = ""
    if lease is not None and lease.proxy_url:
        proxy_url = normalize_proxy_url(lease.proxy_url)
        scheme = urlparse(proxy_url).scheme.lower()
        if scheme.startswith("socks"):
            kwargs.setdefault("proxy", proxy_url)
        else:
            kwargs.setdefault("proxies", {"http": proxy_url, "https": proxy_url})

    # curl SSL options for proxy.
    if CurlOpt is not None and _skip_proxy_ssl(proxy_url):
        opts = dict(kwargs.get("curl_options") or {})
        opts[CurlOpt.PROXY_SSL_VERIFYPEER] = 0
        opts[CurlOpt.PROXY_SSL_VERIFYHOST] = 0
        kwargs["curl_options"] = opts

    return kwargs


def _wrap_transport_error(exc: BaseException) -> UpstreamError:
    if isinstance(exc, UpstreamError):
        return exc
    body = str(exc).replace("\n", "\\n")[:400]
    return UpstreamError(
        f"Transport request failed: {exc}",
        status=502,
        body=body,
    )


class ResettableSession:
    """AsyncSession wrapper that resets connection on configurable status codes.

    Designed for long-lived hot-path use; session is recreated transparently
    when a reset-triggering status code is received.
    """

    def __init__(
        self,
        *,
        lease: ProxyLease | None = None,
        browser_override: str | None = None,
        reset_on_status: set[int] | None = None,
        **session_kwargs: Any,
    ) -> None:
        self._kwargs = build_session_kwargs(
            lease=lease,
            browser_override=browser_override,
            extra=session_kwargs or None,
        )
        if reset_on_status is None:
            codes = get_config().get_list("retry.reset_session_status_codes", [403])
            reset_on_status = {int(c) for c in codes}
        self._reset_on = reset_on_status
        self._reset_pending = False
        self._lock = asyncio.Lock()
        self._session = self._create()

    def _create(self):
        try:
            from curl_cffi.requests import AsyncSession

            return AsyncSession(**self._kwargs)
        except ImportError:
            return _AiohttpSession(**self._kwargs)

    async def _maybe_reset(self) -> None:
        if not self._reset_pending:
            return
        async with self._lock:
            if not self._reset_pending:
                return
            self._reset_pending = False
            old, self._session = self._session, self._create()
            try:
                await old.close()
            except Exception:
                pass

    async def _request(self, method: str, *args: Any, **kwargs: Any):
        await self._maybe_reset()
        try:
            response = await getattr(self._session, method)(*args, **kwargs)
        except Exception as exc:
            self._reset_pending = True
            raise _wrap_transport_error(exc) from exc
        if self._reset_on and response.status_code in self._reset_on:
            self._reset_pending = True
        return response

    async def get(self, *args: Any, **kwargs: Any):
        return await self._request("get", *args, **kwargs)

    async def post(self, *args: Any, **kwargs: Any):
        return await self._request("post", *args, **kwargs)

    async def delete(self, *args: Any, **kwargs: Any):
        return await self._request("delete", *args, **kwargs)

    async def close(self) -> None:
        if self._session is not None:
            try:
                await self._session.close()
            finally:
                self._session = None  # type: ignore[assignment]

    async def __aenter__(self) -> "ResettableSession":
        return self

    async def __aexit__(self, *_: Any) -> None:
        await self.close()

    def __getattr__(self, name: str) -> Any:
        return getattr(self._session, name)


class _AiohttpResponse:
    def __init__(self, response, content: bytes | None = None) -> None:
        self._response = response
        self.status_code = response.status
        self.content = content if content is not None else b""

    async def aiter_lines(self):
        pending = b""
        async for raw in self._response.content.iter_any():
            if not raw:
                continue
            pending += raw
            while True:
                nl = pending.find(b"\n")
                if nl < 0:
                    break
                line = pending[:nl]
                pending = pending[nl + 1 :]
                if line.endswith(b"\r"):
                    line = line[:-1]
                yield line.decode("utf-8", "replace")
        if pending:
            if pending.endswith(b"\r"):
                pending = pending[:-1]
            yield pending.decode("utf-8", "replace")
        self._response.release()

    async def aiter_content(self):
        async for chunk in self._response.content.iter_chunked(65536):
            yield chunk
        self._response.release()


class _AiohttpSession:
    """Small curl_cffi-compatible subset backed by aiohttp.

    This fallback is primarily for FreeBSD/serv00 packages where curl_cffi does
    not currently build. Browser TLS impersonation is unavailable in this mode.
    """

    def __init__(self, **kwargs: Any) -> None:
        self._kwargs = kwargs
        self._session = None

    async def _ensure(self):
        if self._session is None:
            import aiohttp

            self._session = aiohttp.ClientSession()
        return self._session

    def _request_kwargs(self, kwargs: dict[str, Any]) -> dict[str, Any]:
        request_kwargs = dict(kwargs)
        request_kwargs.pop("impersonate", None)
        request_kwargs.pop("curl_options", None)
        request_kwargs.pop("allow_redirects", None)
        headers = request_kwargs.get("headers")
        if isinstance(headers, dict):
            headers = dict(headers)
            accept_encoding = headers.get("Accept-Encoding")
            if isinstance(accept_encoding, str) and (
                "br" in accept_encoding.lower() or "zstd" in accept_encoding.lower()
            ):
                headers["Accept-Encoding"] = "gzip, deflate"
            request_kwargs["headers"] = headers
        proxy = self._kwargs.get("proxy")
        proxies = self._kwargs.get("proxies") or {}
        if not proxy and isinstance(proxies, dict):
            proxy = proxies.get("https") or proxies.get("http")
        if proxy:
            request_kwargs["proxy"] = proxy
        return request_kwargs

    async def _request(self, method: str, url: str, **kwargs: Any):
        session = await self._ensure()
        stream = bool(kwargs.pop("stream", False))
        allow_redirects = kwargs.pop("allow_redirects", True)
        request_kwargs = self._request_kwargs(kwargs)
        response = await session.request(
            method.upper(),
            url,
            allow_redirects=allow_redirects,
            **request_kwargs,
        )
        if stream:
            return _AiohttpResponse(response)
        content = await response.read()
        response.release()
        return _AiohttpResponse(response, content)

    async def get(self, url: str, **kwargs: Any):
        return await self._request("GET", url, **kwargs)

    async def post(self, url: str, **kwargs: Any):
        return await self._request("POST", url, **kwargs)

    async def delete(self, url: str, **kwargs: Any):
        return await self._request("DELETE", url, **kwargs)

    async def close(self) -> None:
        if self._session is not None:
            await self._session.close()
            self._session = None


__all__ = [
    "ResettableSession",
    "build_session_kwargs",
    "normalize_proxy_url",
]
