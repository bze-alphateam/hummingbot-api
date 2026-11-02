from typing import Any, Dict

from hummingbot.client.config.config_helpers import ClientConfigAdapter
from pydantic import SecretStr


class HummingbotAPIConfigAdapter(ClientConfigAdapter):
    def _encrypt_secrets(self, conf_dict: Dict[str, Any]):
        from utils.security import BackendAPISecurity
        for attr, value in conf_dict.items():
            attr_type = self._hb_config.model_fields[attr].annotation
            if attr_type == SecretStr:
                clear_text_value = value.get_secret_value() if isinstance(value, SecretStr) else value
                conf_dict[attr] = BackendAPISecurity.secrets_manager.encrypt_secret_value(attr, clear_text_value)

    def _decrypt_secrets(self, conf_dict: Dict[str, Any]):
        from utils.security import BackendAPISecurity
        for attr, value in conf_dict.items():
            attr_type = self._hb_config.__fields__[attr].type_
            if attr_type == SecretStr:
                decrypted_value = BackendAPISecurity.secrets_manager.decrypt_secret_value(attr, value.get_secret_value())
                conf_dict[attr] = SecretStr(decrypted_value)

    def _decrypt_all_internal_secrets(self):
        from utils.security import BackendAPISecurity
        for traversal_item in self.traverse():
            if traversal_item.type_ == SecretStr:
                encrypted_value = traversal_item.value
                if isinstance(encrypted_value, SecretStr):
                    encrypted_value = encrypted_value.get_secret_value()
                decrypted_value = BackendAPISecurity.secrets_manager.decrypt_secret_value(traversal_item.attr, encrypted_value)
                parent_attributes = traversal_item.config_path.split(".")[:-1]
                config = self
                for parent_attribute in parent_attributes:
                    config = getattr(config, parent_attribute)
                setattr(config, traversal_item.attr, decrypted_value)

    def decrypt_all_secure_data(self):
        from utils.security import BackendAPISecurity

        # Walk the nested models too: a connector such as beezee keeps its secure fields
        # (private_key, mnemonic, passphrase) inside the `account_type` model, not at the top level.
        self._decrypt_secure_fields(self, BackendAPISecurity.secrets_manager)

    @classmethod
    def _decrypt_secure_fields(cls, config: ClientConfigAdapter, secrets_manager):
        for traversal_item in list(config.traverse()):
            value = traversal_item.value
            if isinstance(value, ClientConfigAdapter):
                cls._decrypt_secure_fields(value, secrets_manager)
                continue
            if traversal_item.client_field_data is None or not traversal_item.client_field_data.is_secure:
                continue
            if isinstance(value, SecretStr):
                value = value.get_secret_value()
            if value == "" or secrets_manager is None:
                decrypted_value = value
            else:
                decrypted_value = secrets_manager.decrypt_secret_value(attr=traversal_item.attr, value=value)
            setattr(config, traversal_item.attr, decrypted_value)
