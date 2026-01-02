import asyncio
import json
import logging
import os
import sys
import time
import websockets
from py_clob_client.clob_types import OrderArgs, OrderType
from py_clob_client.order_builder.constants import BUY, SELL
from utils.slug import get_market_slug
from utils.clob_client import get_client
from config import (
    MARKET_SESSION_SECONDS,
    POLYMARKET_WS_USER_URL as WS_USER_URL,
    PROFIT_MARGIN,
)
from utils.tokens import fetch_tokens
import gc

gc.disable()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s.%(msecs)03d [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger("HedgeBot")


class HedgerState:
    def __init__(self):
        self.tokens = {}
        self.token_map = {}
        self.current_slug = None
        self.hedged_anchors = set()
        self.hedged_orders = set()
        self.processing_anchors = set()
        self.lock = asyncio.Lock()


state = HedgerState()
client = get_client()
creds = client.create_or_derive_api_creds()


async def refresh_market_data():
    while True:
        try:
            slug = get_market_slug("btc")
            if slug != state.current_slug:
                logger.info(f"🔄 Fetching tokens for period: {slug}")
                up_token, down_token, _ = await fetch_tokens(coin="btc")

                async with state.lock:
                    state.tokens = {up_token: "Up", down_token: "Down"}
                    state.token_map = {"Up": up_token, "Down": down_token}
                    state.current_slug = slug
                    state.hedged_anchors.clear()
                    state.processing_anchors.clear()
                    state.hedged_orders.clear()

                logger.info(
                    f"✅ Market Updated: Up={up_token[:10]}... Down={down_token[:10]}..."
                )

            now_ts = time.time()
            next_boundary = (
                (int(now_ts) // MARKET_SESSION_SECONDS) + 1
            ) * MARKET_SESSION_SECONDS
            sleep_time = next_boundary - now_ts + 2
            await asyncio.sleep(sleep_time)

        except Exception as e:
            logger.error(f"Refresh Task Error: {e}")
            await asyncio.sleep(10)


async def send_hedge(anchor_id, anchor_side, anchor_price, anchor_size):

    hedge_side = "Down" if anchor_side == "Up" else "Up"
    hedge_token = state.token_map.get(hedge_side)
    hedge_price = min(max(round(1 - anchor_price - PROFIT_MARGIN, 2), 0.01), 0.99)

    logger.info(f"⚡ SENDING HEDGE {hedge_side} @ ${hedge_price:.2f} ")
    try:
        args = OrderArgs(
            price=hedge_price,
            size=5,
            side=BUY,
            token_id=hedge_token,
        )
        signed = client.create_order(args)
        res = client.post_order(signed, OrderType.GTC)
        hedge_order_id = res.get("orderID")

        async with state.lock:
            state.processing_anchors.discard(anchor_id)
            state.hedged_anchors.add(anchor_id)
            if hedge_order_id:
                state.hedged_orders.add(hedge_order_id)

        logger.info(f"✅ Hedge placed: {hedge_order_id}")
        return hedge_order_id
    except Exception as e:
        logger.error(f"Hedge Order Error: {e}")
        async with state.lock:
            state.processing_anchors.discard(anchor_id)
            state.hedged_anchors.add(anchor_id)
        await asyncio.sleep(0.05)


async def handle_message(message):
    try:
        data = json.loads(message)
        anchor_id = data.get("id")
        side = data.get("side")
        price = float(data.get("price", 0))
        size = float(data.get("size_matched", 0))
        outcome = data.get("outcome")
        status = data.get("status")

        if (
            not anchor_id
            or side != "BUY"
            or not outcome
            or (status != "MATCHED")
            or (price > 50)
        ):
            return

        async with state.lock:
            if (
                anchor_id in state.hedged_anchors
                or anchor_id in state.processing_anchors
                or anchor_id in state.hedged_orders
            ):
                return

        logger.info(f"🔔 MATCHED [{anchor_id[:8]}]: {size} {outcome} @ ${price:.2f}")
        async with state.lock:  # Fix: use async with here too
            state.processing_anchors.add(anchor_id)
        hedge_order_id = await asyncio.create_task(
            send_hedge(anchor_id, outcome, price, size)
        )

    except json.JSONDecodeError:
        logger.debug("Received non-JSON message (likely heartbeat)")
    except Exception as e:
        logger.error(f"Message Error: {e}", exc_info=True)


async def hedger_main():
    asyncio.create_task(refresh_market_data())
    await asyncio.sleep(2)

    logger.info("🔌 Connecting to WebSocket...")

    while True:
        try:
            async with websockets.connect(
                WS_USER_URL, ping_interval=10, ping_timeout=10, close_timeout=5
            ) as ws:
                auth_payload = {
                    "type": "user",
                    "auth": {
                        "apiKey": creds.api_key,
                        "secret": creds.api_secret,
                        "passphrase": creds.api_passphrase,
                    },
                }

                await ws.send(json.dumps(auth_payload))
                logger.info("🌐 WS Authenticated. Waiting for fills...")
                async for message in ws:
                    await handle_message(message)

        except (websockets.ConnectionClosed, OSError, ConnectionRefusedError) as e:
            logger.warning(f"🔌 Disconnected: {e}. Reconnecting...")
            continue

        except Exception as e:
            logger.error(f"Unexpected Error: {e}", exc_info=True)
            continue


if __name__ == "__main__":
    try:
        if os.name != "nt":
            import uvloop

            uvloop.run(hedger_main())
        else:
            asyncio.run(hedger_main())
    except KeyboardInterrupt:
        logger.info("Hedger Stopped")
    except Exception as e:
        logger.critical(f"Fatal Error: {e}", exc_info=True)
        exit(1)
