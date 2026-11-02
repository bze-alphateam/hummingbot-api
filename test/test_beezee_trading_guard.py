"""The API never trades for beezee.

A beezee account signs with a sequence number, and its bot container is the only signer. A second signer
in the API process would race it, so the order, cancel and executor routes refuse the connector with
HTTP 400 and leave every other connector untouched.

Run with: pytest test/test_beezee_trading_guard.py -v
"""
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from deps import get_accounts_service, get_executor_service
from routers import executors, trading

REFUSAL = "beezee trades only inside its bot container"


def _client(accounts_service, executor_service):
    app = FastAPI()
    app.include_router(trading.router)
    app.include_router(executors.router)
    app.dependency_overrides[get_accounts_service] = lambda: accounts_service
    app.dependency_overrides[get_executor_service] = lambda: executor_service
    return TestClient(app, raise_server_exceptions=False)


@pytest.fixture
def services():
    accounts = SimpleNamespace(
        place_trade=AsyncMock(return_value="order-1"),
        cancel_order=AsyncMock(return_value="order-1"),
    )
    executor = SimpleNamespace(
        create_executor=AsyncMock(return_value={
            "executor_id": "ex-1",
            "executor_type": "order_executor",
            "connector_name": "binance",
            "trading_pair": "BTC-USDT",
            "status": "running",
            "created_at": "2026-11-02T00:00:00",
        })
    )
    return accounts, executor


def _order(connector):
    return {
        "account_name": "bot-1",
        "connector_name": connector,
        "trading_pair": "BZE-USDC",
        "trade_type": "BUY",
        "amount": "1",
        "order_type": "LIMIT",
        "price": "1",
    }


@pytest.mark.parametrize("connector", ["beezee", "BeeZee", " beezee ", "beezee_testnet"])
def test_placing_an_order_on_beezee_is_refused(services, connector):
    accounts, executor = services

    response = _client(accounts, executor).post("/trading/orders", json=_order(connector))

    assert response.status_code == 400
    assert response.json()["detail"] == REFUSAL
    accounts.place_trade.assert_not_called()


def test_placing_an_order_on_another_connector_is_unchanged(services):
    accounts, executor = services

    response = _client(accounts, executor).post("/trading/orders", json=_order("binance"))

    assert response.status_code == 201
    assert response.json()["order_id"] == "order-1"
    accounts.place_trade.assert_awaited_once()


@pytest.mark.parametrize("connector", ["beezee", "BEEZEE", "beezee_testnet"])
def test_cancelling_an_order_on_beezee_is_refused(services, connector):
    accounts, executor = services

    response = _client(accounts, executor).post(f"/trading/bot-1/{connector}/orders/abc/cancel")

    assert response.status_code == 400
    assert response.json()["detail"] == REFUSAL
    accounts.cancel_order.assert_not_called()


def test_cancelling_an_order_on_another_connector_is_unchanged(services):
    accounts, executor = services

    response = _client(accounts, executor).post("/trading/bot-1/binance/orders/abc/cancel")

    assert response.status_code == 200
    accounts.cancel_order.assert_awaited_once()


def _executor_request(executor_config):
    return {"account_name": "bot-1", "executor_config": executor_config}


@pytest.mark.parametrize(
    "executor_config",
    [
        {"type": "order_executor", "connector_name": "beezee", "trading_pair": "BZE-USDC"},
        {"type": "order_executor", "connector_name": " BeeZee ", "trading_pair": "BZE-USDC"},
        # Nested, and one of several connectors.
        {"type": "xemm_executor", "maker_market": "beezee", "taker_market": "binance"},
        {"type": "xemm_executor", "maker_market": "binance", "taker_market": "beezee"},
        {
            "type": "arbitrage_executor",
            "buying_market": {"connector_name": "binance", "trading_pair": "BZE-USDC"},
            "selling_market": {"connector_name": "beezee", "trading_pair": "BZE-USDC"},
        },
        {"type": "custom", "legs": [{"connector_name": "binance"}, {"connector_name": "beezee_testnet"}]},
    ],
)
def test_creating_an_executor_that_uses_beezee_is_refused(services, executor_config):
    accounts, executor = services

    response = _client(accounts, executor).post("/executors/", json=_executor_request(executor_config))

    assert response.status_code == 400
    assert response.json()["detail"] == REFUSAL
    executor.create_executor.assert_not_called()


def test_creating_an_executor_on_another_connector_is_unchanged(services):
    accounts, executor = services
    config = {"type": "order_executor", "connector_name": "binance", "trading_pair": "BTC-USDT"}

    response = _client(accounts, executor).post("/executors/", json=_executor_request(config))

    assert response.status_code == 201
    executor.create_executor.assert_awaited_once()
