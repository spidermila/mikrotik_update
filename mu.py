import argparse
import os

from libs.configmanager import ConfigManager


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
        print(f'File {args.soubor} doesn\'t exist!')
        return 1
    cm = ConfigManager(configuration_file)
    if not cm.check_config_file():
        return 1
    _, devices = cm.load_config()

    for d in devices:
        if d.ssh_test():
            d.ssh_connect()
            d.exec_command('user print')
            d.ssh_close()
        else:
            print(f"Can't connect to {d.name}")
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
