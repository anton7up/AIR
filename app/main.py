import asyncio
import logging

import uvicorn

from app.api.main import app as api_app
from app.bot.app import run_bot
from app.core.config import get_settings


async def main() -> None:
    settings = get_settings()
    logging.basicConfig(
        level=settings.log_level,
        format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    )
    server = uvicorn.Server(
        uvicorn.Config(
            api_app,
            host=settings.api_host,
            port=settings.api_port,
            log_level=settings.log_level.lower(),
            proxy_headers=False,
            server_header=False,
        )
    )
    await asyncio.gather(server.serve(), run_bot(settings))


if __name__ == "__main__":
    asyncio.run(main())
