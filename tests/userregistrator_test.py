import pathlib
from unittest.mock import MagicMock
from unittest.mock import patch

import paramiko
import pytest

from mu.userregistrator import UserRegistrator


@pytest.fixture
def ur():
    return UserRegistrator(
        dev_name='testrouter',
        dev_address='10.0.0.1',
        dev_port=22,
        username='scriptuser',
        public_key_file='tests/data/test_key.pub',
        public_key_owner='owner',
    )


@pytest.fixture
def connected_ur(ur):
    ur.client = MagicMock()
    return ur


# ─── __init__ ────────────────────────────────────────────────────────────────

def test_init_basic():
    ur = UserRegistrator(
        dev_name='r',
        dev_address='10.0.0.1',
        dev_port=22,
        username='admin',
    )
    assert ur.dev_name == 'r'
    assert ur.dev_address == '10.0.0.1'
    assert ur.dev_port == 22
    assert ur.username == 'admin'
    assert ur.public_key_file is None
    assert ur.public_key_owner is None
    assert ur.client is None


def test_init_with_public_key_file():
    ur = UserRegistrator(
        dev_name='r',
        dev_address='10.0.0.1',
        dev_port=22,
        username='admin',
        public_key_file='mykey.pub',
    )
    assert isinstance(ur.public_key_file, pathlib.Path)
    assert str(ur.public_key_file) == 'mykey.pub'


def test_init_with_public_key_owner():
    ur = UserRegistrator(
        dev_name='r',
        dev_address='10.0.0.1',
        dev_port=22,
        username='admin',
        public_key_owner='alice',
    )
    assert ur.public_key_owner == 'alice'


def test_init_public_key_file_non_string():
    ur = UserRegistrator(
        dev_name='r',
        dev_address='10.0.0.1',
        dev_port=22,
        username='admin',
        public_key_file=None,
        public_key_owner=None,
    )
    assert ur.public_key_file is None
    assert ur.public_key_owner is None


# ─── ssh_connect ─────────────────────────────────────────────────────────────

def test_ssh_connect_success(ur):
    ur._admin_user = 'admin'
    ur._admin_pwd = 'password'
    with patch('paramiko.SSHClient') as mock_ssh_class:
        mock_client = MagicMock()
        mock_ssh_class.return_value = mock_client
        ur.ssh_connect()
    assert ur.client is mock_client
    mock_client.connect.assert_called_once()


def test_ssh_connect_auth_failure(ur):
    ur._admin_user = 'admin'
    ur._admin_pwd = 'wrongpassword'
    with patch('paramiko.SSHClient') as mock_ssh_class:
        mock_client = MagicMock()
        mock_ssh_class.return_value = mock_client
        mock_client.connect.side_effect = (
            paramiko.AuthenticationException('fail')
        )
        with pytest.raises(paramiko.AuthenticationException):
            ur.ssh_connect()


# ─── ssh_close ───────────────────────────────────────────────────────────────

def test_ssh_close_with_client(connected_ur):
    saved_client = connected_ur.client
    connected_ur.ssh_close()
    saved_client.close.assert_called_once()
    assert connected_ur.client is None


def test_ssh_close_no_client(ur):
    ur.client = None
    ur.ssh_close()  # should not raise


# ─── check_key_file ──────────────────────────────────────────────────────────

def test_check_key_file_no_public_key_file(ur):
    ur.public_key_file = None
    ur.client = MagicMock()
    result = ur.check_key_file()
    assert result is False


def test_check_key_file_no_client(ur):
    ur.client = None
    result = ur.check_key_file()
    assert result is False


def test_check_key_file_found(connected_ur):
    connected_ur.public_key_file = pathlib.Path('mykey.pub')
    mock_stdout = MagicMock()
    mock_stdout.readlines.return_value = [
        '0  mykey.pub  500\n',
    ]
    connected_ur.client.exec_command.return_value = (
        MagicMock(), mock_stdout, MagicMock(),
    )
    result = connected_ur.check_key_file()
    assert result is True


def test_check_key_file_not_found(connected_ur):
    connected_ur.public_key_file = pathlib.Path('mykey.pub')
    mock_stdout = MagicMock()
    mock_stdout.readlines.return_value = [
        '0  otherkey.pub  500\n',
    ]
    connected_ur.client.exec_command.return_value = (
        MagicMock(), mock_stdout, MagicMock(),
    )
    result = connected_ur.check_key_file()
    assert result is False


def test_check_key_file_exception(connected_ur):
    connected_ur.public_key_file = pathlib.Path('mykey.pub')
    connected_ur.client.exec_command.side_effect = Exception('fail')
    with pytest.raises(Exception):
        connected_ur.check_key_file()


def test_check_key_file_short_line(connected_ur):
    connected_ur.public_key_file = pathlib.Path('mykey.pub')
    mock_stdout = MagicMock()
    # Lines with <= 2 words are skipped
    mock_stdout.readlines.return_value = ['short\n']
    connected_ur.client.exec_command.return_value = (
        MagicMock(), mock_stdout, MagicMock(),
    )
    result = connected_ur.check_key_file()
    assert result is False


# ─── user_exists ─────────────────────────────────────────────────────────────

def test_user_exists_no_client(ur):
    ur.client = None
    result = ur.user_exists()
    assert result is False


def test_user_exists_found(connected_ur):
    connected_ur.username = 'scriptuser'
    mock_stdout = MagicMock()
    mock_stdout.readlines.return_value = [
        '0  scriptuser  full\n',
    ]
    connected_ur.client.exec_command.return_value = (
        MagicMock(), mock_stdout, MagicMock(),
    )
    result = connected_ur.user_exists()
    assert result is True


def test_user_exists_not_found(connected_ur):
    connected_ur.username = 'scriptuser'
    mock_stdout = MagicMock()
    mock_stdout.readlines.return_value = [
        '0  otheruser  full\n',
    ]
    connected_ur.client.exec_command.return_value = (
        MagicMock(), mock_stdout, MagicMock(),
    )
    result = connected_ur.user_exists()
    assert result is False


def test_user_exists_exception(connected_ur):
    connected_ur.client.exec_command.side_effect = Exception('fail')
    with pytest.raises(Exception):
        connected_ur.user_exists()


def test_user_exists_short_line(connected_ur):
    connected_ur.username = 'scriptuser'
    mock_stdout = MagicMock()
    mock_stdout.readlines.return_value = ['short\n']
    connected_ur.client.exec_command.return_value = (
        MagicMock(), mock_stdout, MagicMock(),
    )
    result = connected_ur.user_exists()
    assert result is False


# ─── register_user ───────────────────────────────────────────────────────────

def test_register_user_no_client(ur):
    ur.client = None
    ur.register_user()  # should return without error


def test_register_user_success(connected_ur):
    mock_stdout = MagicMock()
    mock_stdout.readlines.return_value = []
    connected_ur.client.exec_command.return_value = (
        MagicMock(), mock_stdout, MagicMock(),
    )
    with patch.object(connected_ur, 'user_exists', return_value=True):
        connected_ur.register_user()


def test_register_user_group_not_exist(connected_ur, capsys):
    mock_stdout = MagicMock()
    mock_stdout.readlines.return_value = [
        'input does not match any value of group\n',
    ]
    connected_ur.client.exec_command.return_value = (
        MagicMock(), mock_stdout, MagicMock(),
    )
    with patch.object(connected_ur, 'user_exists', return_value=False):
        connected_ur.register_user()
    captured = capsys.readouterr()
    assert "Group full doesn't exist" in captured.out


def test_register_user_not_created(connected_ur):
    mock_stdout = MagicMock()
    mock_stdout.readlines.return_value = []
    connected_ur.client.exec_command.return_value = (
        MagicMock(), mock_stdout, MagicMock(),
    )
    with patch.object(connected_ur, 'user_exists', return_value=False):
        connected_ur.register_user()


def test_register_user_exec_exception(connected_ur):
    connected_ur.client.exec_command.side_effect = Exception('fail')
    with pytest.raises(Exception):
        connected_ur.register_user()


# ─── upload_key_file ─────────────────────────────────────────────────────────

def test_upload_key_file_no_client(ur):
    ur.client = None
    ur.upload_key_file()  # should return without error


def test_upload_key_file_success(connected_ur):
    connected_ur.public_key_file = pathlib.Path('mykey.pub')
    with patch('mu.userregistrator.SCPClient') as mock_scp_class:
        mock_scp = MagicMock()
        mock_scp_class.return_value.__enter__ = MagicMock(
            return_value=mock_scp,
        )
        mock_scp_class.return_value.__exit__ = MagicMock(return_value=False)
        connected_ur.upload_key_file()
    mock_scp.put.assert_called_once_with(pathlib.Path('mykey.pub'))


# ─── add_key_to_user ─────────────────────────────────────────────────────────

def test_add_key_to_user_no_client(ur):
    ur.client = None
    ur.add_key_to_user()  # should return without error


def test_add_key_to_user_no_public_key_file(connected_ur):
    connected_ur.public_key_file = None
    connected_ur.add_key_to_user()  # should return without error


def test_add_key_to_user_success(connected_ur):
    connected_ur.public_key_file = pathlib.Path('mykey.pub')
    connected_ur.public_key_owner = 'owner'
    mock_stdout = MagicMock()
    mock_stdout.readlines.return_value = []
    connected_ur.client.exec_command.return_value = (
        MagicMock(), mock_stdout, MagicMock(),
    )
    connected_ur.add_key_to_user()
    connected_ur.client.exec_command.assert_called_once()


def test_add_key_to_user_group_not_exist(connected_ur, capsys):
    connected_ur.public_key_file = pathlib.Path('mykey.pub')
    connected_ur.public_key_owner = 'owner'
    mock_stdout = MagicMock()
    mock_stdout.readlines.return_value = [
        'input does not match any value of group\n',
    ]
    connected_ur.client.exec_command.return_value = (
        MagicMock(), mock_stdout, MagicMock(),
    )
    connected_ur.add_key_to_user()
    captured = capsys.readouterr()
    assert "Group full doesn't exist" in captured.out


def test_add_key_to_user_exception(connected_ur):
    connected_ur.public_key_file = pathlib.Path('mykey.pub')
    connected_ur.public_key_owner = 'owner'
    connected_ur.client.exec_command.side_effect = Exception('fail')
    with pytest.raises(Exception):
        connected_ur.add_key_to_user()


# ─── run ─────────────────────────────────────────────────────────────────────

def test_run_user_exists_key_file_present(ur):
    with patch('builtins.input', return_value='admin'):
        with patch('getpass.getpass', return_value='password'):
            with patch.object(ur, 'ssh_connect'):
                with patch.object(ur, 'user_exists', return_value=True):
                    with patch.object(ur, 'check_key_file', return_value=True):
                        with patch.object(ur, 'add_key_to_user'):
                            with patch.object(ur, 'ssh_close'):
                                with patch('time.sleep'):
                                    result = ur.run()
    assert result is True


def test_run_user_not_exists_key_upload_success(ur):
    with patch('builtins.input', return_value='admin'):
        with patch('getpass.getpass', return_value='password'):
            with patch.object(ur, 'ssh_connect'):
                with patch.object(ur, 'user_exists', return_value=False):
                    with patch.object(ur, 'register_user'):
                        with patch.object(
                            ur, 'check_key_file',
                            side_effect=[False, True],
                        ):
                            with patch.object(ur, 'upload_key_file'):
                                with patch.object(ur, 'add_key_to_user'):
                                    with patch.object(ur, 'ssh_close'):
                                        with patch('time.sleep'):
                                            result = ur.run()
    assert result is True


def test_run_upload_fails(ur):
    with patch('builtins.input', return_value='admin'):
        with patch('getpass.getpass', return_value='password'):
            with patch.object(ur, 'ssh_connect'):
                with patch.object(ur, 'user_exists', return_value=True):
                    with patch.object(
                        ur, 'check_key_file',
                        side_effect=[False, False],
                    ):
                        with patch.object(ur, 'upload_key_file'):
                            with patch('time.sleep'):
                                result = ur.run()
    assert result is False


def test_run_no_public_key_file_prompts(ur):
    ur.public_key_file = None
    ur.public_key_owner = None
    inputs = iter(['admin', 'mykey.pub', 'alice'])
    with patch('builtins.input', side_effect=inputs):
        with patch('getpass.getpass', return_value='password'):
            with patch.object(ur, 'ssh_connect'):
                with patch.object(ur, 'user_exists', return_value=True):
                    with patch.object(ur, 'check_key_file', return_value=True):
                        with patch.object(ur, 'add_key_to_user'):
                            with patch.object(ur, 'ssh_close'):
                                with patch('time.sleep'):
                                    result = ur.run()
    assert result is True
