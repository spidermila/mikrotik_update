[![pre-commit.ci status](https://results.pre-commit.ci/badge/github/spidermila/mikrotik_upgrade/main.svg)](https://results.pre-commit.ci/latest/github/spidermila/mikrotik_upgrade/main)

# mikrotik_upgrade
A command line tool to simplify update of a fleet of Mikrotik devices.
The script will first perform a backup of the device and download
it to a local directory. The upgrade is performed only if
the backup and download are successful.

The script uses **ssh key** to authenticate with the Mikrotik device. 
You need to generate the ssh key pair before using this program.
I expect there will be a dedicated user created for this purpose.
The script can set up this user and upload the public key for you.

If the ssh authentication fails, the script will prompt for a user
and password of an existing user and attempt to create the script user.
It will also upload an existing public key to the device and associate
it to the script user.

## How to use the compiled binary file
The released versions contain compiled executable files for Linux and Windows which can be used directly.
```bash
./mu sample.yaml
```
or
```bash
mu.exe sample.yaml
```

## How to use the python script
I recommend to use virtualenv or venv and install the prerequisites there.

Prerequisites:
```bash
python3 -m pip install -r requirements.txt
```

Usage:
```bash
python mu.py sample.yaml
```

Options:
```
-V --version     Show version
-h --help        Help
-D --dry-run     Only check configuration and test connectivity to devices without performing the upgrade
```

## Example yaml file
```yaml
global: # global settings
    log_dir: /home/test_user/mikrotik_upgrade # local dicrectory where log file will be stored
    backup_dir: /home/test_user/mikrotik_upgrade/backups # local directory where backup files will be stored
    username: upgrade_user # script user on the Mikrotik device
    private_key_file: /home/test_user/.ssh/id_ed25519 # private key which will be used for authentication
    public_key_file: /home/test_user/.ssh/id_ed25519.pub # public key which will be uploaded to the device, if needed
    public_key_owner: test_user@homePC # this string will be stored on the device along with the key
    port: 22 # ssh port of the devices
    delete_backup_after_download: False # delete the backup file on the Mikrotik device once it's downloaded to backup_dir
    online_upgrade_channel: stable # [stable, testing, development, long term]
    reboot_timeout: 200 # seconds, 240 is default
devices: # your fleet of Mikrotik devices
    -   name: main_router # mandatory, mainly for logging
        address: 192.168.1.1 # mandatory
        port: 22 # optional if specified globally
        username: main_router_upgrade_user # optional
        upgrade_type: online # optional, default is online, [online, manual]
        online_upgrade_channel: stable # optional, stable is default, [stable, testing, development, long term]
    -   name: ap1
        address: 192.168.1.2
        port: 23 # setting this on the device level has a higher priority over the global settings
    -   name: minimal_example_device # global and default settings will be applied for this one
        address: 192.168.1.3
    -   name: ap2
        address: 192.168.1.4
        upgrade_type: manual
        packages:
            - /home/test_user/mikrotik_upgrade/packages/routeros-7.15beta9-mipsbe.npk
            - /home/test_user/mikrotik_upgrade/packages/wireless-7.15beta9-mipsbe.npk
    -   name: ap3
        address: 192.168.1.5
        upgrade_type: manual
        packages:
            - /home/test_user/mikrotik_upgrade/packages/wireless-7.14.1-mipsbe.npk
            - /home/test_user/mikrotik_upgrade/packages/routeros-7.14.1-mipsbe.npk
```

The tool will backup the configuration, download the backup file and upgrade the device.
