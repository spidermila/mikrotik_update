import argparse
import os

from libs.configmanager import ConfigManager
from libs.logger import Logger


def main() -> int:
    parser = argparse.ArgumentParser(add_help=False)
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
    args = parser.parse_args()
    configuration_file = args.configuration_file
    if not os.path.isfile(configuration_file):
        print(f'File {args.configuration_file} doesn\'t exist!')
        return 1
    cm = ConfigManager(configuration_file)
    if not cm.check_config_file():
        return 1
    config, devices = cm.load_config()
    logger = Logger(config.log_dir)
    if args.dry_run:
        logger.log('info', 'script', '=======DRYRUN started=======')
    else:
        logger.log('info', 'script', '=======script started=======')
    for d in devices:
        if d.ssh_test():
            d.ssh_connect()
            if args.dry_run:
                d.refresh_update_info(logger=logger)
                logger.log(
                    'info',
                    d.name,
                    d.version_info_str,
                    stdout=True,
                )
            else:
                d.upgrade(logger=logger)
            d.ssh_close()
        else:
            print(f"Can't connect to {d.name}")
    logger.log('info', 'script', '======script completed======')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
