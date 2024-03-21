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
        help='show this help',
    )
    parser.add_argument(
        'configuration_file',
        help='configuration file in yaml format',
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
    logger.log('info', 'script', '=======script started=======')
    for d in devices:
        if d.ssh_test():
            # TODO: continue after userregistrator completes successfully
            d.ssh_connect()
            d.upgrade(logger=logger)
            # print(d.name, d.identity, d.upgrade_type)
            # d.exec_command('user print')
            d.ssh_close()
        else:
            print(f"Can't connect to {d.name}")
    logger.log('info', 'script', '======script completed======')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
