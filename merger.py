import os
import time
import requests
import asyncio
from web3 import Web3
from eth_account import Account
from dotenv import load_dotenv
from web3.middleware import ExtraDataToPOAMiddleware
from abi.ctfAbi import ctf_abi
from abi.safeAbi import safe_abi

# Constants
CONDITIONAL_TOKENS_FRAMEWORK_ADDRESS = "0x4D97DCd97eC945f40cF65F87097ACe5EA0476045"
NEG_RISK_ADAPTER_ADDRESS = "0xd91E80cF2E7be2e162c6513ceD06f1dD0dA35296"
USDC_ADDRESS = "0x2791bca1f2de4661ed88a30c99a7a9449aa84174"
USDCE_DIGITS = 6
load_dotenv()


def merge_tokens(condition_id, amount=None, neg_risk=False):
    """
    Merge conditional tokens back to USDC.

    Args:
        condition_id: The condition ID (bytes32 hex string)
        amount: Amount to merge in USDC (e.g., "1.5"). If None, merges all available tokens
        neg_risk: Whether to use NEG_RISK_ADAPTER (default: False)

    Returns:
        bool: True if merge successful, False otherwise
    """
    try:
        # Connect to provider
        rpc_url = os.getenv("RPC_URL")
        w3 = Web3(Web3.HTTPProvider(rpc_url))

        # Inject POA middleware for Polygon
        from web3.middleware import ExtraDataToPOAMiddleware

        w3.middleware_onion.inject(ExtraDataToPOAMiddleware, layer=0)

        # Load wallet and safe
        private_key = os.getenv("PRIVATE_KEY")
        account = Account.from_key(private_key)
        safe_address = Web3.to_checksum_address(os.getenv("POLYMARKET_PROXY_ADDRESS"))

        safe = w3.eth.contract(address=safe_address, abi=safe_abi)

        # Determine merge amount
        if amount is None:
            # Get minimum balance of both positions
            ctf_contract = w3.eth.contract(
                address=Web3.to_checksum_address(CONDITIONAL_TOKENS_FRAMEWORK_ADDRESS),
                abi=ctf_abi,
            )

            parent_collection_id = bytes(32)
            collection_id_0 = ctf_contract.functions.getCollectionId(
                parent_collection_id, bytes.fromhex(condition_id[2:]), 1
            ).call()
            collection_id_1 = ctf_contract.functions.getCollectionId(
                parent_collection_id, bytes.fromhex(condition_id[2:]), 2
            ).call()

            position_id_0 = ctf_contract.functions.getPositionId(
                Web3.to_checksum_address(USDC_ADDRESS), collection_id_0
            ).call()
            position_id_1 = ctf_contract.functions.getPositionId(
                Web3.to_checksum_address(USDC_ADDRESS), collection_id_1
            ).call()

            balance_0 = ctf_contract.functions.balanceOf(
                safe_address, position_id_0
            ).call()
            balance_1 = ctf_contract.functions.balanceOf(
                safe_address, position_id_1
            ).call()

            amount_wei = min(balance_0, balance_1)

            if amount_wei == 0:
                print("Merge failed: No tokens to merge")
                return False
        else:
            amount_wei = int(float(amount) * (10**USDCE_DIGITS))

        # Encode merge transaction
        ctf_contract = w3.eth.contract(abi=ctf_abi)
        parent_collection_id = (
            "0x0000000000000000000000000000000000000000000000000000000000000000"
        )
        partition = [1, 2]

        data = ctf_contract.functions.mergePositions(
            Web3.to_checksum_address(USDC_ADDRESS),
            bytes.fromhex(parent_collection_id[2:]),
            bytes.fromhex(condition_id[2:]),
            partition,
            amount_wei,
        )._encode_transaction_data()

        # Sign and execute Safe transaction
        nonce = safe.functions.nonce().call()
        to = (
            NEG_RISK_ADAPTER_ADDRESS
            if neg_risk
            else CONDITIONAL_TOKENS_FRAMEWORK_ADDRESS
        )

        tx_hash = safe.functions.getTransactionHash(
            Web3.to_checksum_address(to),
            0,
            bytes.fromhex(data[2:]),
            0,  # operation: Call
            0,
            0,
            0,  # safeTxGas, baseGas, gasPrice
            "0x0000000000000000000000000000000000000000",  # gasToken
            "0x0000000000000000000000000000000000000000",  # refundReceiver
            nonce,
        ).call()

        # Sign the hash
        hash_bytes = Web3.to_bytes(
            hexstr=tx_hash.hex() if hasattr(tx_hash, "hex") else tx_hash
        )
        signature_obj = account.unsafe_sign_hash(hash_bytes)

        r = signature_obj.r.to_bytes(32, byteorder="big")
        s = signature_obj.s.to_bytes(32, byteorder="big")
        v = signature_obj.v.to_bytes(1, byteorder="big")
        signature = r + s + v

        # Build and send transaction
        tx = safe.functions.execTransaction(
            Web3.to_checksum_address(to),
            0,
            bytes.fromhex(data[2:]),
            0,
            0,
            0,
            0,
            "0x0000000000000000000000000000000000000000",
            "0x0000000000000000000000000000000000000000",
            signature,
        ).build_transaction(
            {
                "from": account.address,
                "nonce": w3.eth.get_transaction_count(account.address),
                "gas": 500000,
                "gasPrice": w3.eth.gas_price,
            }
        )

        signed_tx = account.sign_transaction(tx)
        tx_hash = w3.eth.send_raw_transaction(signed_tx.raw_transaction)

        # Wait for receipt
        receipt = w3.eth.wait_for_transaction_receipt(tx_hash)

        # Check if transaction succeeded
        if receipt["status"] == 1:
            print(f"Merge successful! Amount: {amount_wei / 10**USDCE_DIGITS} USDC")
            return True
        else:
            print("Merge failed: Transaction reverted")
            return False

    except Exception as e:
        print(f"Merge failed: {str(e)}")
        return False


private_key = os.getenv("PRIVATE_KEY")
account = Account.from_key(private_key)
safe_address = Web3.to_checksum_address(os.getenv("POLYMARKET_PROXY_ADDRESS"))
w3 = Web3(Web3.HTTPProvider(os.getenv("RPC_URL")))
w3.middleware_onion.inject(ExtraDataToPOAMiddleware, layer=0)
matic_balance = w3.eth.get_balance(account.address)
proxy_balance = w3.eth.get_balance(safe_address)

print(f"--- Wallet Check ---")
print(f"Signer Address (from Private Key): {account.address}")
print(f"Signer POL Balance: {w3.from_wei(matic_balance, 'ether')} POL")
print(f"Proxy Address (Safe): {safe_address}")
print(f"Proxy POL Balance: {w3.from_wei(proxy_balance, 'ether')} POL")
print(f"--------------------")

if matic_balance == 0:
    raise Exception(f"STOP: Your Signer address {account.address} has NO gas!")


async def do_it():

    url = f"https://data-api.polymarket.com/positions?sizeThreshold=1&limit=100&sortBy=TOKENS&sortDirection=DESC&user={os.getenv('POLYMARKET_PROXY_ADDRESS')}&mergeable=true"

    response = requests.get(url).json()
    if not response:
        print("No mergeable positions found.")
        return
    condition_ids = set([token["conditionId"] for token in response])
    condition_ids
    for condition_id in condition_ids:
        print("Merging tokens for condition ID:", condition_id)
        merge_tokens(condition_id)


async def main():
    while True:
        asyncio.create_task(do_it())
        await asyncio.sleep(10)


if __name__ == "__main__":
    asyncio.run(main())
