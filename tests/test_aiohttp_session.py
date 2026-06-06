import asyncio
import unittest

from aiohttp import web

from app.dataplane.proxy.adapters.session import _AiohttpSession


class AiohttpSessionFallbackTests(unittest.TestCase):
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
