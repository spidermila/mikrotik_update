[![pre-commit.ci status](https://results.pre-commit.ci/badge/github/spidermila/mikrotik_upgrade/main.svg)](https://results.pre-commit.ci/latest/github/spidermila/mikrotik_upgrade/main)

# mikrotik_upgrade
A command line tool to simplify update of a fleet of Mikrotik devices.
Work in progress.
The tool will backup the configuration, download the backup file, upgrade the device.
Configuration (including list of devices to upgrade) is taken from a yaml file passed as a parameter.
