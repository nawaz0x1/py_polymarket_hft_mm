import asyncio
import json
import logging
import os
import sys
import websockets
from utils.clob_client import get_client
from config import POLYMARKET_WS_USER_URL
from in_memory_db.utils import add_item as in_memory_db_add_item


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s.%(msecs)03d [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
    handlers=[logging.StreamHandler(sys.stdout)],
)

logger = logging.getLogger("OrderListener")
client = get_client()
creds = client.create_or_derive_api_creds()


async def handle_message(message):
    try:
        data = json.loads(message)
        logger.debug(f"Received Message: {data}")
        data_type = data.get("type")
        if data_type == "PLACEMENT":
            return
        orders_ids = []
        orders_ids.append(data.get("id"))

        if data_type == "TRADE":
            for orders in data.get("maker_orders", []):
                orders_ids.append(orders.get("order_id"))

        for order_id in orders_ids:
            in_memory_db_add_item(order_id)
            logger.info(f"Added Order ID: {order_id} into in-memory DB")

    except json.JSONDecodeError:
        logger.error("Failed to decode message as JSON")
        return


async def hedger_main():
    logger.info("🔌 Connecting to WebSocket...")

    while True:
        try:
            async with websockets.connect(
                POLYMARKET_WS_USER_URL,
                ping_interval=10,
                ping_timeout=10,
                close_timeout=5,
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
                logger.info("🌐 WS Authenticated. Listening Orders...")
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
        logger.info("Order Listener Stopped by User")
    except Exception as e:
        logger.critical(f"Fatal Error: {e}", exc_info=True)
        exit(1)
