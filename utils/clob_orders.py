import asyncio
import logging
from py_clob_client.client import ClobClient
from py_clob_client.clob_types import OrderArgs
from py_clob_client.order_builder.constants import BUY
from config import PROFIT_MARGIN, PLACE_OPPOSITE_ORDER
from utils.clob_client import get_client


logger = logging.getLogger(__name__)


async def cache_tocken_trading_infos(
    order_book,
) -> None:
    client = get_client()

    up_token_id, down_token_id = order_book.up_token_id, order_book.down_token_id
    client.get_tick_size(up_token_id)
    client.get_tick_size(down_token_id)
    client.get_neg_risk(up_token_id)
    client.get_neg_risk(down_token_id)
    client.get_fee_rate_bps(up_token_id)
    client.get_fee_rate_bps(down_token_id)


async def place_anchor_and_hedge(
    up_token_id, down_token_id, anchor_side, price, size=5
):
    if anchor_side == "UP":
        anchor_token_id = up_token_id
        hedge_token_id = down_token_id
    else:
        anchor_token_id = down_token_id
        hedge_token_id = up_token_id

    asyncio.create_task(place_limit_order(anchor_token_id, price, size))
    if PLACE_OPPOSITE_ORDER:
        asyncio.create_task(
            place_limit_order(hedge_token_id, 1 - price - PROFIT_MARGIN, size)
        )

        logger.info(f"Order prices: {price} and {1 - price - PROFIT_MARGIN}")
    else:
        logger.info(f"Order price: {price}")


async def place_limit_order(token_id: str, price: float, size: int):
    client = get_client()
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
    return response["orderID"]
