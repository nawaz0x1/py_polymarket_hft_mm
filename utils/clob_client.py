import os
import logging
from dotenv import load_dotenv
from py_clob_client.client import ClobClient
from config import POLYMARKET_HOST, CHAIN_ID

load_dotenv()

PRIVATE_KEY = os.getenv("PRIVATE_KEY")
POLYMARKET_PROXY_ADDRESS = os.getenv("POLYMARKET_PROXY_ADDRESS")
SIGNATURE_TYPE = os.getenv("SIGNATURE_TYPE")

logger = logging.getLogger(__name__)


_client = None
_client_creds = None


def init_clob_client() -> ClobClient:
    try:
        client = ClobClient(
            POLYMARKET_HOST,
            key=PRIVATE_KEY,
            chain_id=CHAIN_ID,
            signature_type=int(SIGNATURE_TYPE),
            funder=POLYMARKET_PROXY_ADDRESS,
        )
        creds = client.create_or_derive_api_creds()
        client.set_api_creds(creds)
        logger.info("ClobClient initialized successfully")
        return client, creds
    except Exception as e:
        logger.error(f"Failed to initialize ClobClient: {e}")
        return None, None


def init_global_client():
    global _client, _client_creds
    _client, _client_creds = init_clob_client()


def is_client_ready():
    return _client is not None


def get_client():
    if _client is None:
        init_clob_client()
    return _client


def get_client_creds():
    if _client_creds is None:
        init_clob_client()
    return _client_creds
