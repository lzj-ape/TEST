# Uniswap V3 Transaction Decoder

本脚本通过标准 Ethereum JSON-RPC 读取链上原始数据，解析 Uniswap V3 Pool 的 `Swap` 事件，输出结构化 JSON。

## 功能

输入交易哈希，输出：

- `sender`：发起交易的地址（`tx.from`）
- `recipient`：Swap 事件中的接收地址
- `tokenIn` / `tokenOut`：输入 / 输出代币合约地址
- `amountIn` / `amountOut`：按代币 decimals 换算后的可读数量

## 安装

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## 运行

```bash
python uniswap_v3_tx_decoder.py <tx_hash>
```

默认会将每次运行的结果追加保存到 `my_swaps.jsonl`（每行一个 JSON）。也可以指定输出文件：

```bash
export OUTPUT_FILE="my_swaps.jsonl"
python uniswap_v3_tx_decoder.py <tx_hash>
```

## 测试用例（Ethereum Mainnet）

以下交易哈希均为主网 Uniswap V3 Swap：

1. `0xf0627951120f194afbd2ad340e19f1cb9f7e44ad44d3b30dc8e87126f033132c`
2. `0xc466db1f3091f65ece1ac35bc34181a78980229e3800dda2a8d7725414d43f11`
3. `0xa58c897f9f93c3bd462ca08c280fad84c14d796d5d345f59594967b1c9e76c5e`
4. `0x7fdee03ffb227454946852b815b6b86d38e77e6190985c1816b41a8a7b790ea0`

示例运行：

```bash
python uniswap_v3_tx_decoder.py 0xf0627951120f194afbd2ad340e19f1cb9f7e44ad44d3b30dc8e87126f033132c
python uniswap_v3_tx_decoder.py 0xc466db1f3091f65ece1ac35bc34181a78980229e3800dda2a8d7725414d43f11
python uniswap_v3_tx_decoder.py 0xa58c897f9f93c3bd462ca08c280fad84c14d796d5d345f59594967b1c9e76c5e
python uniswap_v3_tx_decoder.py 0x7fdee03ffb227454946852b815b6b86d38e77e6190985c1816b41a8a7b790ea0

```

对应输出（实际运行结果）：

```json
{
  "sender": "0x2528b985765da6aebde7c6d823915c1cc336b057",
  "recipient": "0x5050e08626c499411b5d0e0b5af0e83d3fd82edf",
  "tokenIn": "0xc02aaa39b223fe8d0a0e5c4f27ead9083c756cc2",
  "tokenOut": "0xa0b86991c6218b36c1d19d4a2e9eb0ce3606eb48",
  "amountIn": "1.357645416556783549",
  "amountOut": "4475.810037"
}
```

```json
{
  "sender": "0xd2306a7187fe8b0c0dee59b50fdc438d2075d24c",
  "recipient": "0xd2306a7187fe8b0c0dee59b50fdc438d2075d24c",
  "tokenIn": "0xa0b86991c6218b36c1d19d4a2e9eb0ce3606eb48",
  "tokenOut": "0xc02aaa39b223fe8d0a0e5c4f27ead9083c756cc2",
  "amountIn": "0.185175",
  "amountOut": "0.000056114514652537"
}
```

```json
{
  "sender": "0x3af24b14590917bf0d07b03bf1114cec3b69ae94",
  "recipient": "0xaf682de1f2e6f710731121a05a44cb3c1b511f7d",
  "tokenIn": "0xa0b86991c6218b36c1d19d4a2e9eb0ce3606eb48",
  "tokenOut": "0xc02aaa39b223fe8d0a0e5c4f27ead9083c756cc2",
  "amountIn": "0.185175",
  "amountOut": "0.000056114514652537"
}
```
```json
{
  "sender": "0x3b6ef09907a14361201876574b20afd3bbbe83ab",
  "recipient": "0x3b6ef09907a14361201876574b20afd3bbbe83ab",
  "tokenIn": "0xdac17f958d2ee523a2206206994597c13d831ec7",
  "tokenOut": "0xf5b5efc906513b4344ebabcf47a04901f99f09f3",
  "amountIn": "2.32",
  "amountOut": "1892132"
}
```
## 说明

- 仅使用 `eth_getTransactionByHash` / `eth_getTransactionReceipt` / `eth_call` 等基础 RPC。
- 不使用任何第三方“已解码 swap”接口。
- 多跳交易时：`tokenIn/amountIn` 取第一笔 Swap，`tokenOut/amountOut` 取最后一笔 Swap。
