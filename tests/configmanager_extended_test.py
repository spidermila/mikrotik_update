"""
Extended ConfigManager tests covering the load_config branches
that are not reached by the pre-existing tests (which fail due to
PermissionError on /path/to/log).  All tests here mock Logger so
no filesystem access is required.
"""
from unittest.mock import mock_open
from unittest.mock import patch

import yaml

from mu.configmanager import ConfigManager


def _base_global(**extra):
    g = {
        'backup_dir': '/tmp/backup',
        'private_key_file': '',
        'username': 'global-user',
        'log_dir': '/tmp/log',
    }
    g.update(extra)
    return g


def _make_data(global_opts=None, device_opts=None):
    gl = _base_global(**(global_opts or {}))
    dev = {'name': 'dev1', 'address': '10.0.0.1'}
    dev.update(device_opts or {})
    return {'global': gl, 'devices': [dev]}


# ─── deprecated online_upgrade_channel ───────────────────────────────────────

def test_load_config_deprecated_online_upgrade_channel(capsys):
    mock_data = _make_data(
        global_opts={'online_upgrade_channel': 'legacy'},
    )
    with patch('builtins.open', mock_open(read_data=yaml.dump(mock_data))):
        with patch('yaml.safe_load', return_value=mock_data):
            with patch('mu.configmanager.Logger'):
                cm = ConfigManager('dummy')
                devices, _ = cm.load_config()
    captured = capsys.readouterr()
    assert 'deprecated' in captured.out
    assert devices[0].online_update_channel == 'legacy'


# ─── username from device ────────────────────────────────────────────────────

def test_load_config_username_from_device():
    mock_data = _make_data(device_opts={'username': 'device-user'})
    with patch('builtins.open', mock_open(read_data=yaml.dump(mock_data))):
        with patch('yaml.safe_load', return_value=mock_data):
            with patch('mu.configmanager.Logger'):
                cm = ConfigManager('dummy')
                devices, _ = cm.load_config()
    assert devices[0].username == 'device-user'


# ─── username from global ────────────────────────────────────────────────────

def test_load_config_username_from_global():
    mock_data = _make_data()  # no username in device, global has 'global-user'
    with patch('builtins.open', mock_open(read_data=yaml.dump(mock_data))):
        with patch('yaml.safe_load', return_value=mock_data):
            with patch('mu.configmanager.Logger'):
                cm = ConfigManager('dummy')
                devices, _ = cm.load_config()
    assert devices[0].username == 'global-user'


# ─── no username at all ──────────────────────────────────────────────────────

def test_load_config_no_username_at_all(capsys):
    mock_data = _make_data(global_opts={'username': ''})
    # Remove username from global
    mock_data['global'].pop('username', None)
    with patch('builtins.open', mock_open(read_data=yaml.dump(mock_data))):
        with patch('yaml.safe_load', return_value=mock_data):
            with patch('mu.configmanager.Logger'):
                cm = ConfigManager('dummy')
                devices, _ = cm.load_config()
    captured = capsys.readouterr()
    assert 'Username not specified' in captured.out
    assert len(devices) == 0


# ─── port from device ────────────────────────────────────────────────────────

def test_load_config_port_from_device():
    mock_data = _make_data(
        global_opts={'port': 1000},
        device_opts={'port': 2222},
    )
    with patch('builtins.open', mock_open(read_data=yaml.dump(mock_data))):
        with patch('yaml.safe_load', return_value=mock_data):
            with patch('mu.configmanager.Logger'):
                cm = ConfigManager('dummy')
                devices, _ = cm.load_config()
    assert devices[0].port == 2222


# ─── port from global ────────────────────────────────────────────────────────

def test_load_config_port_from_global():
    mock_data = _make_data(global_opts={'port': 3333})
    with patch('builtins.open', mock_open(read_data=yaml.dump(mock_data))):
        with patch('yaml.safe_load', return_value=mock_data):
            with patch('mu.configmanager.Logger'):
                cm = ConfigManager('dummy')
                devices, _ = cm.load_config()
    assert devices[0].port == 3333


# ─── port default 22 ─────────────────────────────────────────────────────────

def test_load_config_port_default():
    mock_data = _make_data()  # no port anywhere
    with patch('builtins.open', mock_open(read_data=yaml.dump(mock_data))):
        with patch('yaml.safe_load', return_value=mock_data):
            with patch('mu.configmanager.Logger'):
                cm = ConfigManager('dummy')
                devices, _ = cm.load_config()
    assert devices[0].port == 22


# ─── online_update_channel from device ───────────────────────────────────────

def test_load_config_online_update_channel_from_device():
    mock_data = _make_data(
        global_opts={'online_update_channel': 'stable'},
        device_opts={'online_update_channel': 'testing'},
    )
    with patch('builtins.open', mock_open(read_data=yaml.dump(mock_data))):
        with patch('yaml.safe_load', return_value=mock_data):
            with patch('mu.configmanager.Logger'):
                cm = ConfigManager('dummy')
                devices, _ = cm.load_config()
    assert devices[0].online_update_channel == 'testing'


# ─── online_update_channel from global ───────────────────────────────────────

def test_load_config_online_update_channel_from_global():
    mock_data = _make_data(global_opts={'online_update_channel': 'long-term'})
    with patch('builtins.open', mock_open(read_data=yaml.dump(mock_data))):
        with patch('yaml.safe_load', return_value=mock_data):
            with patch('mu.configmanager.Logger'):
                cm = ConfigManager('dummy')
                devices, _ = cm.load_config()
    assert devices[0].online_update_channel == 'long-term'


# ─── online_update_channel default stable ────────────────────────────────────

def test_load_config_online_update_channel_default():
    mock_data = _make_data()  # no channel anywhere
    with patch('builtins.open', mock_open(read_data=yaml.dump(mock_data))):
        with patch('yaml.safe_load', return_value=mock_data):
            with patch('mu.configmanager.Logger'):
                cm = ConfigManager('dummy')
                devices, _ = cm.load_config()
    assert devices[0].online_update_channel == 'stable'


# ─── update_type from device ─────────────────────────────────────────────────

def test_load_config_update_type_from_device():
    mock_data = _make_data(
        global_opts={'update_type': 'online'},
        device_opts={'update_type': 'manual', 'packages': ['pkg1']},
    )
    with patch('builtins.open', mock_open(read_data=yaml.dump(mock_data))):
        with patch('yaml.safe_load', return_value=mock_data):
            with patch('mu.configmanager.Logger'):
                cm = ConfigManager('dummy')
                devices, _ = cm.load_config()
    assert devices[0].update_type == 'manual'


# ─── update_type from global ─────────────────────────────────────────────────

def test_load_config_update_type_from_global():
    mock_data = _make_data(global_opts={'update_type': 'online'})
    with patch('builtins.open', mock_open(read_data=yaml.dump(mock_data))):
        with patch('yaml.safe_load', return_value=mock_data):
            with patch('mu.configmanager.Logger'):
                cm = ConfigManager('dummy')
                devices, _ = cm.load_config()
    assert devices[0].update_type == 'online'


# ─── update_type default online ──────────────────────────────────────────────

def test_load_config_update_type_default():
    mock_data = _make_data()  # no update_type anywhere
    with patch('builtins.open', mock_open(read_data=yaml.dump(mock_data))):
        with patch('yaml.safe_load', return_value=mock_data):
            with patch('mu.configmanager.Logger'):
                cm = ConfigManager('dummy')
                devices, _ = cm.load_config()
    assert devices[0].update_type == 'online'


# ─── packages loaded for manual update_type ──────────────────────────────────

def test_load_config_packages_for_manual_update():
    mock_data = _make_data(
        device_opts={
            'update_type': 'manual',
            'packages': ['pkg1.npk', 'pkg2.npk'],
        },
    )
    with patch('builtins.open', mock_open(read_data=yaml.dump(mock_data))):
        with patch('yaml.safe_load', return_value=mock_data):
            with patch('mu.configmanager.Logger'):
                cm = ConfigManager('dummy')
                devices, _ = cm.load_config()
    assert devices[0].packages == ['pkg1.npk', 'pkg2.npk']


# ─── packages empty for online update_type ───────────────────────────────────

def test_load_config_no_packages_for_online_update():
    mock_data = _make_data(device_opts={'update_type': 'online'})
    with patch('builtins.open', mock_open(read_data=yaml.dump(mock_data))):
        with patch('yaml.safe_load', return_value=mock_data):
            with patch('mu.configmanager.Logger'):
                cm = ConfigManager('dummy')
                devices, _ = cm.load_config()
    assert devices[0].packages == []
