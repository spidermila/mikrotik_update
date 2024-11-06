import pathlib
from unittest.mock import mock_open
from unittest.mock import patch

import pytest
import yaml

from libs.configmanager import ConfigManager
# from unittest.mock import MagicMock


def test_config_manager_init():
    cm = ConfigManager(filename='my_test_file')
    assert cm.filename == 'my_test_file'


def test_load_config_success():
    mock_data = {
        'global': {
            'backup_dir': '/path/to/backup',
            'private_key_file': '',
            'username': 'user',
            'public_key_file': 'tests/data/test_key.pub',
            'public_key_owner': 'owner',
            'port': 333,
            'log_dir': '/path/to/log',
            'reboot_timeout': 240,
            'delete_backup_after_download': True,
            'online_upgrade_channel': 'stable',
        },
        'devices': [
            {
                'name': 'device1',
                'address': '192.168.1.1',
                'username': 'device_user',
                'port': 2222,
                'online_upgrade_channel': 'beta',
                'upgrade_type': 'manual',
                'packages': ['package1', 'package2'],
            },
        ],
    }

    with patch('builtins.open', mock_open(read_data=yaml.dump(mock_data))):
        with patch('yaml.safe_load', return_value=mock_data):
            config_manager = ConfigManager('dummy_filename')
            cfg, devices = config_manager.load_config()

            assert cfg.backup_dir == pathlib.Path('/path/to/backup')
            assert cfg.private_key_file == ''
            assert cfg.username == 'user'
            assert cfg.public_key_file == 'tests/data/test_key.pub'
            assert cfg.public_key_owner == 'owner'
            assert cfg.port == 333
            assert cfg.log_dir == '/path/to/log'
            assert cfg.reboot_timeout == 240
            assert cfg.delete_backup_after_download is True
            assert cfg.online_upgrade_channel == 'stable'

            assert len(devices) == 1
            device = devices[0]
            assert device.name == 'device1'
            assert device.address == '192.168.1.1'
            assert device.username == 'device_user'
            assert device.port == 2222
            assert device.online_upgrade_channel == 'beta'
            assert device.upgrade_type == 'manual'
            assert device.packages == ['package1', 'package2']


def test_load_config_yamlerror():
    invalid_yaml_content = 'invalid_yaml: ['
    with patch('builtins.open', mock_open(read_data=invalid_yaml_content)):
        config_manager = ConfigManager('dummy_filename')
        with pytest.raises(yaml.YAMLError):
            config_manager.load_config()


def test_load_config_username_not_in_devices():
    mock_data = {
        'global': {
            'backup_dir': '/path/to/backup',
            'private_key_file': '',
            'username': 'global-user',
            'public_key_file': 'tests/data/test_key.pub',
            'public_key_owner': 'owner',
            'port': 333,
            'log_dir': '/path/to/log',
            'reboot_timeout': 240,
            'delete_backup_after_download': True,
            'online_upgrade_channel': 'stable',
        },
        'devices': [
            {
                'name': 'device1',
                'address': '192.168.1.1',
                'port': 2222,
                'online_upgrade_channel': 'beta',
                'upgrade_type': 'manual',
                'packages': ['package1', 'package2'],
            },
        ],
    }
    with patch('builtins.open', mock_open(read_data=yaml.dump(mock_data))):
        with patch('yaml.safe_load', return_value=mock_data):
            config_manager = ConfigManager('dummy_filename')
            cfg, devices = config_manager.load_config()
            device = devices[0]
            assert device.username == 'global-user'


def test_load_config_no_username(capsys):
    mock_data = {
        'global': {
            'backup_dir': '/path/to/backup',
            'private_key_file': '',
            'public_key_file': 'tests/data/test_key.pub',
            'public_key_owner': 'owner',
            'port': 333,
            'log_dir': '/path/to/log',
            'reboot_timeout': 240,
            'delete_backup_after_download': True,
            'online_upgrade_channel': 'stable',
        },
        'devices': [
            {
                'name': 'device1',
                'address': '192.168.1.1',
                'port': 2222,
                'online_upgrade_channel': 'beta',
                'upgrade_type': 'manual',
                'packages': ['package1', 'package2'],
            },
        ],
    }
    with patch('builtins.open', mock_open(read_data=yaml.dump(mock_data))):
        with patch('yaml.safe_load', return_value=mock_data):
            config_manager = ConfigManager('dummy_filename')
            _, _ = config_manager.load_config()
            captured = capsys.readouterr()
            assert 'Username not specified for' in captured.out


def test_load_config_prt_not_in_devices():
    mock_data = {
        'global': {
            'backup_dir': '/path/to/backup',
            'private_key_file': '',
            'username': 'global-user',
            'public_key_file': 'tests/data/test_key.pub',
            'public_key_owner': 'owner',
            'port': 333,
            'log_dir': '/path/to/log',
            'reboot_timeout': 240,
            'delete_backup_after_download': True,
            'online_upgrade_channel': 'stable',
        },
        'devices': [
            {
                'name': 'device1',
                'address': '192.168.1.1',
                'username': 'device_user',
                'online_upgrade_channel': 'beta',
                'upgrade_type': 'manual',
                'packages': ['package1', 'package2'],
            },
        ],
    }
    with patch('builtins.open', mock_open(read_data=yaml.dump(mock_data))):
        with patch('yaml.safe_load', return_value=mock_data):
            config_manager = ConfigManager('dummy_filename')
            _, devices = config_manager.load_config()
            device = devices[0]
            assert device.port == 333


def test_load_config_no_port():
    mock_data = {
        'global': {
            'backup_dir': '/path/to/backup',
            'private_key_file': '',
            'username': 'global-user',
            'public_key_file': 'tests/data/test_key.pub',
            'public_key_owner': 'owner',
            'log_dir': '/path/to/log',
            'reboot_timeout': 240,
            'delete_backup_after_download': True,
            'online_upgrade_channel': 'stable',
        },
        'devices': [
            {
                'name': 'device1',
                'address': '192.168.1.1',
                'username': 'device_user',
                'online_upgrade_channel': 'beta',
                'upgrade_type': 'manual',
                'packages': ['package1', 'package2'],
            },
        ],
    }
    with patch('builtins.open', mock_open(read_data=yaml.dump(mock_data))):
        with patch('yaml.safe_load', return_value=mock_data):
            config_manager = ConfigManager('dummy_filename')
            _, devices = config_manager.load_config()
            device = devices[0]
            assert device.port == 22


def test_load_config_no_online_update_channel_in_dev():
    mock_data = {
        'global': {
            'backup_dir': '/path/to/backup',
            'private_key_file': '',
            'username': 'user',
            'public_key_file': 'tests/data/test_key.pub',
            'public_key_owner': 'owner',
            'port': 333,
            'log_dir': '/path/to/log',
            'reboot_timeout': 240,
            'delete_backup_after_download': True,
            'online_upgrade_channel': 'stable',
        },
        'devices': [
            {
                'name': 'device1',
                'address': '192.168.1.1',
                'username': 'device_user',
                'port': 2222,
                'upgrade_type': 'manual',
                'packages': ['package1', 'package2'],
            },
        ],
    }
    with patch('builtins.open', mock_open(read_data=yaml.dump(mock_data))):
        with patch('yaml.safe_load', return_value=mock_data):
            config_manager = ConfigManager('dummy_filename')
            _, devices = config_manager.load_config()
            device = devices[0]
            assert device.online_upgrade_channel == 'stable'
