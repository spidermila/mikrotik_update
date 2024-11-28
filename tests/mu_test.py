import subprocess

import pytest


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
            'usage: mu [-h] [-D] [-U | -B] [-d DEVICE_NAME] [-V] ' +
            'configuration_file\nmu: error: the following arguments ' +
            'are required: configuration_file\n',
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
