"""A beezee bot deployed through the API starts headless, from our image, with its own profile.

`POST /bot-orchestration/deploy-v2-script` copies the credentials profile into the instance, points the
instance at the broker so status and stop work over MQTT, and runs the container with CONFIG_PASSWORD (the
bot decrypts the profile with it) and HEADLESS_MODE (no prompt). The image defaults to the BZE bot image, not
the upstream one.

Run with: pytest test/test_beezee_headless_deploy.py -v
"""
import os
from types import SimpleNamespace

import pytest
import yaml

import services.docker_service as docker_service_module
from models import V2ControllerDeployment
from models.bot_orchestration import V2ScriptDeployment
from services.docker_service import DockerService

BOT_IMAGE = "ghcr.io/bze-alphateam/hummingbot:bze-latest"


class _Containers:
    def __init__(self):
        self.runs = []

    def run(self, **kwargs):
        self.runs.append(kwargs)


class _Docker(DockerService):
    """The real create_hummingbot_instance, with a recording Docker client."""

    def __init__(self):  # noqa: D107 - deliberately skips DockerService.__init__
        self.SOURCE_PATH = os.getcwd()
        self.containers = _Containers()
        self.client = SimpleNamespace(containers=self.containers)


@pytest.fixture
def workdir(tmp_path, monkeypatch):
    profile = tmp_path / "bots" / "credentials" / "bot-1"
    (profile / "connectors").mkdir(parents=True)
    (profile / "connectors" / "beezee.yml").write_text("connector: beezee\n")
    (profile / "conf_client.yml").write_text(yaml.safe_dump({
        "instance_id": "template",
        "mqtt_bridge": {
            "mqtt_host": "localhost",
            "mqtt_port": 1883,
            "mqtt_username": "",
            "mqtt_password": "",
            "mqtt_commands": True,
            "mqtt_autostart": True,
        },
    }))
    scripts = tmp_path / "bots" / "conf" / "scripts"
    scripts.mkdir(parents=True)
    (scripts / "beezee_pmm.yml").write_text("script_file_name: beezee_pmm\n")
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(
        docker_service_module,
        "settings",
        SimpleNamespace(
            security=SimpleNamespace(config_password="config-pw"),
            broker=SimpleNamespace(username="broker-user", password="broker-pw"),
        ),
    )
    monkeypatch.setattr(docker_service_module, "ensure_gateway_certs", lambda password: None)
    monkeypatch.setattr(docker_service_module, "gateway_certs_dir", lambda host=False: str(tmp_path / "certs"))
    return tmp_path


def _deployment(**overrides):
    return V2ScriptDeployment(**{
        "instance_name": "bot-1-20261102-120000",
        "credentials_profile": "bot-1",
        "script_config": "beezee_pmm.yml",
        "headless": True,
        **overrides,
    })


def test_deploy_requests_default_to_the_bze_bot_image():
    assert _deployment().image == BOT_IMAGE
    controllers = V2ControllerDeployment(
        instance_name="bot-1", credentials_profile="bot-1", controllers_config=["beezee_ctrl.yml"]
    )
    assert controllers.image == BOT_IMAGE


def test_the_container_runs_headless_and_can_decrypt_the_profile(workdir):
    docker = _Docker()

    result = docker.create_hummingbot_instance(_deployment())

    assert result["success"] is True
    (run,) = docker.containers.runs
    assert run["image"] == BOT_IMAGE
    assert run["environment"]["CONFIG_PASSWORD"] == "config-pw"
    assert run["environment"]["HEADLESS_MODE"] == "true"
    assert run["environment"]["SCRIPT_CONFIG"] == "beezee_pmm.yml"


def test_the_instance_gets_the_profile_and_the_broker_settings_for_status_and_stop(workdir):
    docker = _Docker()

    docker.create_hummingbot_instance(_deployment())

    conf = workdir / "bots" / "instances" / "bot-1-20261102-120000" / "conf"
    assert (conf / "connectors" / "beezee.yml").read_text() == "connector: beezee\n"
    client = yaml.safe_load((conf / "conf_client.yml").read_text())
    assert client["instance_id"] == "bot-1-20261102-120000"
    assert client["mqtt_bridge"]["mqtt_username"] == "broker-user"
    assert client["mqtt_bridge"]["mqtt_password"] == "broker-pw"
    assert client["mqtt_bridge"]["mqtt_commands"] is True
    assert client["mqtt_bridge"]["mqtt_autostart"] is True
