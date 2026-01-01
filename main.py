import asyncio
from utils.logger import setup_logging
from utils.tokens import fetch_tokens


async def main():
    logger = setup_logging()
    logger.info("Polymarket HFT Market Maker started")

    up_token, down_token, market_slug = await fetch_tokens()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nMarket maker stopped by user")
    except Exception as e:
        print(f"Fatal error: {e}")
        exit(1)
