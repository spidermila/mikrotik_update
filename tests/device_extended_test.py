import pathlib
from unittest.mock import call
from unittest.mock import MagicMock
from unittest.mock import patch

import paramiko
import pytest

from mu.config import Config
from mu.device import Device
from mu.logger import Logger


# mock_conf and disconnected_dev fixtures live in conftest.py


@pytest.fixture
def dev(mock_conf):
    d = Device(
        conf=mock_conf,
        name='router',
        address='10.0.0.1',
        port=22,
        username='admin',
        update_type='online',
        logger=MagicMock(spec=Logger),
    )
    d.client = MagicMock()
    return d


# ─── _ssh_check ──────────────────────────────────────────────────────────────

def test_ssh_check_no_client_raises(disconnected_dev):
    with pytest.raises(SystemExit):
        disconnected_dev._ssh_check()


# ─── ssh_call ────────────────────────────────────────────────────────────────

def test_ssh_call_returns_lines(dev):
    mock_stdout = MagicMock()
    mock_stdout.readlines.return_value = ['line1\n', 'line2\n']
    dev.client.exec_command.return_value = (
        MagicMock(), mock_stdout, MagicMock(),
    )
    result = dev.ssh_call('some command')
    assert result == ['line1', 'line2']


def test_ssh_call_raises_on_exception(dev):
    dev.client.exec_command.side_effect = Exception('boom')
    with pytest.raises(Exception):
        dev.ssh_call('cmd')


# ─── ssh_close ───────────────────────────────────────────────────────────────

def test_ssh_close_closes_client(dev):
    saved_client = dev.client
    dev.ssh_close()
    saved_client.close.assert_called_once()
    assert dev.client is None


def test_ssh_close_no_client(disconnected_dev):
    disconnected_dev.ssh_close()  # should not raise


# ─── ssh_connect ─────────────────────────────────────────────────────────────

def test_ssh_connect_with_key(disconnected_dev):
    disconnected_dev.conf.key = MagicMock()
    with patch('paramiko.SSHClient') as mock_ssh_class:
        mock_client = MagicMock()
        mock_ssh_class.return_value = mock_client
        with patch.object(
            disconnected_dev, '_get_identity', return_value='myrouter',
        ):
            disconnected_dev.ssh_connect()
    assert disconnected_dev.identity == 'myrouter'
    mock_client.connect.assert_called_once()


def test_ssh_connect_without_key(disconnected_dev):
    with patch('paramiko.SSHClient') as mock_ssh_class:
        mock_client = MagicMock()
        mock_ssh_class.return_value = mock_client
        with patch.object(
            disconnected_dev, '_get_identity', return_value='myrouter',
        ):
            disconnected_dev.ssh_connect()
    mock_client.connect.assert_called_once()


def test_ssh_connect_auth_exception(disconnected_dev):
    with patch('paramiko.SSHClient') as mock_ssh_class:
        mock_client = MagicMock()
        mock_ssh_class.return_value = mock_client
        mock_client.connect.side_effect = (
            paramiko.AuthenticationException('fail')
        )
        with pytest.raises(paramiko.AuthenticationException):
            disconnected_dev.ssh_connect()


# ─── ssh_test ────────────────────────────────────────────────────────────────

def test_ssh_test_success_with_key(disconnected_dev):
    disconnected_dev.conf.key = MagicMock()
    with patch('paramiko.SSHClient') as mock_ssh_class:
        mock_client = MagicMock()
        mock_ssh_class.return_value = mock_client
        result = disconnected_dev.ssh_test()
    assert result is True
    mock_client.close.assert_called_once()


def test_ssh_test_success_without_key(disconnected_dev):
    with patch('paramiko.SSHClient') as mock_ssh_class:
        mock_client = MagicMock()
        mock_ssh_class.return_value = mock_client
        result = disconnected_dev.ssh_test()
    assert result is True


def test_ssh_test_auth_exception_user_says_n(disconnected_dev):
    disconnected_dev.conf.public_key_file = None
    disconnected_dev.conf.public_key_owner = None
    with patch('paramiko.SSHClient') as mock_ssh_class:
        mock_client = MagicMock()
        mock_ssh_class.return_value = mock_client
        mock_client.connect.side_effect = (
            paramiko.AuthenticationException('fail')
        )
        with patch('builtins.input', return_value='n'):
            with pytest.raises(SystemExit):
                disconnected_dev.ssh_test()


def test_ssh_test_auth_exception_user_says_y(disconnected_dev):
    disconnected_dev.conf.public_key_file = 'mykey.pub'
    disconnected_dev.conf.public_key_owner = 'owner'
    with patch('paramiko.SSHClient') as mock_ssh_class:
        mock_client = MagicMock()
        mock_ssh_class.return_value = mock_client
        mock_client.connect.side_effect = (
            paramiko.AuthenticationException('fail')
        )
        with patch('builtins.input', return_value='y'):
            with patch('mu.device.UserRegistrator') as mock_ur_class:
                mock_ur = MagicMock()
                mock_ur.run.return_value = True
                mock_ur_class.return_value = mock_ur
                result = disconnected_dev.ssh_test()
    assert result is True


def test_ssh_test_auth_exception_device_has_public_key_file(disconnected_dev):
    disconnected_dev.conf.public_key_file = 'global_key.pub'
    disconnected_dev.conf.public_key_owner = 'owner'
    disconnected_dev.public_key_file = 'device_key.pub'
    disconnected_dev.public_key_owner = 'device_owner'
    with patch('paramiko.SSHClient') as mock_ssh_class:
        mock_client = MagicMock()
        mock_ssh_class.return_value = mock_client
        mock_client.connect.side_effect = (
            paramiko.AuthenticationException('fail')
        )
        with patch('builtins.input', return_value='y'):
            with patch('mu.device.UserRegistrator') as mock_ur_class:
                mock_ur = MagicMock()
                mock_ur.run.return_value = True
                mock_ur_class.return_value = mock_ur
                result = disconnected_dev.ssh_test()
    assert result is True


def test_ssh_test_os_error(disconnected_dev):
    with patch('paramiko.SSHClient') as mock_ssh_class:
        mock_client = MagicMock()
        mock_ssh_class.return_value = mock_client
        mock_client.connect.side_effect = OSError('unreachable')
        result = disconnected_dev.ssh_test()
    assert result is False


# ─── simple_ssh_test ─────────────────────────────────────────────────────────

def test_simple_ssh_test_success_with_key(disconnected_dev):
    disconnected_dev.conf.key = MagicMock()
    with patch('paramiko.SSHClient') as mock_ssh_class:
        mock_client = MagicMock()
        mock_ssh_class.return_value = mock_client
        result = disconnected_dev.simple_ssh_test()
    assert result is True


def test_simple_ssh_test_success_without_key(disconnected_dev):
    with patch('paramiko.SSHClient') as mock_ssh_class:
        mock_client = MagicMock()
        mock_ssh_class.return_value = mock_client
        result = disconnected_dev.simple_ssh_test()
    assert result is True


def test_simple_ssh_test_failure(disconnected_dev):
    with patch('paramiko.SSHClient') as mock_ssh_class:
        mock_client = MagicMock()
        mock_ssh_class.return_value = mock_client
        mock_client.connect.side_effect = Exception('fail')
        result = disconnected_dev.simple_ssh_test()
    assert result is False


# ─── backup ──────────────────────────────────────────────────────────────────

def test_backup_success(dev):
    dev.identity = 'myrouter'
    dev.conf.delete_backup_after_download = False
    saved_output = ['Configuration backup saved\r']
    with patch.object(dev, 'ssh_call', return_value=saved_output):
        with patch('mu.device.SCPClient') as mock_scp_class:
            mock_scp = MagicMock()
            mock_scp_class.return_value.__enter__ = MagicMock(
                return_value=mock_scp,
            )
            mock_scp_class.return_value.__exit__ = MagicMock(
                return_value=False,
            )
            with patch.object(pathlib.Path, 'mkdir'):
                with patch.object(dev, 'export_config', return_value=True):
                    result = dev.backup()
    assert result is True


def test_backup_failure_message(dev):
    dev.identity = 'myrouter'
    with patch.object(dev, 'ssh_call', return_value=['some error output']):
        with patch.object(pathlib.Path, 'mkdir'):
            result = dev.backup()
    assert result is False


def test_backup_scp_exception(dev):
    dev.identity = 'myrouter'
    saved_output = ['Configuration backup saved\r']
    with patch.object(dev, 'ssh_call', return_value=saved_output):
        with patch('mu.device.SCPClient', side_effect=Exception('scp fail')):
            with patch.object(pathlib.Path, 'mkdir'):
                with patch.object(dev, 'export_config', return_value=True):
                    result = dev.backup()
    assert result is False


def test_backup_with_delete(dev):
    dev.identity = 'myrouter'
    dev.conf.delete_backup_after_download = True
    saved_output = ['Configuration backup saved\r']
    with patch.object(dev, 'ssh_call', return_value=saved_output):
        with patch('mu.device.SCPClient') as mock_scp_class:
            mock_scp = MagicMock()
            mock_scp_class.return_value.__enter__ = MagicMock(
                return_value=mock_scp,
            )
            mock_scp_class.return_value.__exit__ = MagicMock(
                return_value=False,
            )
            with patch.object(pathlib.Path, 'mkdir'):
                with patch.object(dev, '_delete_file') as mock_delete:
                    with patch.object(
                        dev, 'export_config', return_value=True,
                    ):
                        result = dev.backup()
    assert result is True
    mock_delete.assert_called_once()


# ─── export_config ───────────────────────────────────────────────────────────

def test_export_config_uses_backup_basename(dev, tmp_path):
    dev.identity = 'myrouter'
    dev.conf.backup_dir = tmp_path
    dev.backup_file_full_name = 'myrouter-20240101-1200.backup'
    export_lines = ['# comment', '/ip address', 'add address=1.2.3.4/24']
    with patch.object(dev, 'ssh_call', return_value=export_lines):
        result = dev.export_config()
    assert result is True
    out = tmp_path / 'myrouter-20240101-1200.rsc'
    assert out.exists()
    assert out.read_text() == '\n'.join(export_lines) + '\n'
    assert (out.stat().st_mode & 0o777) == 0o600
    assert dev.export_file_full_name == 'myrouter-20240101-1200.rsc'


def test_export_config_without_backup_basename(dev, tmp_path):
    dev.identity = 'myrouter'
    dev.conf.backup_dir = tmp_path
    with patch.object(dev, 'ssh_call', return_value=['line']):
        result = dev.export_config()
    assert result is True
    written = list(tmp_path.glob('myrouter-*.rsc'))
    assert len(written) == 1


def test_export_config_ssh_failure(dev, tmp_path):
    dev.identity = 'myrouter'
    dev.conf.backup_dir = tmp_path
    with patch.object(dev, 'ssh_call', side_effect=Exception('boom')):
        result = dev.export_config()
    assert result is False
    assert list(tmp_path.glob('*.rsc')) == []


def test_export_config_write_failure(dev, tmp_path):
    dev.identity = 'myrouter'
    dev.conf.backup_dir = tmp_path
    with patch.object(dev, 'ssh_call', return_value=['line']):
        with patch.object(
            pathlib.Path, 'write_text', side_effect=OSError('disk full'),
        ):
            result = dev.export_config()
    assert result is False


# ─── exec_command ────────────────────────────────────────────────────────────

def test_exec_command_prints_output(dev, capsys):
    with patch.object(dev, 'ssh_call', return_value=['line1', 'line2']):
        dev.exec_command('some cmd')
    captured = capsys.readouterr()
    assert 'line1' in captured.out
    assert 'line2' in captured.out


# ─── get_installed_packages ──────────────────────────────────────────────────

def test_get_installed_packages_normal(dev):
    output = [
        'Columns: #, NAME, VERSION, SCHEDULED',
        ' 0 routeros     7.15',
        ' 1 wireless     7.15',
    ]
    with patch.object(dev, 'ssh_call', return_value=output):
        result = dev.get_installed_packages()
    assert 'routeros 7.15' in result
    assert 'wireless 7.15' in result


def test_get_installed_packages_empty_output(dev):
    with patch.object(dev, 'ssh_call', return_value=['only one line']):
        result = dev.get_installed_packages()
    assert result == []


# ─── get_update_available ────────────────────────────────────────────────────

def test_get_update_available_true(dev):
    with patch.object(dev, 'refresh_update_info'):
        dev.update_available = True
        result = dev.get_update_available()
    assert result is True


def test_get_update_available_false(dev):
    with patch.object(dev, 'refresh_update_info'):
        dev.update_available = False
        result = dev.get_update_available()
    assert result is False


# ─── refresh_update_info ─────────────────────────────────────────────────────

def test_refresh_update_info_new_version_available(dev):
    dev.online_update_channel = 'stable'
    output = [
        '  installed-version: 7.14',
        '  latest-version: 7.15',
        '  status: New version is available',
    ]
    with patch.object(dev, '_get_channel', return_value='stable'):
        with patch.object(dev, 'ssh_call', return_value=output):
            dev.refresh_update_info()
    assert dev.update_available is True
    assert dev.installed_version == '7.14'
    assert dev.latest_version == '7.15'


def test_refresh_update_info_not_available(dev):
    dev.online_update_channel = 'stable'
    output = [
        '  installed-version: 7.15',
        '  latest-version: 7.15',
        '  status: System is already up to date',
    ]
    with patch.object(dev, '_get_channel', return_value='stable'):
        with patch.object(dev, 'ssh_call', return_value=output):
            dev.refresh_update_info()
    assert dev.update_available is False


def test_refresh_update_info_downloaded_reboot(dev):
    dev.online_update_channel = 'stable'
    output = [
        '  status: Downloaded, please reboot',
    ]
    with patch.object(dev, '_get_channel', return_value='stable'):
        with patch.object(dev, 'ssh_call', return_value=output):
            dev.refresh_update_info()
    assert dev.update_available is False


def test_refresh_update_info_channel_switch(dev):
    dev.online_update_channel = 'testing'
    output = [
        '  installed-version: 7.14',
        '  latest-version: 7.15',
        '  status: New version is available',
    ]
    with patch.object(dev, '_get_channel', return_value='stable'):
        with patch.object(dev, 'ssh_call', return_value=output):
            with patch.object(dev, '_set_channel') as mock_set:
                dev.refresh_update_info()
    assert dev.update_available is True
    assert mock_set.call_args_list == [call('testing'), call('stable')]


def test_refresh_update_info_channel_switch_no_update(dev):
    dev.online_update_channel = 'testing'
    output = [
        '  installed-version: 7.15',
        '  latest-version: 7.15',
        '  status: System is already up to date',
    ]
    with patch.object(dev, '_get_channel', return_value='stable'):
        with patch.object(dev, 'ssh_call', return_value=output):
            with patch.object(dev, '_set_channel') as mock_set:
                dev.refresh_update_info()
    assert dev.update_available is False
    assert mock_set.call_args_list == [call('testing'), call('stable')]


# ─── reboot_and_wait ─────────────────────────────────────────────────────────

def test_reboot_and_wait_success(dev):
    dev.conf.reboot_timeout = 30
    with patch.object(dev, '_reboot'):
        with patch.object(dev, 'simple_ssh_test', return_value=True):
            with patch('time.sleep'):
                result = dev.reboot_and_wait()
    assert result is True


def test_reboot_and_wait_downgrade(dev):
    dev.conf.reboot_timeout = 30
    with patch.object(dev, '_downgrade') as mock_downgrade:
        with patch.object(dev, 'simple_ssh_test', return_value=True):
            with patch('time.sleep'):
                result = dev.reboot_and_wait(downgrade=True)
    assert result is True
    mock_downgrade.assert_called_once()


def test_reboot_and_wait_timeout(dev):
    dev.conf.reboot_timeout = 0
    with patch.object(dev, '_reboot'):
        with patch.object(dev, 'simple_ssh_test', return_value=False):
            with patch('time.sleep'):
                result = dev.reboot_and_wait()
    assert result is False


# ─── update (online) ─────────────────────────────────────────────────────────

def test_update_online_same_channel(dev):
    dev.update_type = 'online'
    with patch.object(dev, '_get_channel', return_value='stable'):
        with patch.object(dev, 'refresh_update_info'):
            with patch.object(dev, '_online_update') as mock_online:
                dev.update()
    mock_online.assert_called_once()


def test_update_online_different_channel(dev):
    dev.update_type = 'online'
    dev.online_update_channel = 'testing'
    with patch.object(dev, '_get_channel', return_value='stable'):
        with patch.object(dev, '_set_channel') as mock_set:
            with patch.object(dev, 'refresh_update_info'):
                with patch.object(dev, '_online_update'):
                    with patch('time.sleep'):
                        dev.update()
    mock_set.assert_called_once_with('testing')


def test_update_manual(dev):
    dev.update_type = 'manual'
    with patch.object(dev, 'get_installed_packages', return_value=[]):
        with patch.object(dev, '_manual_update') as mock_manual:
            dev.update()
    mock_manual.assert_called_once()


# ─── _online_update ──────────────────────────────────────────────────────────

def test_online_update_not_available(dev):
    dev.update_available = False
    dev._online_update()
    dev.logger.log.assert_called_with(
        'info',
        'router',
        'update not available',
        stdout=True,
    )


def test_online_update_download_success(dev):
    dev.update_available = True
    dev.version_info_str = 'installed: 7.14, available: 7.15'
    with patch.object(dev, '_download_update', return_value=True):
        with patch.object(dev, 'reboot_and_wait', return_value=True):
            with patch.object(dev, 'ssh_connect') as mock_connect:
                with patch.object(dev, 'refresh_update_info') as mock_refresh:
                    dev._online_update()
    mock_connect.assert_called_once()
    mock_refresh.assert_called_once()


def test_online_update_download_failure(dev):
    dev.update_available = True
    dev.version_info_str = 'installed: 7.14, available: 7.15'
    with patch.object(dev, '_download_update', return_value=False):
        dev._online_update()
    dev.logger.log.assert_called_with(
        'error',
        'router',
        'download not successful',
        stdout=True,
    )


def test_online_update_reboot_fails(dev):
    dev.update_available = True
    dev.version_info_str = 'installed: 7.14, available: 7.15'
    with patch.object(dev, '_download_update', return_value=True):
        with patch.object(dev, 'reboot_and_wait', return_value=False):
            with patch.object(dev, 'ssh_connect') as mock_connect:
                dev._online_update()
    mock_connect.assert_not_called()


# ─── _download_update ────────────────────────────────────────────────────────

def test_download_update_success(dev):
    output = ['  status: Downloaded, please reboot']
    with patch.object(dev, 'ssh_call', return_value=output):
        result = dev._download_update()
    assert result is True


def test_download_update_failure(dev):
    output = ['  status: Some other status']
    with patch.object(dev, 'ssh_call', return_value=output):
        result = dev._download_update()
    assert result is False


# ─── _manual_update ──────────────────────────────────────────────────────────

def test_manual_update_no_packages(dev):
    dev.packages = []
    dev._manual_update()
    dev.logger.log.assert_called_with(
        'error',
        'router',
        'manual update selected but no packages provided',
        stdout=True,
    )


def test_manual_update_package_not_exist(dev, tmp_path):
    pkg = tmp_path / 'routeros-7.15.npk'
    dev.packages = [str(pkg)]
    dev._manual_update()
    dev.logger.log.assert_called_with(
        'error',
        'router',
        f'{pkg} does not exist',
        stdout=True,
    )


def test_manual_update_success(dev, tmp_path):
    pkg = tmp_path / 'routeros-7.15.npk'
    pkg.write_bytes(b'fake pkg')
    dev.packages = [str(pkg)]
    installed = ['routeros 7.14']
    with patch.object(dev, 'get_installed_packages', return_value=installed):
        with patch.object(dev, '_upload_package', return_value=True):
            with patch.object(dev, 'reboot_and_wait', return_value=True):
                with patch.object(dev, 'ssh_connect') as mock_connect:
                    with patch.object(
                        dev, 'refresh_update_info',
                    ) as mock_refresh:
                        dev._manual_update()
    mock_connect.assert_called_once()
    mock_refresh.assert_called_once()


def test_manual_update_upload_fails(dev, tmp_path):
    pkg = tmp_path / 'routeros-7.15.npk'
    pkg.write_bytes(b'fake pkg')
    dev.packages = [str(pkg)]
    installed = ['routeros 7.14']
    with patch.object(dev, 'get_installed_packages', return_value=installed):
        with patch.object(dev, '_upload_package', return_value=False):
            dev._manual_update()
    dev.logger.log.assert_called_with(
        'error',
        'router',
        f'failed to upload {pkg} to device',
        stdout=True,
    )


def test_manual_update_downgrade(dev, tmp_path):
    pkg = tmp_path / 'routeros-7.13.npk'
    pkg.write_bytes(b'fake pkg')
    dev.packages = [str(pkg)]
    installed = ['routeros 7.15']
    with patch.object(dev, 'get_installed_packages', return_value=installed):
        with patch.object(dev, '_upload_package', return_value=True):
            with patch.object(
                dev, 'reboot_and_wait', return_value=True,
            ) as mock_reboot:
                with patch.object(dev, 'ssh_connect'):
                    with patch.object(dev, 'refresh_update_info'):
                        dev._manual_update()
    mock_reboot.assert_called_once_with(downgrade=True)


def test_manual_update_reboot_fails(dev, tmp_path):
    pkg = tmp_path / 'routeros-7.15.npk'
    pkg.write_bytes(b'fake pkg')
    dev.packages = [str(pkg)]
    installed = ['routeros 7.14']
    with patch.object(dev, 'get_installed_packages', return_value=installed):
        with patch.object(dev, '_upload_package', return_value=True):
            with patch.object(dev, 'reboot_and_wait', return_value=False):
                with patch.object(dev, 'ssh_connect') as mock_connect:
                    dev._manual_update()
    mock_connect.assert_not_called()


# ─── _get_identity ───────────────────────────────────────────────────────────

def test_get_identity(dev):
    with patch.object(dev, 'ssh_call', return_value=['name: myrouter']):
        result = dev._get_identity()
    assert result == 'myrouter'


# ─── _get_channel ────────────────────────────────────────────────────────────

def test_get_channel_found(dev):
    with patch.object(dev, 'ssh_call', return_value=['  channel: stable']):
        result = dev._get_channel()
    assert result == 'stable'


def test_get_channel_not_found(dev):
    with patch.object(dev, 'ssh_call', return_value=['  something: else']):
        result = dev._get_channel()
    assert result == ''


# ─── _set_channel ────────────────────────────────────────────────────────────

def test_set_channel_success(dev):
    with patch.object(dev, 'ssh_call', return_value=[]):
        dev._set_channel('testing')


def test_set_channel_syntax_error(dev):
    with patch.object(dev, 'ssh_call', return_value=['syntax error']):
        dev._set_channel('bad-channel')
    dev.logger.log.assert_called()


# ─── _delete_file ────────────────────────────────────────────────────────────

def test_delete_file(dev):
    with patch.object(dev, 'ssh_call', return_value=[]) as mock_call:
        dev._delete_file('myfile.backup')
    mock_call.assert_called_with('file remove myfile.backup')


# ─── _reboot ─────────────────────────────────────────────────────────────────

def test_reboot(dev):
    with patch.object(dev, 'ssh_call', return_value=[]) as mock_call:
        dev._reboot()
    mock_call.assert_called_with('system reboot\ny')


# ─── _downgrade ──────────────────────────────────────────────────────────────

def test_downgrade(dev):
    with patch.object(dev, 'ssh_call', return_value=[]) as mock_call:
        dev._downgrade()
    mock_call.assert_called_with('system package downgrade\ny')


# ─── _routerboard_upgrade ────────────────────────────────────────────────────

def test_routerboard_upgrade(dev):
    with patch.object(dev, 'ssh_call', return_value=[]) as mock_call:
        dev._routerboard_upgrade()
    mock_call.assert_called_with('system routerboard upgrade')


# ─── _upload_package ─────────────────────────────────────────────────────────

def test_upload_package_success(dev, tmp_path):
    pkg = tmp_path / 'routeros-7.15.npk'
    pkg.write_bytes(b'fake')
    with patch('mu.device.SCPClient') as mock_scp_class:
        mock_scp = MagicMock()
        mock_scp_class.return_value.__enter__ = MagicMock(
            return_value=mock_scp,
        )
        mock_scp_class.return_value.__exit__ = MagicMock(return_value=False)
        result = dev._upload_package(pkg)
    assert result is True


def test_upload_package_failure(dev, tmp_path):
    pkg = tmp_path / 'routeros-7.15.npk'
    pkg.write_bytes(b'fake')
    with patch('mu.device.SCPClient', side_effect=Exception('scp fail')):
        result = dev._upload_package(pkg)
    assert result is False


# ─── firmware_update ─────────────────────────────────────────────────────────

def test_firmware_update_reconnect_fails(dev):
    dev.current_firmware = '7.14'
    dev.upgrade_firmware = '7.16'
    with patch.object(dev, 'refresh_firmware_info'):
        with patch.object(dev, '_routerboard_upgrade'):
            with patch.object(dev, 'reboot_and_wait', return_value=True):
                with patch.object(
                    dev, 'ssh_connect', side_effect=Exception('fail'),
                ):
                    result = dev.firmware_update()
    assert result is False


def test_firmware_update_still_different_after_reboot(dev):
    call_count = {'n': 0}

    def side_refresh():
        call_count['n'] += 1
        dev.current_firmware = '7.14'
        dev.upgrade_firmware = '7.16'

    with patch.object(dev, 'refresh_firmware_info', side_effect=side_refresh):
        with patch.object(dev, '_routerboard_upgrade'):
            with patch.object(dev, 'reboot_and_wait', return_value=True):
                with patch.object(dev, 'ssh_connect'):
                    result = dev.firmware_update()
    assert result is False


# ─── version_is_lower ────────────────────────────────────────────────────────

@pytest.fixture(scope='module')
def version_dev():
    return Device(
        conf=MagicMock(spec=Config),
        name='r',
        address='10.0.0.1',
        port=22,
        username='admin',
        update_type='online',
        logger=MagicMock(spec=Logger),
    )


@pytest.mark.parametrize(
    'a,b,expected', [
        ('6.99', '7.0', True),
        ('7.0', '6.99', False),
        ('7.14', '7.15', True),
        ('7.15', '7.14', False),
        ('7.15', '7.15', False),
        ('7.15beta9', '7.15', True),
        ('7.15', '7.15beta9', False),
        ('7.15alpha1', '7.15', True),
        ('7.15', '7.15alpha1', False),
        ('7.15beta1', '7.15', True),
        ('7.15', '7.15beta1', False),
        ('7.15beta1', '7.15beta2', True),
        ('7.15beta2', '7.15beta1', False),
        ('7.15', '7.15', False),
        ('7.15.1', '7.15.2', True),
        ('7.15.2', '7.15.1', False),
        ('7.15.1', '7.15.1', False),
        ('7.15rc1', '7.16', True),
        ('7.14', '7.15rc1', True),
    ],
)
def test_version_is_lower(version_dev, a, b, expected):
    assert version_dev.version_is_lower(a, b) is expected


# ─── defensive client=None guard coverage ────────────────────────────────────

def test_ssh_call_client_none_after_check(disconnected_dev):
    """Cover raise when client is None despite _ssh_check pass."""
    with patch.object(disconnected_dev, '_ssh_check'):
        with pytest.raises(Exception):
            disconnected_dev.ssh_call('cmd')


def test_upload_package_client_none_after_check(disconnected_dev, tmp_path):
    """Cover raise when client is None despite _ssh_check pass."""
    pkg = tmp_path / 'routeros-7.15.npk'
    pkg.write_bytes(b'fake')
    with patch.object(disconnected_dev, '_ssh_check'):
        result = disconnected_dev._upload_package(pkg)
    assert result is False


def test_backup_client_none_after_check(disconnected_dev):
    """Cover raise when client is None inside backup try block."""
    disconnected_dev.identity = 'myrouter'
    backup_saved = ['Configuration backup saved\r']
    with patch.object(disconnected_dev, '_ssh_check'):
        with patch.object(
            disconnected_dev, 'ssh_call', return_value=backup_saved,
        ):
            with patch.object(pathlib.Path, 'mkdir'):
                with patch.object(
                    disconnected_dev, 'export_config', return_value=True,
                ):
                    result = disconnected_dev.backup()
    assert result is False
