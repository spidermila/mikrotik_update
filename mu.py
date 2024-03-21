from libs.config import Config
from libs.device import Device


def main() -> int:
    conf = Config(
        username='zerver_script',
        key_file='/home/milan/.ssh/id_ed25519',
    )
    d = Device(conf, 'router', '192.168.111.111', 22)
    if d.ssh_test():
        d.ssh_connect()
        d.exec_command('user print')
        d.ssh_close()
    else:
        print(f"Can't connect to {d.name}")
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
