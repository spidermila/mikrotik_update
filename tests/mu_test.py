import subprocess
from unittest.mock import MagicMock
from unittest.mock import patch

import pytest

from mu.main import main


@pytest.mark.parametrize(
    'stdout, arg, expected_output', [
        (True, '--help', 'Show this help'),
        (True, '--version', 'mu version'),
        (
            True,
            'non_existing_file.yaml',
            "File non_existing_file.yaml doesn't exist!\n",
        ),
        (
            False,
            '--dry-run',
            'usage: mu [-h] [-D] [-U | -B | -C] [-k N] [-d DEVICE_NAME] ' +
            '[-V]\n          configuration_file\nmu: error: the following ' +
            'arguments are required: configuration_file\n',
        ),
    ],
)
def test_mu_parameters(stdout, arg, expected_output):
    result = subprocess.run(
        ['python3', '-m', 'mu'] + arg.split(),
        capture_output=True,
        text=True,
    )
    if stdout:
        assert expected_output in result.stdout
    else:
        assert result.stderr == expected_output


def _run_main(argv, devices):
    logger = MagicMock()
    with patch('mu.main.os.path.isfile', return_value=True):
        with patch('mu.main.ConfigManager') as cm:
            cm.return_value.check_config_file.return_value = True
            cm.return_value.load_config.return_value = (devices, logger)
            rc = main(argv)
    return rc, logger


def _cleanup_device(name):
    d = MagicMock()
    d.name = name
    d.ssh_test.return_value = True
    d.cleanup_backups.return_value = (True, [])
    return d


def test_cleanup_runs_on_all_devices_only():
    d1, d2 = _cleanup_device('r1'), _cleanup_device('r2')
    rc, _ = _run_main(['c.yaml', '-C'], [d1, d2])
    assert rc == 0
    for d in (d1, d2):
        d.cleanup_backups.assert_called_once_with(1, dry_run=False)
        d.backup.assert_not_called()
        d.update.assert_not_called()
        d.get_update_available.assert_not_called()
        d.firmware_update.assert_not_called()


def test_cleanup_keep_and_device_selection():
    d1, d2 = _cleanup_device('r1'), _cleanup_device('r2')
    _run_main(['c.yaml', '-C', '-k', '3', '-d', 'r1'], [d1, d2])
    d1.cleanup_backups.assert_called_once_with(3, dry_run=False)
    d2.cleanup_backups.assert_not_called()


def test_cleanup_dry_run_passed_through():
    d1 = _cleanup_device('r1')
    _run_main(['c.yaml', '-C', '-D'], [d1])
    d1.cleanup_backups.assert_called_once_with(1, dry_run=True)


@pytest.mark.parametrize(
    'extra',
    [['-k', '-1'], ['-k', 'x'], ['-C', '-U'], ['-C', '-B']],
)
def test_cleanup_bad_args_exit_2_without_config(extra):
    with patch('mu.main.ConfigManager') as cm:
        with pytest.raises(SystemExit) as e:
            main(['c.yaml'] + extra)
    assert e.value.code == 2
    cm.assert_not_called()


def test_no_cleanup_without_flag():
    d1 = _cleanup_device('r1')
    d1.get_update_available.return_value = False
    d1.update_firmware = False
    _run_main(['c.yaml'], [d1])
    d1.cleanup_backups.assert_not_called()


def test_cleanup_failure_logged_and_next_device_processed():
    d1, d2 = _cleanup_device('r1'), _cleanup_device('r2')
    d1.cleanup_backups.return_value = (False, [])
    rc, logger = _run_main(['c.yaml', '-C'], [d1, d2])
    assert rc == 0
    logger.log.assert_any_call(
        'error', 'r1', 'backup cleanup failed', stdout=True,
    )
    d2.cleanup_backups.assert_called_once()


def test_help_lists_cleanup_options():
    result = subprocess.run(
        ['python3', '-m', 'mu', '--help'], capture_output=True, text=True,
    )
    assert '--cleanup-backups' in result.stdout
    assert '--keep-backups' in result.stdout
    assert 'default: 1' in result.stdout
