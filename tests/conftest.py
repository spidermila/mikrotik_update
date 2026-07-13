import pathlib
from unittest.mock import MagicMock

import pytest

from mu.config import Config
from mu.device import Device
from mu.logger import Logger


@pytest.fixture
def mock_conf():
    conf = MagicMock(spec=Config)
    conf.key = None
    conf.reboot_timeout = 10
    conf.backup_dir = pathlib.Path('/tmp/backups')
    conf.delete_backup_after_download = False
    return conf


@pytest.fixture
def disconnected_dev(mock_conf):
    return Device(
        conf=mock_conf,
        name='router',
        address='10.0.0.1',
        port=22,
        username='admin',
        update_type='online',
        logger=MagicMock(spec=Logger),
    )
