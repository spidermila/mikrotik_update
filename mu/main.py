import argparse
import configparser
import importlib.metadata
import os
from collections.abc import Sequence

from mu.configmanager import ConfigManager

try:
    VERSION_STR = importlib.metadata.version('mu')
except importlib.metadata.PackageNotFoundError:
    _config = configparser.ConfigParser()
    _config.read(os.path.join(os.path.dirname(__file__), '..', 'setup.cfg'))
    VERSION_STR = _config['metadata']['version']


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        add_help=False,
        prog='mu',
    )
    parser.add_argument(
        '-h',
        '--help',
        action='help',
        default=argparse.SUPPRESS,
        help='Show this help',
    )
    parser.add_argument(
        'configuration_file',
        help='Configuration file in yaml format',
    )
    parser.add_argument(
        '-D',
        '--dry-run',
        '--check-only',
        help='Only check the updates. Do not perform backup and update.',
        action='store_true',
    )
    single_action_group = parser.add_mutually_exclusive_group()
    single_action_group.add_argument(
        '-U',
        '--update-only',
        help='Only perform update.',
        action='store_true',
    )
    single_action_group.add_argument(
        '-B',
        '--backup-only',
        help='Only perform backup and download the backup file.',
        action='store_true',
    )
    parser.add_argument(
        '-d',
        dest='device_name',
        help='Specify device name(s) as per your configuration file.' +
        ' Can be used multiple times to specify multiple devices.',
        action='append',
    )
    parser.add_argument(
        '-V',
        '--version',
        help='Display the program version',
        action='version',
        version=f'%(prog)s version {VERSION_STR}',
    )
    args = parser.parse_args()
    configuration_file = args.configuration_file
    if not os.path.isfile(configuration_file):
        print(f'File {args.configuration_file} doesn\'t exist!')
        return 1
    cm = ConfigManager(configuration_file)
    if not cm.check_config_file():
        return 1
    devices, logger = cm.load_config()
    if args.dry_run:
        logger.log('info', 'script', '=======DRYRUN started=======')
    else:
        logger.log('info', 'script', '=======script started=======')
    if args.device_name:
        devices_in_scope = []
        for device_name in args.device_name:
            found = False
            for device in devices:
                if device.name == device_name:
                    devices_in_scope.append(device)
                    found = True
                    continue
            if not found:
                print(f'Device {device_name} not found in configuration file!')
                return 1
        devices = devices_in_scope
    for d in devices:
        if d.ssh_test():
            d.ssh_connect()
            if args.dry_run:
                if d.update_type == 'manual':
                    installed = d.get_installed_packages()
                    logger.log(
                        'info',
                        d.name,
                        'manual update. installed packages: ' +
                        f'{installed}, packages to update: {d.packages}',
                        stdout=True,
                    )
                else:
                    d.refresh_update_info()
                    logger.log(
                        'info',
                        d.name,
                        d.version_info_str,
                        stdout=True,
                    )
            else:
                if args.backup_only:
                    d.backup()
                else:
                    if d.get_update_available():
                        if args.update_only:
                            d.update()
                        else:
                            d.backup()
                            d.update()
                    else:
                        logger.log(
                            'info',
                            d.name,
                            'No updates available.',
                            stdout=True,
                        )

            d.ssh_close()
        else:
            print(f"Can't connect to {d.name}")
    logger.log('info', 'script', '======script completed======')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
