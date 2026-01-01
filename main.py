import time
import asyncio
import requests
from utils.logger import setup_logging
from utils.tokens import fetch_tokens
from utils.clob_client_and_order import init_clob_client
from utils.orderbook import OrderBook, SIGNALES
from utils.market_time import is_in_trading_window, get_period_elapsed_seconds
from utils.clob_client_and_order import (
    place_anchor_and_hedge,
    cache_tocken_trading_infos,
)


session = requests.Session()
requests.get = session.get
requests.post = session.post
requests.put = session.put
requests.patch = session.patch
requests.delete = session.delete
requests.head = session.head
requests.options = session.options


async def main():
    max_trades = 1
    trades = 0

    logger = setup_logging()
    logger.info("Polymarket HFT Market Maker started")

    up_token, down_token, market_slug = await fetch_tokens()
    client = init_clob_client()
    book = OrderBook(up_token, down_token, market_slug)
    await asyncio.create_task(cache_tocken_trading_infos(client, book))
    book.start()

    await asyncio.sleep(5)  # Allow some time for initial order book data

    market_data = book.get_current_market_data()

    up_bid_price = market_data["best_bid_price"]
    up_ask_price = market_data["best_ask_price"]
    down_ask_price = 1 - up_bid_price
    down_bid_price = 1 - up_ask_price

    print(
        f"Initial Prices - UP: {up_bid_price:.2f}/{up_ask_price:.2f} | DOWN: {down_bid_price:.2f}/{down_ask_price:.2f}",
        flush=True,
    )

    while True:
        if not is_in_trading_window():

            book.stop()
            logger.info("Trading session ended. Starting new session.")
            await asyncio.sleep(10)
            up_token, down_token, market_slug = await fetch_tokens()
            book = OrderBook(up_token, down_token, market_slug)
            asyncio.create_task(cache_tocken_trading_infos(client, book))
            book.start()

        market_data = book.get_current_market_data()
        if not market_data:
            continue

        up_bid_price = market_data["best_bid_price"]
        up_ask_price = market_data["best_ask_price"]

        down_ask_price = 1 - up_bid_price
        down_bid_price = 1 - up_ask_price

        if trades < max_trades:
            trading_side = book.last_signal

            if trading_side == SIGNALES.UP:
                await place_anchor_and_hedge(
                    client,
                    up_token,
                    down_token,
                    "UP",
                    up_bid_price,
                    size=5,
                )
                trades += 1
                logger.info(
                    f"Placed UP anchor and hedge orders. Total trades: {trades}"
                )

            elif trading_side == SIGNALES.DOWN:
                await place_anchor_and_hedge(
                    client,
                    up_token,
                    down_token,
                    "DOWN",
                    down_bid_price,
                    size=5,
                )
                trades += 1
                logger.info(
                    f"Placed DOWN anchor and hedge orders. Total trades: {trades}"
                )

        await asyncio.sleep(1)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nMarket maker stopped by user")
    except Exception as e:
        print(f"Fatal error: {e}")
        exit(1)
