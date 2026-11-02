"""Turn recorded token counts into dollars.

Prices are $ per million tokens, from Anthropic's model table as of 2026-10-06.
Cache writes are the 5-minute rate. Haiku's cache rates aren't listed there, so
they use the usual 0.1x and 1.25x of its input price.
"""

from agent.llm import Usage

PRICES = {
    "claude-opus-5-5": {"input": 4.00, "output": 20.00, "read": 0.20, "write": 5.00},
    "claude-sonnet-5-5": {"input": 2.00, "output": 10.00, "read": 0.20, "write": 2.50},
    "claude-haiku-5-5": {"input": 0.10, "output": 0.50, "read": 0.01, "write": 0.125},
}


def cost(usage: Usage, model: str) -> float:
    price = PRICES[model]
    return (
        usage.input_tokens * price["input"]
        + usage.output_tokens * price["output"]
        + usage.cache_read_tokens * price["read"]
        + usage.cache_write_tokens * price["write"]
    ) / 1_000_000
