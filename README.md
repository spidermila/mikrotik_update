[![pre-commit.ci status](https://results.pre-commit.ci/badge/github/spidermila/mikrotik_upgrade/main.svg)](https://results.pre-commit.ci/latest/github/spidermila/mikrotik_upgrade/main)

# mikrotik_upgrade
A command line tool to simplify update of a fleet of Mikrotik devices.
The script uses ssh key to authenticate with the Mikrotik device.
I expect there will be a dedicated user created for this purpose.
The script can set up this user and upload the public key for you.

If the ssh authentication fails, the script will prompt for a user
and password of an existing user and attempt to create the script user.
It will also upload an existing public key to the device and associate
it to the script user. Next time you run the script, it should
authenticate with the device and perform the upgrade.

I recommend to use virtualenv or venv and install the prerequisites there.

Prerequisites:
```bash
python3 -m pip install -r requirements.txt
```

Usage:
```bash
python mu.py sample.yaml
```


```yaml
global: # global settings
    log_dir: /home/test_user/mikrotik # local dicrectory where log file will be stored
    backup_dir: /home/test_user/mikrotik/backups # local directory where backup files will be stored
    username: upgrade_user # script user on the Mikrotik device
    private_key_file: /home/test_user/.ssh/id_ed25519 # private key which will be used for authentication
    public_key_file: /home/test_user/.ssh/id_ed25519.pub # public key which will be uploaded to the device, if needed
    public_key_owner: test_user@homePC # this string will be stored on the device along with the key
    port: 22 # ssh port of the device
    delete_backup_after_download: False # delete the backup file on the Mikrotik device once it's downloaded to backup_dir
    online_upgrade_channel: stable # [stable, testing, development, long term]
    reboot_timeout: 200 # seconds, 240 is default
devices: # your fleet of Mikrotik devices
    -   name: main_router # mandatory, mainly for logging
        address: 192.168.1.1 # mandatory
        port: 22 # optional if specified globally
        username: main_router_upgrade_user # optional
        upgrade_type: online # optional, default is online, manual upgrade not yet implemented
        online_upgrade_channel: stable # optional, stable is default, [stable, testing, development, long term]
    -   name: ap1
        address: 192.168.1.2
        port: 23 # setting this on the device level has a higher priority over the global settings
    -   name: minimal_example_device # global and default settings will be applied for this one
        address: 192.168.1.3
```

The tool will backup the configuration, download the backup file and upgrade the device.
