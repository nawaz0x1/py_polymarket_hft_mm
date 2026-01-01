import json
import logging
from multiprocessing.util import get_logger
from typing import Optional, Tuple
import aiohttp
from .slug import get_market_slug
from config import GAMMA_API_URL, REQUEST_TIMEOUT


logger = logging.getLogger(__name__)


async def fetch_tokens(
    coin: str = "btc",
) -> Tuple[Optional[str], Optional[str], Optional[str]]:

    if not coin or not isinstance(coin, str):
        raise ValueError("Coin must be a non-empty string")

    try:
        slug = get_market_slug(coin)
        url = f"{GAMMA_API_URL}/events/slug/{slug}"

        async with aiohttp.ClientSession() as session:
            async with session.get(
                url, timeout=aiohttp.ClientTimeout(total=REQUEST_TIMEOUT)
            ) as response:
                if response.status == 200:
                    data = await response.json()
                    return _extract_tokens(data, slug)
                else:
                    logger.warning(f"API request failed with status {response.status}")

    except aiohttp.ClientError as e:
        logger.error(f"Network error fetching tokens: {e}")
    except json.JSONDecodeError as e:
        logger.error(f"Invalid JSON response: {e}")
    except ValueError as e:
        logger.error(f"Invalid input: {e}")
        raise
    except Exception as e:
        logger.error(f"Unexpected error fetching tokens: {e}")

    return None, None, None


def _extract_tokens(
    data: dict, slug: str
) -> Tuple[Optional[str], Optional[str], Optional[str]]:

    try:
        if not isinstance(data, dict) or "markets" not in data:
            logger.error("Invalid response structure: missing 'markets' field")
            return None, None, None

        markets = data["markets"]
        if not isinstance(markets, list) or len(markets) == 0:
            logger.error("Invalid response structure: 'markets' is empty or not a list")
            return None, None, None

        market = markets[0]
        if not isinstance(market, dict) or "clobTokenIds" not in market:
            logger.error("Invalid market structure: missing 'clobTokenIds'")
            return None, None, None

        clob_token_ids = market["clobTokenIds"]
        if not isinstance(clob_token_ids, str):
            logger.error("Invalid token IDs format: not a string")
            return None, None, None

        try:
            token_list = json.loads(clob_token_ids)
            if not isinstance(token_list, list) or len(token_list) < 2:
                logger.error("Invalid token list format or insufficient tokens")
                return None, None, None

            up_token = token_list[0]
            down_token = token_list[1]

            if not (
                isinstance(up_token, str)
                and isinstance(down_token, str)
                and up_token.isdigit()
                and down_token.isdigit()
            ):
                logger.error("Invalid token ID format")
                return None, None, None

            logger.info(
                f"Successfully extracted tokens for market {slug}: \n\tUP : {up_token} \n\tDOWN : {down_token}"
            )
            return up_token, down_token, slug

        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse token IDs JSON: {e}")
            return None, None, None

    except Exception as e:
        logger.error(f"Unexpected error extracting tokens: {e}")
        return None, None, None
