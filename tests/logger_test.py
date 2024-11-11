import pathlib
from datetime import datetime
from unittest.mock import mock_open
from unittest.mock import patch

import pytest

from mu.logger import Logger


@pytest.fixture(scope='session')
def tmpdir_path(tmpdir_factory):
    return tmpdir_factory.mktemp('test')


@pytest.fixture(scope='session')
def mock_logger():
    return Logger()


def test_logger_init(tmpdir_path):
    with patch('pathlib.Path.mkdir') as mock_mkdir:
        logger = Logger(log_dir_str=str(tmpdir_path))
        assert logger.log_file == pathlib.PosixPath(
            tmpdir_path.join('mikrotik_update.log'),
        )
        mock_mkdir.assert_called_once_with(parents=True, exist_ok=True)


def test_logger_init_no_log_dir(mock_logger):
    assert mock_logger.log_file == pathlib.PosixPath('mikrotik_update.log')


def test_logger_log_to_file(tmpdir_path):
    now = datetime.now()
    timestamp = now.strftime('%Y-%m-%d %H:%M:%S')
    with patch('builtins.open', mock_open()) as mock_file:
        with patch('datetime.datetime') as mock_datetime:
            mock_datetime.now.return_value = timestamp
            logger = Logger(str(tmpdir_path))
            logger.log('INFO', 'device1', 'Test message')
            mock_file().write.assert_called_once_with(
                f'{timestamp} - INFO - device1 - Test message \n',
            )


def test_logger_log_to_stdout(tmpdir_path, capsys):
    now = datetime.now()
    timestamp = now.strftime('%Y-%m-%d %H:%M:%S')
    with patch('builtins.open', mock_open()):
        with patch('datetime.datetime') as mock_datetime:
            mock_datetime.now.return_value = timestamp
            logger = Logger(tmpdir_path)
            logger.log('INFO', 'device1', 'Test message', stdout=True)
            captured = capsys.readouterr()
            assert captured.out.strip() == \
                f'{timestamp} - INFO - device1 - Test message'


def test_logger_permission_error(capsys):
    with patch('builtins.open', mock_open()) as mock_file:
        mock_file.side_effect = PermissionError
        logger = Logger(file_name='test.log')
        with pytest.raises(SystemExit):
            logger.log('ERROR', 'device1', 'Test message')
        captured = capsys.readouterr()
        assert 'Unable to write to test.log' in captured.out
