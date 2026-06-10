# import pathlib
from unittest.mock import MagicMock
from unittest.mock import patch

import pytest

from mu.config import Config
from mu.device import Device
from mu.logger import Logger


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
        logger=logger,
        packages=['package1', 'package2'],
    )
    return dev


def test_device_init(device):
    mock_config = config
    mock_logger = logger
    assert device.conf == mock_config
    assert device.name == 'test-name'
    assert device.address == '192.168.1.1'
    assert device.port == 333
    assert device.username == 'test-user'
    assert device.update_type == 'test-update'
    assert device.logger == mock_logger
    assert device.packages == ['package1', 'package2']
    assert device.online_update_channel == 'stable'
    assert device.client is None
    assert device.identity == ''
    assert device.public_key_file is None
    assert device.public_key_owner is None
    assert device.installed_version == 'unknown'
    assert device.latest_version == 'unknown'
    assert device.version_info_str == 'installed: unknown, available: unknown'
    assert device.update_firmware is False
    assert device.current_firmware == 'unknown'
    assert device.upgrade_firmware == 'unknown'
    assert device.firmware_info_str == (
        'current firmware: unknown, upgrade firmware: unknown'
    )


@pytest.fixture
def connected_device():
    mock_conf = MagicMock(spec=Config)
    mock_logger = MagicMock(spec=Logger)
    dev = Device(
        conf=mock_conf,
        name='test-router',
        address='192.168.1.1',
        port=22,
        username='admin',
        update_type='online',
        logger=mock_logger,
    )
    dev.client = MagicMock()
    return dev


def test_refresh_firmware_info(connected_device):
    routerboard_output = [
        '       routerboard: yes',
        '            model: RBmAPL-2nD',
        '  current-firmware: 7.14.3',
        '  upgrade-firmware: 7.16',
    ]
    with patch.object(
        connected_device, 'ssh_call', return_value=routerboard_output,
    ):
        connected_device.refresh_firmware_info()
    assert connected_device.current_firmware == '7.14.3'
    assert connected_device.upgrade_firmware == '7.16'
    assert connected_device.firmware_info_str == (
        'current firmware: 7.14.3, upgrade firmware: 7.16'
    )


def test_refresh_firmware_info_up_to_date(connected_device):
    routerboard_output = [
        '       routerboard: yes',
        '  current-firmware: 7.16',
        '  upgrade-firmware: 7.16',
    ]
    with patch.object(
        connected_device, 'ssh_call', return_value=routerboard_output,
    ):
        connected_device.refresh_firmware_info()
    assert connected_device.current_firmware == '7.16'
    assert connected_device.upgrade_firmware == '7.16'


def test_get_firmware_update_available_true(connected_device):
    routerboard_output = [
        '  current-firmware: 7.14.3',
        '  upgrade-firmware: 7.16',
    ]
    with patch.object(
        connected_device, 'ssh_call', return_value=routerboard_output,
    ):
        assert connected_device.get_firmware_update_available() is True


def test_get_firmware_update_available_false(connected_device):
    routerboard_output = [
        '  current-firmware: 7.16',
        '  upgrade-firmware: 7.16',
    ]
    with patch.object(
        connected_device, 'ssh_call', return_value=routerboard_output,
    ):
        assert connected_device.get_firmware_update_available() is False


def test_firmware_update_already_up_to_date(connected_device):
    routerboard_output = [
        '  current-firmware: 7.16',
        '  upgrade-firmware: 7.16',
    ]
    with patch.object(
        connected_device, 'ssh_call', return_value=routerboard_output,
    ):
        result = connected_device.firmware_update()
    assert result is True
    connected_device.logger.log.assert_called_with(
        'info',
        'test-router',
        'routerboard firmware up to date: 7.16',
        stdout=True,
    )


def test_firmware_update_performs_upgrade(connected_device):
    before_output = [
        '  current-firmware: 7.14.3',
        '  upgrade-firmware: 7.16',
    ]
    after_output = [
        '  current-firmware: 7.16',
        '  upgrade-firmware: 7.16',
    ]
    call_count = 0

    def ssh_call_side_effect(cmd):
        nonlocal call_count
        if 'routerboard print' in cmd:
            call_count += 1
            return before_output if call_count == 1 else after_output
        return []

    with patch.object(
        connected_device, 'ssh_call', side_effect=ssh_call_side_effect,
    ):
        with patch.object(
            connected_device, 'reboot_and_wait', return_value=True,
        ):
            with patch.object(connected_device, 'ssh_connect'):
                result = connected_device.firmware_update()
    assert result is True
    assert connected_device.current_firmware == '7.16'


def test_firmware_update_reboot_timeout(connected_device):
    routerboard_output = [
        '  current-firmware: 7.14.3',
        '  upgrade-firmware: 7.16',
    ]
    with patch.object(
        connected_device, 'ssh_call', return_value=routerboard_output,
    ):
        with patch.object(
            connected_device, 'reboot_and_wait', return_value=False,
        ):
            result = connected_device.firmware_update()
    assert result is False
