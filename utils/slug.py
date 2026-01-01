import pytz
from datetime import datetime


MARKET_INTERVAL_SECONDS = 900
TIMEZONE = "US/Eastern"


def get_market_slug(coin: str = "btc") -> str:

    if not coin or not isinstance(coin, str):
        raise ValueError("Coin must be a non-empty string")

    et_tz = pytz.timezone(TIMEZONE)
    now = datetime.now(et_tz)
    ts = int(now.timestamp())
    start = (ts // MARKET_INTERVAL_SECONDS) * MARKET_INTERVAL_SECONDS
    return f"{coin.lower()}-updown-15m-{start}"
