# import pathlib
from unittest.mock import MagicMock

import pytest

from mu.config import Config
from mu.device import Device
from mu.logger import Logger
# from unittest.mock import mock_open
# from unittest.mock import patch


@pytest.fixture(scope='session', autouse=True)
def config():
    yield MagicMock(spec=Config)


@pytest.fixture(scope='session', autouse=True)
def logger():
    yield MagicMock(spec=Logger)


@pytest.fixture(scope='session')
def device():
    dev = Device(
        conf=config,
        name='test-name',
        address='192.168.1.1',
        port=333,
        username='test-user',
        update_type='test-update',
        packages=['package1', 'package2'],
    )
    return dev


def test_device_init(device):
    mock_config = config
    assert device.conf == mock_config
    assert device.name == 'test-name'
    assert device.address == '192.168.1.1'
    assert device.port == 333
    assert device.username == 'test-user'
    assert device.update_type == 'test-update'
    assert device.packages == ['package1', 'package2']
    assert device.online_update_channel == 'stable'
    assert device.client is None
    assert device.identity == ''
    assert device.public_key_file is None
    assert device.public_key_owner is None
    assert device.installed_version == 'unknown'
    assert device.latest_version == 'unknown'
    assert device.version_info_str == 'installed: unknown, available: unknown'


def test_device_backup(device, capsys):
    with pytest.raises(SystemExit) as excinfo:
        device.backup(logger=logger)
    assert excinfo.type == SystemExit
    assert excinfo.value.code == 1
    captured = capsys.readouterr()
    assert 'SSH not connected' in captured.out
