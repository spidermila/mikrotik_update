import pathlib
from unittest.mock import MagicMock
from unittest.mock import patch

from libs.config import Config


def test_config_init():
    with patch('paramiko.Ed25519Key.from_private_key_file') as mock_key:
        mock_key.return_value = MagicMock()
        config = Config(
            backup_dir='/path/to/backup',
            private_key_file='/path/to/private_key',
        )

        assert config.username == ''
        assert config.public_key_file is None
        assert config.public_key_owner is None
        assert config.port is None
        assert config.log_dir is None
        assert config.delete_backup_after_download is False
        assert config.upgrade_type == 'online'
        assert config.online_upgrade_channel == 'stable'
        assert config.reboot_timeout == 240
        assert config.backup_dir == pathlib.Path('/path/to/backup')
        assert config.private_key_file == '/path/to/private_key'
        mock_key.assert_called_once_with('/path/to/private_key')


def test_config_without_private_key():
    config = Config(backup_dir='/path/to/backup')

    assert config.username == ''
    assert config.public_key_file is None
    assert config.public_key_owner is None
    assert config.port is None
    assert config.log_dir is None
    assert config.delete_backup_after_download is False
    assert config.upgrade_type == 'online'
    assert config.online_upgrade_channel == 'stable'
    assert config.reboot_timeout == 240
    assert config.backup_dir == pathlib.Path('/path/to/backup')
    assert config.private_key_file == ''
