import pathlib
from unittest.mock import call
from unittest.mock import MagicMock
from unittest.mock import patch

import paramiko
import pytest

from mu.config import Config
from mu.device import _FREE_SPACE_CMD
from mu.device import _LIST_FILES_CMD
from mu.device import _parse_ros_time
from mu.device import _ros_quote
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


def test_backup_delete_refuses_comma_name(dev):
    dev.identity = 'my,router'
    dev.conf.delete_backup_after_download = True
    saved = ['Configuration backup saved\r']
    with patch.object(dev, 'ssh_call', return_value=saved) as ssh:
        with patch('mu.device.SCPClient'):
            with patch.object(pathlib.Path, 'mkdir'):
                with patch.object(dev, 'export_config', return_value=True):
                    result = dev.backup()
    assert result is True
    assert ',' in dev.backup_file_full_name
    assert not any('remove' in str(c) for c in ssh.call_args_list)


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
        with patch('mu.device.os.open', side_effect=OSError('disk full')):
            result = dev.export_config()
    assert result is False
    assert list(tmp_path.glob('*.rsc')) == []


def test_export_config_empty_output(dev, tmp_path):
    dev.identity = 'myrouter'
    dev.conf.backup_dir = tmp_path
    with patch.object(dev, 'ssh_call', return_value=[]):
        result = dev.export_config()
    assert result is False
    assert list(tmp_path.glob('*.rsc')) == []


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


def test_refresh_update_info_polls_until_settled(dev):
    """RouterOS reports 'checking for updates' asynchronously; we must
    re-read `system package update print` until the status settles."""
    dev.online_update_channel = 'stable'
    checking = [
        '  channel: stable',
        '  status: checking for updates...',
    ]
    settled = [
        '  installed-version: 7.14',
        '  latest-version: 7.15',
        '  status: New version is available',
    ]
    # ssh_call sequence: check-for-updates kick-off, then print (still
    # checking), then print (still checking), then print (settled).
    call_outputs = [[], checking, checking, settled]
    with patch.object(dev, '_get_channel', return_value='stable'):
        with patch.object(
            dev, 'ssh_call', side_effect=call_outputs,
        ) as mock_call:
            with patch('mu.device.time.sleep'):
                dev.refresh_update_info()
    assert dev.update_available is True
    assert dev.installed_version == '7.14'
    assert dev.latest_version == '7.15'
    # first call was check-for-updates, the rest were print reads
    assert mock_call.call_args_list[0] == call(
        'system package update check-for-updates',
    )
    assert all(
        c == call('system package update print')
        for c in mock_call.call_args_list[1:]
    )


def test_refresh_update_info_polling_timeout(dev):
    """If the check never settles within the timeout, we log a warning
    and fall back to the last observed (transient) output."""
    dev.online_update_channel = 'stable'
    checking = [
        '  channel: stable',
        '  status: checking for updates...',
    ]
    with patch.object(dev, '_get_channel', return_value='stable'):
        with patch.object(dev, 'ssh_call', return_value=checking):
            with patch('mu.device.time.sleep'):
                # Advance the monotonic clock past the 30s deadline so
                # the loop exits after a single iteration.
                with patch(
                    'mu.device.default_timer',
                    side_effect=[0, 1000, 1000],
                ):
                    dev.refresh_update_info()
    assert dev.update_available is False
    dev.logger.log.assert_any_call(
        'warning',
        dev.name,
        'check-for-updates did not settle within '
        f'{Device.UPDATE_CHECK_POLL_TIMEOUT}s; '
        'using last known status',
        stdout=True,
    )


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
    with patch.object(dev, 'ssh_call', return_value=['myrouter\r']):
        result = dev._get_identity()
    assert result == 'myrouter'


def test_get_identity_empty_output(dev):
    with patch.object(dev, 'ssh_call', return_value=[]):
        result = dev._get_identity()
    assert result == ''


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
        assert dev._delete_file('myfile.backup') is True
    mock_call.assert_called_with('/file remove "myfile.backup"')


def test_delete_file_reports_error_output(dev):
    with patch.object(dev, 'ssh_call', return_value=['no such item\r']):
        assert dev._delete_file('x.backup') is False


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


def test_log_command_output_empty_output(dev):
    dev._log_command_output('some cmd', [])
    dev.logger.log.assert_called_once_with(
        'info', dev.name, 'some cmd: (no output)',
    )


def test_log_command_output_with_lines(dev):
    dev._log_command_output('some cmd', ['first', '', '  second  '])
    calls = [c.args for c in dev.logger.log.call_args_list]
    assert ('info', dev.name, 'some cmd:') in calls
    assert ('info', dev.name, '  > first') in calls
    assert ('info', dev.name, '  > second') in calls


def test_reboot_logs_device_output(dev):
    with patch.object(dev, 'ssh_call', return_value=['bye']):
        dev._reboot()
    calls = [c.args for c in dev.logger.log.call_args_list]
    assert ('info', dev.name, 'system reboot:') in calls
    assert ('info', dev.name, '  > bye') in calls


def test_set_channel_logs_device_output(dev):
    with patch.object(dev, 'ssh_call', return_value=['ok']):
        dev._set_channel('stable')
    calls = [c.args for c in dev.logger.log.call_args_list]
    assert (
        'info', dev.name, 'system package update set channel=stable:',
    ) in calls
    assert ('info', dev.name, '  > ok') in calls


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


# ─── backup cleanup ──────────────────────────────────────────────────────────

A = 'jan/02/2024 10:00:00|backup|A.backup\r'
B = '2024-02-03 10:00:00|backup|B.backup\r'
C = 'mar/04/2024 10:00:00|backup|C.backup\r'


def _fake(listing, remove=None, free=('129394278\r',)):
    """ssh_call replacement; `remove` maps file name to output lines."""
    removed: list[str] = []

    def fake(cmd):
        if cmd == _LIST_FILES_CMD:
            if isinstance(listing, Exception):
                raise listing
            return list(listing)
        if cmd == _FREE_SPACE_CMD:
            if isinstance(free, Exception):
                raise free
            return list(free)
        assert cmd.startswith('/file remove ')
        name = cmd[len('/file remove "'):-1]
        removed.append(name)
        return (remove or {}).get(name, [])

    fake.removed = removed  # type: ignore[attr-defined]
    return fake


def _cleanup(dev, listing, keep=1, **kw):
    fake = _fake(listing, **kw)
    with patch.object(dev, 'ssh_call', side_effect=fake):
        return dev.cleanup_backups(keep), fake.removed


def test_cleanup_keep_1_2_0(dev):
    assert _cleanup(dev, [C, A, B]) == (
        (True, ['A.backup', 'B.backup']), ['A.backup', 'B.backup'],
    )
    assert _cleanup(dev, [A, B, C], keep=2) == (
        (True, ['A.backup']), ['A.backup'],
    )
    assert _cleanup(dev, [A, B, C], keep=0)[1] == [
        'A.backup', 'B.backup', 'C.backup',
    ]


def test_cleanup_nothing_to_delete(dev):
    assert _cleanup(dev, [A]) == ((True, []), [])
    assert _cleanup(dev, []) == ((True, []), [])
    assert _cleanup(dev, ['jan/02/2024 10:00:00|file|x.rsc\r']) == (
        (True, []), [],
    )


def test_cleanup_only_top_level_backup_files(dev):
    listing = [
        'jan/02/2024 10:00:00|script|x.rsc\r',
        'jan/02/2024 10:00:00|package|y.npk\r',
        'jan/02/2024 10:00:00|backup|z.backup\r',
        'jan/02/2024 10:00:00|backup|flash/q.backup\r',
        'jan/02/2024 10:00:00|directory|d.backup\r',
        '',
    ]
    assert _cleanup(dev, listing, keep=0)[1] == ['z.backup']


def test_cleanup_orders_by_time_then_name(dev):
    listing = [
        'jan/01/2024 10:00:00|backup|z-old.backup\r',
        'feb/01/2024 10:00:00|backup|a-new.backup\r',
    ]
    assert _cleanup(dev, listing)[1] == ['z-old.backup']
    tie = [
        'jan/01/2024 10:00:00|backup|a.backup\r',
        'jan/01/2024 10:00:00|backup|b.backup\r',
    ]
    assert _cleanup(dev, tie)[1] == ['a.backup']


@pytest.mark.parametrize('keep', [-1, 'a', 1.5, True])
def test_cleanup_rejects_bad_keep(dev, keep):
    with patch.object(dev, 'ssh_call') as mock_call:
        with pytest.raises(ValueError):
            dev.cleanup_backups(keep)
    mock_call.assert_not_called()


@pytest.mark.parametrize(
    'listing',
    [
        RuntimeError('boom'),
        ['syntax error (line 1 column 5)'],
        ['garbage|backup|A.backup\r'],
        ['|backup|A.backup\r'],
    ],
)
def test_cleanup_refuses_on_bad_listing(dev, listing):
    result, removed = _cleanup(dev, listing, keep=0)
    assert result == (False, [])
    assert removed == []
    assert dev.logger.log.call_args_list[0].args[0] == 'error'


def test_cleanup_continues_after_failed_delete(dev):
    result, removed = _cleanup(
        dev, [A, B, C], keep=0, remove={'B.backup': ['no such item\r']},
    )
    assert result == (False, ['A.backup', 'C.backup'])
    assert removed == ['A.backup', 'B.backup', 'C.backup']
    dev.logger.log.assert_any_call(
        'error', 'router', 'failed to delete backup B.backup', stdout=True,
    )


def test_cleanup_exception_in_delete_is_failure(dev):
    fake = _fake([A, B])

    def raising(cmd):
        if cmd.startswith('/file remove'):
            raise OSError('lost')
        return fake(cmd)

    with patch.object(dev, 'ssh_call', side_effect=raising):
        assert dev.cleanup_backups(0) == (False, [])


def test_cleanup_logs_each_file_and_summary(dev):
    _cleanup(dev, [A, B, C])
    dev.logger.log.assert_any_call(
        'info', 'router', 'deleted backup A.backup', stdout=True,
    )
    dev.logger.log.assert_any_call(
        'info', 'router', 'backup cleanup: kept 1, deleted 2', stdout=True,
    )


def test_cleanup_dry_run_deletes_nothing(dev):
    fake = _fake([A, B, C])
    with patch.object(dev, 'ssh_call', side_effect=fake):
        result = dev.cleanup_backups(1, dry_run=True)
    assert result == (True, ['A.backup', 'B.backup'])
    assert fake.removed == []
    dev.logger.log.assert_any_call(
        'info', 'router', 'would delete backup A.backup', stdout=True,
    )


def test_ros_quote_escapes_everything_unsafe():
    assert _ros_quote('a b".backup') == '"a\\20b\\22.backup"'
    quoted = _ros_quote('$x[y];\\?.backup')
    assert not any(c in quoted[1:-1] for c in '$[]";?')
    assert _ros_quote('\u00e9') == '"\\C3\\A9"'


def test_cleanup_quotes_odd_names(dev):
    name = 'we ird"$x.backup'
    with patch.object(dev, 'ssh_call', return_value=[]) as mock_call:
        dev._delete_file(name)
    mock_call.assert_called_once_with('/file remove ' + _ros_quote(name))


def test_cleanup_refuses_comma_names(dev):
    comma = 'jan/01/2024 10:00:00|backup|a.rsc,b.backup\r'
    (ok, names), removed = _cleanup(dev, [comma], keep=0)
    assert ok is False
    assert names == []
    assert removed == []


def test_cleanup_dry_run_refuses_comma_names(dev):
    comma = 'jan/01/2024 10:00:00|backup|a.rsc,b.backup\r'
    fake = _fake([comma, C])
    with patch.object(dev, 'ssh_call', side_effect=fake):
        ok, names = dev.cleanup_backups(0, dry_run=True)
    assert ok is False
    assert names == ['C.backup']
    assert fake.removed == []


def test_parse_ros_time():
    assert _parse_ros_time('jan/02/2024 10:00:00').month == 1
    assert _parse_ros_time('2024-02-03 10:00:00').day == 3
    assert _parse_ros_time('nope') is None
    assert _parse_ros_time('') is None


def test_refresh_storage_info(dev):
    with patch.object(dev, 'ssh_call', side_effect=_fake([A, B, C])):
        dev.refresh_storage_info()
    assert dev.backup_count == 3
    assert dev.free_space == 129394278


@pytest.mark.parametrize('free', [RuntimeError('x'), ['bad'], []])
def test_refresh_storage_info_failures_leave_unknown(dev, free):
    dev.backup_count, dev.free_space = 5, 5
    fake = _fake(RuntimeError('x'), free=free)
    with patch.object(dev, 'ssh_call', side_effect=fake):
        dev.refresh_storage_info()
    assert dev.backup_count is None
    assert dev.free_space is None
