import os
import gc
import time
from utils.logger import setup_logging
from utils.tokens import fetch_tokens
from utils.orderbook import OrderBook, SIGNALES
from utils.clob_client import init_global_client, is_client_ready
from utils.market_time import is_in_trading_window, get_period_elapsed_seconds
from utils.trade_counter import reset_trades, get_trades_count, increment_trades
from utils.clob_orders import (
    place_anchor_and_hedge,
    cache_token_trading_infos,
)
from utils.cpu_affinity import set_cpu_affinity
from config import (
    MAX_TRADES,
    MAX_TRADING_BPS_THRESHOLD,
    MIN_DELAY_BETWEEN_TRADES_SECONDS,
    MAX_INVENTORY,
    PROFIT_MARGIN,
)


gc.disable()


def main():

    logger = setup_logging()
    set_cpu_affinity()
    logger.info("Polymarket HFT Market Maker started")
    init_global_client()
    time.sleep(2)
    if not is_client_ready():
        logger.error("ClobClient is not ready. Exiting.")
        return
    up_token, down_token, market_slug = fetch_tokens()
    book = OrderBook(up_token, down_token, market_slug)
    book.start()

    time.sleep(5)  # Allow some time for initial order book data

    market_data = book.get_current_market_data()

    up_bid_price = market_data["best_bid_price"]
    up_ask_price = market_data["best_ask_price"]
    down_ask_price = 1 - up_bid_price
    down_bid_price = 1 - up_ask_price

    print(
        f"Initial Prices - UP: {up_bid_price:.2f}/{up_ask_price:.2f} | DOWN: {down_bid_price:.2f}/{down_ask_price:.2f} | Inventory: {book.inventory} / {MAX_INVENTORY}",
        flush=True,
    )

    while True:
        if not is_in_trading_window():

            book.stop()
            logger.info("Trading session ended. Starting new session.")
            gc.collect()
            time.sleep(10)
            reset_trades()
            up_token, down_token, market_slug = fetch_tokens()
            book = OrderBook(up_token, down_token, market_slug)
            cache_token_trading_infos(book)
            book.start()

        market_data = book.get_current_market_data()
        if not market_data:
            continue

        up_bid_price = market_data["best_bid_price"]
        up_ask_price = market_data["best_ask_price"]

        if not ((0.2 < up_ask_price < 0.35) or (0.65 < up_bid_price < 0.8)) or (
            abs(market_data["micro_vs_mid_bps"]) > MAX_TRADING_BPS_THRESHOLD
        ):
            continue

        down_ask_price = 1 - up_bid_price
        down_bid_price = 1 - up_ask_price

        if (
            (get_trades_count() < MAX_TRADES)
            and (get_period_elapsed_seconds() < 500)
            and (book.inventory < MAX_INVENTORY)
        ):
            trading_side = book.last_signal

            if trading_side == SIGNALES.UP:
                order_ids = place_anchor_and_hedge(
                    up_token,
                    down_token,
                    "UP",
                    round(up_bid_price, 2),
                    size=5,
                    signed_orders_cache=book.signed_orders_cache,
                )
                current_trades = increment_trades()
                book.update_signed_orders_cache(
                    [round(up_bid_price, 2), round(1 - up_bid_price - PROFIT_MARGIN, 2)]
                )
                logger.info(
                    f"Placed UP anchor and hedge orders. Total trades: {current_trades}, Order IDs: {order_ids}"
                )
                time.sleep(MIN_DELAY_BETWEEN_TRADES_SECONDS)

            elif trading_side == SIGNALES.DOWN:
                order_ids = place_anchor_and_hedge(
                    up_token,
                    down_token,
                    "DOWN",
                    round(down_bid_price, 2),
                    size=5,
                    signed_orders_cache=book.signed_orders_cache,
                )
                current_trades = increment_trades()
                book.update_signed_orders_cache(
                    [round(down_bid_price, 2), round(1 - down_bid_price - PROFIT_MARGIN, 2)]
                )
                logger.info(
                    f"Placed DOWN anchor and hedge orders. Total trades: {current_trades}, Order IDs: {order_ids}"
                )
                time.sleep(MIN_DELAY_BETWEEN_TRADES_SECONDS)

        time.sleep(0.01)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\nMarket maker stopped by user")
    except Exception as e:
        print(f"Fatal error: {e}")
        exit(1)
