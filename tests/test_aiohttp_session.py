import asyncio
import sys
import types
import unittest
from unittest import mock

from aiohttp import web

from app.dataplane.proxy.adapters.session import (
    ResettableSession,
    _AiohttpSession,
    _PrimpSession,
    _primp_impersonate_name,
)


class AiohttpSessionFallbackTests(unittest.TestCase):
    def test_primp_impersonate_name_normalizes_curl_cffi_browser(self):
        self.assertEqual(_primp_impersonate_name("chrome136"), "chrome_136")
        self.assertEqual(_primp_impersonate_name("edge131"), "edge_131")
        self.assertEqual(_primp_impersonate_name("chrome_120"), "chrome_120")

    def test_resettable_session_uses_primp_before_aiohttp_when_curl_cffi_missing(self):
        fake_primp = types.SimpleNamespace(AsyncClient=object)

        with mock.patch.dict(
            sys.modules,
            {
                "curl_cffi": None,
                "curl_cffi.requests": None,
                "primp": fake_primp,
            },
        ):
            session = ResettableSession(reset_on_status=set())
            try:
                self.assertIsInstance(session._session, _PrimpSession)
            finally:
                asyncio.run(session.close())

    def test_request_kwargs_downgrades_unsupported_accept_encoding(self):
        session = _AiohttpSession()
        kwargs = session._request_kwargs(
            {
                "headers": {
                    "Accept-Encoding": "gzip, deflate, br, zstd",
                    "User-Agent": "test",
                },
                "impersonate": "chrome120",
                "curl_options": {},
            }
        )

        self.assertEqual(kwargs["headers"]["Accept-Encoding"], "gzip, deflate")
        self.assertEqual(kwargs["headers"]["User-Agent"], "test")
        self.assertNotIn("impersonate", kwargs)
        self.assertNotIn("curl_options", kwargs)

    def test_aiter_lines_buffers_chunks_until_newline(self):
        async def run_case():
            async def handler(request):
                response = web.StreamResponse(
                    status=200,
                    headers={"Content-Type": "text/event-stream"},
                )
                await response.prepare(request)
                for chunk in (
                    b'data: {"result":{"response":{"token":"hel',
                    b'lo","messageTag":"final"}}}\r\n',
                    b"\r\n",
                    b"data: [DONE]\n\n",
                ):
                    await response.write(chunk)
                await response.write_eof()
                return response

            app = web.Application()
            app.router.add_post("/sse", handler)
            runner = web.AppRunner(app)
            await runner.setup()
            site = web.TCPSite(runner, "127.0.0.1", 0)
            await site.start()
            sockets = site._server.sockets
            port = sockets[0].getsockname()[1]

            session = _AiohttpSession()
            try:
                response = await session.post(
                    f"http://127.0.0.1:{port}/sse",
                    stream=True,
                )
                return [line async for line in response.aiter_lines()]
            finally:
                await session.close()
                await runner.cleanup()

        self.assertEqual(
            asyncio.run(run_case()),
            [
                'data: {"result":{"response":{"token":"hello","messageTag":"final"}}}',
                "",
                "data: [DONE]",
                "",
            ],
        )


if __name__ == "__main__":
    unittest.main()
