import os
import asyncio
import logging
from dotenv import load_dotenv
from py_clob_client.client import ClobClient
from py_clob_client.clob_types import OrderArgs
from py_clob_client.order_builder.constants import BUY
from config import POLYMARKET_HOST, CHAIN_ID, PROFIT_MARGIN

load_dotenv()

PRIVATE_KEY = os.getenv("PRIVATE_KEY")
POLYMARKET_PROXY_ADDRESS = os.getenv("POLYMARKET_PROXY_ADDRESS")
SIGNATURE_TYPE = os.getenv("SIGNATURE_TYPE")

logger = logging.getLogger(__name__)


async def init_clob_client() -> ClobClient:
    try:
        client = ClobClient(
            POLYMARKET_HOST,
            key=PRIVATE_KEY,
            chain_id=CHAIN_ID,
            signature_type=SIGNATURE_TYPE,
            funder=POLYMARKET_PROXY_ADDRESS,
        )
        client.set_api_creds(client.create_or_derive_api_creds())
        logger.info("ClobClient initialized successfully")
        return client
    except Exception as e:
        logger.error(f"Failed to initialize ClobClient: {e}")
        return None


async def cache_tocken_trading_infos(
    client: ClobClient, up_token_id: str, down_token_id: str
) -> None:
    while True:
        client.get_tick_size(up_token_id)
        client.get_tick_size(down_token_id)
        client.get_neg_risk(up_token_id)
        client.get_neg_risk(down_token_id)
        client.get_fee_rate_bps(up_token_id)
        client.get_fee_rate_bps(down_token_id)
        await asyncio.sleep(10)


async def place_anchor_and_hedge(
    client, up_token_id, down_token_id, anchor_side, price, size=5
):
    if anchor_side == "UP":
        anchor_token_id = up_token_id
        hedge_token_id = down_token_id
    else:
        anchor_token_id = down_token_id
        hedge_token_id = up_token_id

    asyncio.create_task(place_limit_order(client, anchor_token_id, price, size))
    asyncio.create_task(
        place_limit_order(client, hedge_token_id, 1 - price - PROFIT_MARGIN, size)
    )

    logger.info(f"Order prices: {price} and {1 - price - PROFIT_MARGIN}")


async def place_limit_order(client: ClobClient, token_id: str, price: float, size: int):
    start_time = asyncio.get_event_loop().time()
    try:
        response = client.create_and_post_order(
            OrderArgs(
                token_id=token_id,
                price=price,
                size=size,
                side=BUY,
            )
        )
    except Exception as e:
        logger.error(f"Error placing order for token {token_id}: {e}")
        return
    end_time = asyncio.get_event_loop().time()
    logger.info(
        f"Order placed! ID: {response['orderID']} in {end_time - start_time:.2f} sec"
    )
