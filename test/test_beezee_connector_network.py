"""The API starts no network tasks for a beezee account connector.

`start_network()` and the polling loops of a connector open a NewBlock websocket and poll the node, per
account. That load belongs to the bot container; the API only reads a beezee account's balances over REST.
Other connectors keep their tasks.

Run with: pytest test/test_beezee_connector_network.py -v
"""
import asyncio
from decimal import Decimal

import pytest

import services.unified_connector_service as connector_service_module
from services.unified_connector_service import UnifiedConnectorService


class _FakeConnector:
    """A connector that records what the service starts on it."""

    def __init__(self, **kwargs):
        self.in_flight_orders = {}
        self.started = []
        self.balance_reads = 0

    def _set_current_timestamp(self, timestamp):
        pass

    async def _initialize_trading_pair_symbol_map(self):
        pass

    async def _update_trading_rules(self):
        pass

    async def _update_balances(self):
        self.balance_reads += 1

    async def _trading_rules_polling_loop(self):
        self.started.append("trading_rules_polling")

    def _create_user_stream_tracker_task(self):
        self.started.append("user_stream")
        return None

    async def _user_stream_event_listener(self):
        self.started.append("user_stream_listener")

    async def _lost_orders_update_polling_loop(self):
        self.started.append("lost_orders_polling")

    async def start_network(self):
        self.started.append("start_network")

    def get_all_balances(self):
        return {"BZE": Decimal("1")}


@pytest.fixture
def service(monkeypatch):
    monkeypatch.setattr(connector_service_module, "get_connector_class", lambda name: _FakeConnector)
    monkeypatch.setattr(connector_service_module.BackendAPISecurity, "login_account", lambda **kwargs: True)
    monkeypatch.setattr(connector_service_module.BackendAPISecurity, "api_keys", lambda name: {})
    return UnifiedConnectorService(secrets_manager=None)


async def test_beezee_account_connector_reads_balances_but_starts_nothing(service):
    connector = await service.get_trading_connector("bot-1", "beezee")
    await asyncio.sleep(0)

    assert connector.started == []
    assert connector.balance_reads == 1

    await service.refresh_connector_state(connector, "beezee", "bot-1")
    assert connector.balance_reads == 2


async def test_other_account_connectors_still_start_their_tasks(service):
    connector = await service.get_trading_connector("bot-1", "binance")
    await asyncio.sleep(0)

    assert "trading_rules_polling" in connector.started
    assert "user_stream_listener" in connector.started
