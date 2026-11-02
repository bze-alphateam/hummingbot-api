"""Keeps the API from trading on BeeZee.

A BeeZee account signs transactions with a sequence number. The bot container is the only signer of its
account; a second signer in the API process would race it. The API only reads for BeeZee (balances,
portfolio, trading rules) and refuses every route that would place or cancel an order or start an executor.
"""
from typing import Any

from fastapi import HTTPException
from starlette import status

BEEZEE_CONNECTOR = "beezee"
REFUSAL = "beezee trades only inside its bot container"


def is_beezee_connector(name: Any) -> bool:
    """True for `beezee` and its domain variants (`beezee_testnet`), whatever the case or surrounding spaces."""
    if not isinstance(name, str):
        return False
    normalized = name.strip().lower()
    return normalized == BEEZEE_CONNECTOR or normalized.startswith(f"{BEEZEE_CONNECTOR}_")


def mentions_beezee(config: Any) -> bool:
    """True when any string anywhere inside a (nested) config is a BeeZee connector name.

    Executor configs carry connector names under different keys (`connector_name`, `maker_market`,
    `buying_market`, ...) and can nest them, so every string leaf is checked instead of a list of keys.
    """
    if isinstance(config, dict):
        return any(mentions_beezee(value) for value in config.values())
    if isinstance(config, (list, tuple, set)):
        return any(mentions_beezee(item) for item in config)
    return is_beezee_connector(config)


def refuse_beezee(*connectors: Any) -> None:
    """Raises HTTP 400 when any connector name, or any name nested in a config, is BeeZee."""
    if any(mentions_beezee(connector) for connector in connectors):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=REFUSAL)
