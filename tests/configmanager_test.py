from unittest.mock import MagicMock
from unittest.mock import mock_open
from unittest.mock import patch

import pytest
import yaml

from mu.configmanager import ConfigManager
from mu.logger import Logger
# from unittest.mock import MagicMock


@pytest.fixture(scope='session', autouse=True)
def logger():
    yield MagicMock(spec=Logger)


def test_config_manager_init():
    cm = ConfigManager(filename='my_test_file')
    assert cm.filename == 'my_test_file'


def test_load_config_success():
    pass


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
            'online_update_channel': 'stable',
        },
        'devices': [
            {
                'name': 'device1',
                'address': '192.168.1.1',
                'port': 2222,
                'online_update_channel': 'beta',
                'update_type': 'dev-manual',
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
            'online_update_channel': 'stable',
        },
        'devices': [
            {
                'name': 'device1',
                'address': '192.168.1.1',
                'port': 2222,
                'online_update_channel': 'beta',
                'update_type': 'dev-manual',
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
            'online_update_channel': 'stable',
        },
        'devices': [
            {
                'name': 'device1',
                'address': '192.168.1.1',
                'username': 'device_user',
                'online_update_channel': 'beta',
                'update_type': 'dev-manual',
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
            'online_update_channel': 'stable',
        },
        'devices': [
            {
                'name': 'device1',
                'address': '192.168.1.1',
                'username': 'device_user',
                'online_update_channel': 'beta',
                'update_type': 'dev-manual',
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
            'online_update_channel': 'test_stable',
        },
        'devices': [
            {
                'name': 'device1',
                'address': '192.168.1.1',
                'username': 'device_user',
                'port': 2222,
                'update_type': 'dev-manual',
                'packages': ['package1', 'package2'],
            },
        ],
    }
    with patch('builtins.open', mock_open(read_data=yaml.dump(mock_data))):
        with patch('yaml.safe_load', return_value=mock_data):
            config_manager = ConfigManager('dummy_filename')
            _, devices = config_manager.load_config()
            device = devices[0]
            assert device.online_update_channel == 'test_stable'


def test_load_config_no_online_update_channel():
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
        },
        'devices': [
            {
                'name': 'device1',
                'address': '192.168.1.1',
                'username': 'device_user',
                'port': 2222,
                'update_type': 'dev-manual',
                'packages': ['package1', 'package2'],
            },
        ],
    }
    with patch('builtins.open', mock_open(read_data=yaml.dump(mock_data))):
        with patch('yaml.safe_load', return_value=mock_data):
            config_manager = ConfigManager('dummy_filename')
            _, devices = config_manager.load_config()
            device = devices[0]
            assert device.online_update_channel == 'stable'


def test_load_config_no_update_type_in_dev():
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
            'online_update_channel': 'test_stable',
            'update_type': 'test_manual',
        },
        'devices': [
            {
                'name': 'device1',
                'address': '192.168.1.1',
                'username': 'device_user',
                'port': 2222,
                'packages': ['package1', 'package2'],
            },
        ],
    }
    with patch('builtins.open', mock_open(read_data=yaml.dump(mock_data))):
        with patch('yaml.safe_load', return_value=mock_data):
            config_manager = ConfigManager('dummy_filename')
            _, devices = config_manager.load_config()
            device = devices[0]
            assert device.update_type == 'test_manual'


def test_load_config_no_update_type():
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
            'online_update_channel': 'test_stable',
        },
        'devices': [
            {
                'name': 'device1',
                'address': '192.168.1.1',
                'username': 'device_user',
                'port': 2222,
                'packages': ['package1', 'package2'],
            },
        ],
    }
    with patch('builtins.open', mock_open(read_data=yaml.dump(mock_data))):
        with patch('yaml.safe_load', return_value=mock_data):
            config_manager = ConfigManager('dummy_filename')
            _, devices = config_manager.load_config()
            device = devices[0]
            assert device.update_type == 'online'


def test_load_config_update_type_manual_packages():
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
            'online_update_channel': 'test_stable',
        },
        'devices': [
            {
                'name': 'device1',
                'address': '192.168.1.1',
                'username': 'device_user',
                'port': 2222,
                'update_type': 'manual',
                'packages': ['package1', 'package2'],
            },
        ],
    }
    with patch('builtins.open', mock_open(read_data=yaml.dump(mock_data))):
        with patch('yaml.safe_load', return_value=mock_data):
            config_manager = ConfigManager('dummy_filename')
            _, devices = config_manager.load_config()
            device = devices[0]
            assert device.packages == ['package1', 'package2']


def test_check_config_file_yamlerror(capsys):
    invalid_yaml_content = 'invalid_yaml: ['
    with patch('builtins.open', mock_open(read_data=invalid_yaml_content)):
        config_manager = ConfigManager('dummy_filename')
        with pytest.raises(yaml.YAMLError):
            config_manager.check_config_file()


def test_check_config_file_missing_global(capsys):
    mock_data = """
    devices:
      - name: device1
        address: 192.168.1.1
    """
    with patch('builtins.open', mock_open(read_data=mock_data)):
        config_manager = ConfigManager('dummy_filename')
        result = config_manager.check_config_file()
        captured = capsys.readouterr()
        assert not result
        assert 'Config file missing the "global" section' in captured.out


def test_check_config_file_missing_devices(capsys):
    mock_data = """
    global:
      backup_dir: /path/to/backup
      private_key_file: /path/to/private_key
    """
    with patch('builtins.open', mock_open(read_data=mock_data)):
        config_manager = ConfigManager('dummy_filename')
        result = config_manager.check_config_file()
        captured = capsys.readouterr()
        assert not result
        assert 'Config file missing the "devices" section' in captured.out


def test_check_config_file_invalid_global_type(capsys):
    mock_data = """
    global: []
    devices:
      - name: device1
        address: 192.168.1.1
    """
    with patch('builtins.open', mock_open(read_data=mock_data)):
        config_manager = ConfigManager('dummy_filename')
        result = config_manager.check_config_file()
        captured = capsys.readouterr()
        assert not result
        assert 'global section is not a dict!' in captured.out


def test_check_config_file_invalid_devices_type(capsys):
    mock_data = """
    global:
      backup_dir: /path/to/backup
      private_key_file: /path/to/private_key
    devices: {}
    """
    with patch('builtins.open', mock_open(read_data=mock_data)):
        config_manager = ConfigManager('dummy_filename')
        result = config_manager.check_config_file()
        captured = capsys.readouterr()
        assert not result
        assert 'devices section is not a list!' in captured.out


def test_check_config_file_missing_global_options(capsys):
    mock_data = """
    global:
      backup_dir: /path/to/backup
    devices:
      - name: device1
        address: 192.168.1.1
    """
    with patch('builtins.open', mock_open(read_data=mock_data)):
        config_manager = ConfigManager('dummy_filename')
        result = config_manager.check_config_file()
        captured = capsys.readouterr()
        assert not result
        assert 'Missing mandatory options:' in captured.out
        assert 'private_key_file' in captured.out


def test_check_config_file_missing_one_device_option(capsys):
    mock_data = """
    global:
      backup_dir: /path/to/backup
      private_key_file: /path/to/private_key
    devices:
      - name: device1
    """
    with patch('builtins.open', mock_open(read_data=mock_data)):
        config_manager = ConfigManager('dummy_filename')
        result = config_manager.check_config_file()
        captured = capsys.readouterr()
        assert not result
        assert 'Missing mandatory device options:' in captured.out
        assert 'address' in captured.out


def test_check_config_file_missing_two_device_options(capsys):
    mock_data = """
    global:
      backup_dir: /path/to/backup
      private_key_file: /path/to/private_key
    devices:
      - test-option: test-value
    """
    with patch('builtins.open', mock_open(read_data=mock_data)):
        config_manager = ConfigManager('dummy_filename')
        result = config_manager.check_config_file()
        captured = capsys.readouterr()
        assert not result
        assert 'Missing mandatory device options:' in captured.out
        assert 'address' in captured.out
        assert 'name' in captured.out


def test_check_config_file_device_not_dict(capsys):
    mock_data = """
    global:
      backup_dir: /path/to/backup
      private_key_file: /path/to/private_key
    devices:
      - - test
    """
    with patch('builtins.open', mock_open(read_data=mock_data)):
        config_manager = ConfigManager('dummy_filename')
        result = config_manager.check_config_file()
        captured = capsys.readouterr()
        assert not result
        assert 'Device entry is not dict!' in captured.out


def test_check_config_file_no_devices_specified(capsys):
    mock_data = """
    global:
      backup_dir: /path/to/backup
      private_key_file: /path/to/private_key
    devices:
      []
    """
    with patch('builtins.open', mock_open(read_data=mock_data)):
        config_manager = ConfigManager('dummy_filename')
        result = config_manager.check_config_file()
        captured = capsys.readouterr()
        assert not result
        assert 'No devices specified!' in captured.out


def test_check_config_file_correct(capsys):
    mock_data = """
    global:
      backup_dir: /path/to/backup
      private_key_file: /path/to/private_key
    devices:
      - name: test-dev
        address: 192.168.1.1
        other-option: test-value
    """
    with patch('builtins.open', mock_open(read_data=mock_data)):
        config_manager = ConfigManager('dummy_filename')
        result = config_manager.check_config_file()
        # print(f'{result=}')
        # captured = capsys.readouterr()
        assert result
