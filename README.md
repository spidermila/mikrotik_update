[![pre-commit.ci status](https://results.pre-commit.ci/badge/github/spidermila/mikrotik_update/main.svg)](https://results.pre-commit.ci/latest/github/spidermila/mikrotik_update/main)

# mikrotik_update
A command line tool which automates the RouterOS update on a fleet of Mikrotik devices.
The tool will first perform a backup of the device and download
it to a local directory. The update is performed only if
the backup and download are successful.

The above default behaviour can be overriden by the -U or -B options.

The tool uses **ssh key** to authenticate with the Mikrotik device.
You need to generate the ssh key pair before using this tool.
I expect there will be a dedicated user created for this purpose.
The tool can set up this user and upload the public key for you.

If the ssh authentication fails, the tool will prompt for a user
and password of an existing user and attempt to create the script user.
It will also upload an existing public key to the device and associate
it to the script user.

## How to install as a package
I recommend to use virtualenv or venv.
```bash
pip install .
```

Once the package is installed, run it:

```bash
mu sample.yaml
```

## How to use the python script as a module
I recommend to use virtualenv or venv and install the prerequisites there.
The script shall be used as a python module with the `-m` option.

Prerequisites:
```bash
python3 -m pip install -r requirements.txt
```

Usage:
```bash
python -m mu sample.yaml
```

## Options
```
-V, --version         Show version
-h, --help            Help
-D, --dry-run         Only check configuration and test connectivity to devices
                      without performing the backup and update.
-U, --update-only     Only perform update.
-B, --backup-only     Only perform backup and download the backup file.
-d DEVICE_NAME        Specify device name(s) as per your configuration file.
                      Can be used multiple times to specify multiple devices.
                      If no device specified, all devices will be used.
```

## Example yaml file
```yaml
global: # global settings
    log_dir: /home/test_user/mikrotik_update # local dicrectory where log file will be stored
    backup_dir: /home/test_user/mikrotik_update/backups # local directory where backup files will be stored
    username: update_user # script user on the Mikrotik device
    private_key_file: /home/test_user/.ssh/id_ed25519 # private key which will be used for authentication
    public_key_file: /home/test_user/.ssh/id_ed25519.pub # public key which will be uploaded to the device, if needed
    public_key_owner: test_user@homePC # this string will be stored on the device along with the key
    port: 22 # ssh port of the devices
    delete_backup_after_download: False # delete the backup file on the Mikrotik device once it's downloaded to backup_dir
    online_update_channel: stable # [stable, testing, development, long term]
    reboot_timeout: 200 # seconds, 240 is default
devices: # your fleet of Mikrotik devices
    -   name: main_router # mandatory, mainly for logging
        address: 192.168.1.1 # mandatory
        port: 22 # optional if specified globally
        username: main_router_update_user # optional
        update_type: online # optional, default is online, [online, manual]
        online_update_channel: stable # optional, stable is default, [stable, testing, development, long term]
    -   name: ap1
        address: 192.168.1.2
        port: 23 # setting this on the device level has a higher priority over the global settings
    -   name: minimal_example_device # global and default settings will be applied for this one
        address: 192.168.1.3
    -   name: ap2
        address: 192.168.1.4
        update_type: manual
        packages:
            - /home/test_user/mikrotik_update/packages/routeros-7.15beta9-mipsbe.npk
            - /home/test_user/mikrotik_update/packages/wireless-7.15beta9-mipsbe.npk
    -   name: ap3
        address: 192.168.1.5
        update_type: manual
        packages:
            - /home/test_user/mikrotik_update/packages/wireless-7.14.1-mipsbe.npk
            - /home/test_user/mikrotik_update/packages/routeros-7.14.1-mipsbe.npk
```

## Screen wrapper
I am running the `mu` script on my server to which I am connected via a pair of Mikrotik devices.
I got annoyed when I got disconnected from the ssh session while the `mu` script was running.
So, I have created this simple wrapper which runs the `mu` for me in `screen`. Now I can get disconnected,
the updates keep running, and I can return to them when the connection is restored.

All arguments of the `mu_screen` are passed to `mu`.
```bash
mu_screen --dry-run sample.yaml
```
