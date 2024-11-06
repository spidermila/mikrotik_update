import subprocess

import pytest


@pytest.mark.parametrize(
    'stdout, arg, expected_output', [
        (True, '--help', 'Show this help'),
        (True, '--version', 'Mikrotik Upgrade version'),
        (
            True,
            'non_existing_file.yaml',
            "File non_existing_file.yaml doesn't exist!\n",
        ),
        (
            False,
            '--dry-run',
            'usage: Mikrotik Upgrade [-h] [-D] [-V] configuration_file\n' +
            'Mikrotik Upgrade: error: the following arguments are required: ' +
            'configuration_file\n',
        ),
    ],
)
def test_mu_parameters(stdout, arg, expected_output):
    result = subprocess.run(
        ['python3', 'mu.py'] + arg.split(),
        capture_output=True,
        text=True,
    )
    if stdout:
        assert expected_output in result.stdout
    else:
        assert result.stderr == expected_output
