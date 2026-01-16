import json
import os
import sys
from dataclasses import dataclass
from decimal import Decimal, getcontext
from typing import Any, Dict, List, Optional, Tuple

from concurrent.futures import ThreadPoolExecutor

import requests
from eth_abi import decode as abi_decode

getcontext().prec = 78

SWAP_EVENT_SIG = (
    "c42079f94a6350d7e6235f29174924f928cc2ac818eb64fed8004e115fbcca67"
)

TOKEN0_SELECTOR = "0x0dfe1681"
TOKEN1_SELECTOR = "0xd21220a7"
DECIMALS_SELECTOR = "0x313ce567"


class RpcError(RuntimeError):
    pass


class JsonRpcClient:
    def __init__(self, rpc_urls: List[str]) -> None:
        self.rpc_urls = [url for url in rpc_urls if url]
        if not self.rpc_urls:
            raise RpcError("RPC_URL is empty")
        self._request_id = 1
        self._pool_tokens_cache: Dict[str, Tuple[str, str]] = {}
        self._decimals_cache: Dict[str, int] = {}

    def call(self, method: str, params: List[Any]) -> Any:
        last_error: Optional[Exception] = None
        for rpc_url in self.rpc_urls:
            try:
                payload = {
                    "jsonrpc": "2.0",
                    "id": self._request_id,
                    "method": method,
                    "params": params,
                }
                self._request_id += 1
                response = requests.post(rpc_url, json=payload, timeout=30)
                response.raise_for_status()
                body = response.json()
                if "error" in body:
                    raise RpcError(body["error"])
                return body["result"]
            except Exception as exc:
                last_error = exc
                continue
        raise RpcError(f"all RPC endpoints failed for {method}: {last_error}")

def normalize_address(addr: str) -> str:
    if not addr:
        return addr
    addr = addr.lower()
    return addr if addr.startswith("0x") else "0x" + addr


def decode_address(topic: str) -> str:
    return normalize_address("0x" + topic[-40:])


def eth_call(client: JsonRpcClient, to_addr: str, data: str) -> str:
    return client.call("eth_call", [{"to": to_addr, "data": data}, "latest"])


def get_token0_token1(client: JsonRpcClient, pool: str) -> Tuple[str, str]:
    cache_key = normalize_address(pool)
    if cache_key in client._pool_tokens_cache:
        return client._pool_tokens_cache[cache_key]
    token0_hex = eth_call(client, cache_key, TOKEN0_SELECTOR)
    token1_hex = eth_call(client, cache_key, TOKEN1_SELECTOR)
    token0 = normalize_address("0x" + token0_hex[-40:])
    token1 = normalize_address("0x" + token1_hex[-40:])
    client._pool_tokens_cache[cache_key] = (token0, token1)
    return token0, token1


def get_decimals(client: JsonRpcClient, token: str) -> int:
    cache_key = normalize_address(token)
    if cache_key in client._decimals_cache:
        return client._decimals_cache[cache_key]
    decimals_hex = eth_call(client, cache_key, DECIMALS_SELECTOR)
    decimals = int(decimals_hex, 16)
    client._decimals_cache[cache_key] = decimals
    return decimals


def format_amount(value: int, decimals: int) -> str:
    if decimals == 0:
        return str(value)
    scale = Decimal(10) ** Decimal(decimals)
    return str(Decimal(value) / scale)


@dataclass
class SwapEvent:
    pool: str
    sender: str
    recipient: str
    amount0: int
    amount1: int


def parse_swap_logs(receipt: Dict[str, Any]) -> List[SwapEvent]:
    swaps: List[SwapEvent] = []
    for log in receipt.get("logs", []):
        topics = log.get("topics", [])
        if not topics or topics[0].lower().replace("0x", "") != SWAP_EVENT_SIG:
            continue
        if len(topics) < 3:
            continue
        sender = decode_address(topics[1])
        recipient = decode_address(topics[2])
        data_bytes = bytes.fromhex(log["data"][2:])
        amount0, amount1, _, _, _ = abi_decode(
            ["int256", "int256", "uint160", "uint128", "int24"], data_bytes
        )
        pool = normalize_address(log["address"])
        swaps.append(
            SwapEvent(
                pool=pool,
                sender=sender,
                recipient=recipient,
                amount0=int(amount0),
                amount1=int(amount1),
            )
        )
    return swaps


def resolve_swap_tokens(
    client: JsonRpcClient, swap: SwapEvent
) -> Tuple[str, str, int, int]:
    token0, token1 = get_token0_token1(client, swap.pool)
    if swap.amount0 > 0 and swap.amount1 < 0:
        return token0, token1, swap.amount0, -swap.amount1
    if swap.amount1 > 0 and swap.amount0 < 0:
        return token1, token0, swap.amount1, -swap.amount0
    raise RpcError(
        f"unexpected swap amounts in pool {swap.pool}: amount0={swap.amount0}, amount1={swap.amount1}"
    )


def decode_uniswap_v3_swap(tx_hash: str, rpc_urls: List[str]) -> Dict[str, str]:
    client = JsonRpcClient(rpc_urls)
    receipt = client.call("eth_getTransactionReceipt", [tx_hash])
    if receipt is None:
        raise RpcError(f"receipt not found: {tx_hash}")
    if receipt.get("status") != "0x1":
        raise RpcError(f"transaction failed: {tx_hash}")
    tx = client.call("eth_getTransactionByHash", [tx_hash])
    if not tx:
        tx = {}

    swaps = parse_swap_logs(receipt)
    if not swaps:
        raise RpcError(f"no Uniswap V3 Swap event found in tx {tx_hash}")

    first_swap = swaps[0]
    last_swap = swaps[-1]

    with ThreadPoolExecutor(max_workers=4) as executor:
        first_future = executor.submit(resolve_swap_tokens, client, first_swap)
        last_future = executor.submit(resolve_swap_tokens, client, last_swap)
        token_in, _, amount_in, _ = first_future.result()
        _, token_out, _, amount_out = last_future.result()

        decimals_in_future = executor.submit(get_decimals, client, token_in)
        decimals_out_future = executor.submit(get_decimals, client, token_out)
        decimals_in = decimals_in_future.result()
        decimals_out = decimals_out_future.result()

    sender_raw = tx.get("from") or receipt.get("from")
    if not sender_raw:
        raise RpcError(
            "sender not found in RPC response; try a different mainnet RPC URL"
        )

    return {
        "sender": normalize_address(sender_raw),
        "recipient": last_swap.recipient,
        "tokenIn": token_in,
        "tokenOut": token_out,
        "amountIn": format_amount(amount_in, decimals_in),
        "amountOut": format_amount(amount_out, decimals_out),
    }


def main() -> None:
    if len(sys.argv) < 2:
        print("Usage: python uniswap_v3_tx_decoder.py <tx_hash>")
        sys.exit(1)
    tx_hash = sys.argv[1]
    rpc_urls = os.environ.get("RPC_URL", "https://ethereum.publicnode.com")
    rpc_urls_list = [url.strip() for url in rpc_urls.split(",")]
    result = decode_uniswap_v3_swap(tx_hash, rpc_urls_list)
    output_text = json.dumps(result, indent=2)
    print(output_text)

    output_file = os.environ.get("OUTPUT_FILE", "my_swaps.jsonl")
    with open(output_file, "a", encoding="utf-8") as handle:
        handle.write(json.dumps(result, ensure_ascii=True) + "\n")


if __name__ == "__main__":
    main()
