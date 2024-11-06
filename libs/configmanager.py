from typing import List

import yaml

from libs.config import Config
from libs.device import Device


class ConfigManager:
    def __init__(self, filename: str) -> None:
        self.filename = filename

    def load_config(self) -> tuple[Config, List[Device]]:
        devices: List[Device] = []
        with open(self.filename) as stream:
            try:
                data = yaml.safe_load(stream)
            except yaml.YAMLError as exc:
                print(exc)
                raise
        gl = data['global']
        cfg = Config(
            backup_dir=gl['backup_dir'],
            private_key_file=gl['private_key_file'],
        )
        cfg.username = gl.get('username')
        cfg.public_key_file = gl.get('public_key_file')
        cfg.public_key_owner = gl.get('public_key_owner')
        cfg.port = gl.get('port')
        cfg.log_dir = gl.get('log_dir')
        cfg.reboot_timeout = gl.get('reboot_timeout')
        cfg.delete_backup_after_download = gl.get(
            'delete_backup_after_download',
        )
        cfg.online_upgrade_channel = gl.get('online_upgrade_channel')
        cfg.upgrade_type = gl.get('upgrade_type')

        devs = data['devices']
        for dev in devs:
            # Use username from device, global or skip device
            if 'username' in dev:
                username = dev['username']
            elif cfg.username:
                username = cfg.username
            else:
                print(
                    'Username not specified for ' +
                    f"device {dev['name']} nor globally!",
                )
                break
            # Use port from device, global or 22
            if 'port' in dev:
                port = dev['port']
            elif cfg.port:
                port = cfg.port
            else:
                port = 22
            # Use online_upgrade_channel from device, global or stable
            if 'online_upgrade_channel' in dev:
                online_upgrade_channel = dev['online_upgrade_channel']
            elif cfg.online_upgrade_channel:
                online_upgrade_channel = cfg.online_upgrade_channel
            else:
                online_upgrade_channel = 'stable'
            # Use upgrade_type from device, global or online
            if 'upgrade_type' in dev:
                upgrade_type = dev['upgrade_type']
            elif cfg.upgrade_type:
                upgrade_type = cfg.upgrade_type
            else:
                upgrade_type = 'online'
            # load packages if manual upgrade type
            if upgrade_type == 'manual':
                packages = dev['packages']
            else:
                packages = []

            # Create new device
            new_device = Device(
                conf=cfg,
                name=dev['name'],
                address=dev['address'],
                port=port,
                username=username,
                upgrade_type=upgrade_type,
                packages=packages,
            )
            new_device.online_upgrade_channel = online_upgrade_channel
            devices.append(new_device)
        return (cfg, devices)

    def check_config_file(self) -> bool:
        mandatory_global_options = ['backup_dir', 'private_key_file']
        mandatory_device_options = ['name', 'address']
        with open(self.filename) as stream:
            try:
                data = yaml.safe_load(stream)
            except yaml.YAMLError as exc:
                print(exc)
                raise
        ok = True
        if 'global' not in data:
            print('Config file missing the "global" section')
            ok = False
        if 'devices' not in data:
            print('Config file missing the "devices" section')
            ok = False
        if ok:
            if not isinstance(data['global'], dict):
                print('global section is not a dict!')
                ok = False
            if not isinstance(data['devices'], list):
                print('devices section is not a list!')
                ok = False
        if ok:
            # check missing mandatory global options
            missing_options = []
            for option in mandatory_global_options:
                if option not in data['global']:
                    missing_options.append(option)
                    ok = False
            if len(missing_options) > 0:
                print('Missing mandatory options:')
                for mo in missing_options:
                    print(mo)
            # check missing mandatory device options
            missing_options = []
            if len(data['devices']) > 0:
                for device in data['devices']:
                    if not isinstance(device, dict):
                        print('Device entry is not dict!')
                        print('entry:')
                        print(device)
                        ok = False
                    else:
                        for option in mandatory_device_options:
                            if option not in device:
                                missing_options.append(option)
                                ok = False
                        if len(missing_options) > 0:
                            print('Missing mandatory device options:')
                            for mo in missing_options:
                                print(mo)
            else:
                print('No devices specified!')
                ok = False
        return ok
