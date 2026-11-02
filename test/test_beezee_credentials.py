"""Credentials for every beezee account mode, posted as JSON, are stored encrypted.

`POST /accounts/add-credential/{profile}/beezee` sets each top-level key of the body on the connector's
config map. The secure fields of beezee (`private_key`, `mnemonic`, `passphrase`) are not top-level keys:
they sit inside the `account_type` model. They must come out encrypted in the profile's `beezee.yml`,
decrypt back (the bot container does that with CONFIG_PASSWORD), and be the configuration the connector is
built from, also after the API restarts and loads the profile again.

The tests drive the real credential write (`UnifiedConnectorService.update_connector_keys`) with a real
secrets manager in a scratch directory. Only the connector start is replaced.

Run with: pytest test/test_beezee_credentials.py -v
"""
from pathlib import Path
from unittest.mock import AsyncMock

import pytest
from hummingbot.client.config.config_crypt import PASSWORD_VERIFICATION_WORD, ETHKeyFileSecretManger
from hummingbot.client.settings import AllConnectorSettings
from hummingbot.connector.exchange.beezee.beezee_signer import BeezeeSigner

from services.unified_connector_service import UnifiedConnectorService
from utils.file_system import fs_util
from utils.security import BackendAPISecurity

PROFILE = "bot-1"
PASSWORD = "unit-test-password"
BOT_KEY = "11" * 32
BOT_MNEMONIC = " ".join(["abandon"] * 11 + ["about"])
GRANTER = BeezeeSigner("22" * 32, "bze").address
TESTNET = {
    "rest_endpoint": "https://rest.testnet.example",
    "rpc_endpoint": "https://rpc.testnet.example",
    "chain_id": "bzetestnet-3",
    "gas_price": "0.01",
    "gas_adjustment": "1.3",
}
HD_PATH = "m/44'/118'/0'/0/0"

WALLET = {"name": "wallet", "private_key": BOT_KEY}
WALLET_MNEMONIC = {"name": "wallet_mnemonic", "mnemonic": BOT_MNEMONIC, "passphrase": "", "hd_path": HD_PATH}
DELEGATED = {"name": "delegated", "private_key": BOT_KEY, "granter_address": GRANTER}
DELEGATED_MNEMONIC = {
    "name": "delegated_mnemonic",
    "mnemonic": BOT_MNEMONIC,
    "passphrase": "",
    "hd_path": HD_PATH,
    "granter_address": GRANTER,
}
# The secret each mode carries, as it must never appear in the file.
SECRET_OF = {
    "wallet": BOT_KEY,
    "wallet_mnemonic": "abandon abandon",
    "delegated": BOT_KEY,
    "delegated_mnemonic": "abandon abandon",
}


@pytest.fixture
def service(tmp_path, monkeypatch):
    monkeypatch.setattr(fs_util, "base_path", str(tmp_path))
    secrets_manager = ETHKeyFileSecretManger(PASSWORD)
    verification = tmp_path / "credentials" / "master_account" / ".password_verification"
    verification.parent.mkdir(parents=True)
    verification.write_text(secrets_manager.encrypt_secret_value(PASSWORD_VERIFICATION_WORD, PASSWORD_VERIFICATION_WORD))
    (tmp_path / "credentials" / PROFILE / "connectors").mkdir(parents=True)

    AllConnectorSettings.reset_connector_config_keys("beezee")
    connector_service = UnifiedConnectorService(secrets_manager)
    # No connector is started: the write and the decrypt are what is under test.
    monkeypatch.setattr(connector_service, "stop_trading_connector", AsyncMock())
    monkeypatch.setattr(connector_service, "get_trading_connector", AsyncMock())
    yield connector_service
    AllConnectorSettings.reset_connector_config_keys("beezee")
    BackendAPISecurity._secure_configs.clear()


def _file(tmp_path: Path) -> Path:
    return tmp_path / "credentials" / PROFILE / "connectors" / "beezee.yml"


def _modes():
    return [
        pytest.param(WALLET, id="wallet"),
        pytest.param(WALLET_MNEMONIC, id="wallet_mnemonic"),
        pytest.param(DELEGATED, id="delegated"),
        pytest.param(DELEGATED_MNEMONIC, id="delegated_mnemonic"),
    ]


def _secret_field(account_type):
    return "private_key" if "private_key" in account_type else "mnemonic"


@pytest.mark.parametrize("account_type", _modes())
async def test_secure_fields_are_stored_encrypted(service, tmp_path, account_type):
    await service.update_connector_keys(PROFILE, "beezee", {"network": TESTNET, "account_type": account_type})

    text = _file(tmp_path).read_text()
    assert SECRET_OF[account_type["name"]] not in text
    assert f"name: {account_type['name']}" in text
    assert "chain_id: bzetestnet-3" in text
    assert "passphrase: ''" not in text and 'passphrase: ""' not in text
    if "granter_address" in account_type:
        assert GRANTER in text


@pytest.mark.parametrize("account_type", _modes())
async def test_the_stored_profile_decrypts_back_to_the_posted_secrets(service, tmp_path, account_type):
    await service.update_connector_keys(PROFILE, "beezee", {"network": TESTNET, "account_type": account_type})

    loaded = BackendAPISecurity.load_connector_config_map_from_file(_file(tmp_path))

    stored = loaded.account_type
    assert stored.name == account_type["name"]
    field = _secret_field(account_type)
    assert getattr(stored, field).get_secret_value() == account_type[field].strip()
    if "passphrase" in account_type:
        assert stored.passphrase.get_secret_value() == ""
    assert loaded.network.chain_id == "bzetestnet-3"


@pytest.mark.parametrize("account_type", _modes())
async def test_the_connector_is_built_from_the_decrypted_profile_after_a_restart(service, tmp_path, account_type):
    await service.update_connector_keys(PROFILE, "beezee", {"network": TESTNET, "account_type": account_type})
    # A restarted API starts from the connector's default config map.
    AllConnectorSettings.reset_connector_config_keys("beezee")
    assert AllConnectorSettings.get_connector_config_keys("beezee").account_type.name == "read_only"

    BackendAPISecurity.login_account(PROFILE, service.secrets_manager)

    current = AllConnectorSettings.get_connector_config_keys("beezee")
    assert current.account_type.name == account_type["name"]
    field = _secret_field(account_type)
    assert getattr(current.account_type, field).get_secret_value() == account_type[field]
    assert current.network.chain_id == "bzetestnet-3"


@pytest.mark.parametrize("network", [{}, None], ids=["empty network", "network omitted"])
async def test_mainnet_defaults_apply_without_endpoints(service, tmp_path, network):
    body = {"account_type": WALLET}
    if network is not None:
        body["network"] = network

    await service.update_connector_keys(PROFILE, "beezee", body)

    loaded = BackendAPISecurity.load_connector_config_map_from_file(_file(tmp_path))
    assert loaded.network.chain_id == "beezee-1"
    assert loaded.network.rest_endpoint == "https://rest.getbze.com"
    assert loaded.network.rpc_endpoint == "https://rpc.getbze.com"
    assert str(loaded.network.gas_price) == "0.01"


async def test_optional_top_level_keys_are_settable(service, tmp_path):
    await service.update_connector_keys(
        PROFILE,
        "beezee",
        {
            "network": TESTNET,
            "account_type": WALLET,
            "batch_window_ms": 250,
            "max_messages_per_tx": 7,
            "denom_labels": {"factory/bze1abc/example": "EXAMPLE"},
        },
    )

    loaded = BackendAPISecurity.load_connector_config_map_from_file(_file(tmp_path))
    assert loaded.batch_window_ms == 250
    assert loaded.max_messages_per_tx == 7
    assert loaded.denom_labels == {"factory/bze1abc/example": "EXAMPLE"}
