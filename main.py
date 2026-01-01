import time
import asyncio
from utils.logger import setup_logging
from utils.tokens import fetch_tokens
from utils.clob_client import init_clob_client
from utils.orderbook import OrderBook
from utils.market_time import is_in_trading_window


async def main():
    logger = setup_logging()
    logger.info("Polymarket HFT Market Maker started")

    up_token, down_token, market_slug = await fetch_tokens()
    client = await init_clob_client()
    book = OrderBook(up_token, down_token, market_slug)
    book.start()

    while True:
        if not is_in_trading_window():

            book.stop()
            logger.info("Trading session ended. Starting new session.")

            up_token, down_token, market_slug = await fetch_tokens()
            book = OrderBook(up_token, down_token, market_slug)
            book.start()

        await asyncio.sleep(1)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nMarket maker stopped by user")
    except Exception as e:
        print(f"Fatal error: {e}")
        exit(1)
