"""Entry point: `python -m app`. Checks configuration before starting the server."""

import logging
import os
import sys

import uvicorn
from dotenv import load_dotenv

from app.settings import ConfigError, load_settings


def main() -> None:
    load_dotenv()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    try:
        load_settings()
    except ConfigError as error:
        print(f"Configuration error: {error}", file=sys.stderr)
        sys.exit(1)
    uvicorn.run(
        "app.main:app",
        host=os.environ.get("HOST", "127.0.0.1"),
        port=int(os.environ.get("PORT", "8000")),
    )


if __name__ == "__main__":
    main()
