import time
from datetime import datetime
from timeit import default_timer

import paramiko
from scp import SCPClient  # type: ignore

from libs.config import Config
from libs.logger import Logger
from libs.userregistrator import UserRegistrator
# paramiko.common.logging.basicConfig(level=paramiko.common.DEBUG)


class Device:
    def __init__(
            self,
            conf: Config,
            name: str,
            address: str,
            port: int,
            username: str,
            upgrade_type: str,
    ) -> None:
        self.conf = conf
        self.name = name
        self.address = address
        self.port = port
        self.username = username
        self.upgrade_type = upgrade_type
        self.online_upgrade_channel = 'stable'
        self.client: paramiko.SSHClient | None = None
        self.identity = ''
        self.public_key_file: str | None = None
        self.public_key_owner: str | None = None
        self.installed_version = 'unknown'
        self.latest_version = 'unknown'
        self.version_info_str = f'installed: {self.installed_version}, ' +\
                                f'available: {self.latest_version}'

    def simple_ssh_test(self) -> bool:
        ssh = paramiko.SSHClient()
        ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        try:
            if self.conf.key:
                ssh.connect(
                    hostname=self.address,
                    port=self.port,
                    username=self.username,
                    pkey=self.conf.key,
                    look_for_keys=False,
                )
            else:
                ssh.connect(
                    hostname=self.address,
                    port=self.port,
                    username=self.username,
                    look_for_keys=True,
                )
        except Exception:
            return False
        return True

    def ssh_test(self) -> bool:
        ssh = paramiko.SSHClient()
        ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())

        try:
            if self.conf.key:
                ssh.connect(
                    hostname=self.address,
                    port=self.port,
                    username=self.username,
                    pkey=self.conf.key,
                    look_for_keys=False,
                )
            else:
                ssh.connect(
                    hostname=self.address,
                    port=self.port,
                    username=self.username,
                    look_for_keys=True,
                )
        except (
            paramiko.AuthenticationException,
        ) as err:
            print(f'ssh err on {self.name}: {err}')
            print('-' * 20)
            print(
                f'The user {self.username} might not exist ' +
                f'or ssh key is missing on {self.name}.',
            )
            print('Should the script log in and try to fix this? (yY/nN)')
            public_key_file: str | None
            if self.public_key_file:
                public_key_file = self.public_key_file
            else:
                public_key_file = self.conf.public_key_file

            public_key_owner: str | None
            if self.public_key_owner:
                public_key_owner = self.public_key_owner
            else:
                public_key_owner = self.conf.public_key_owner

            while True:
                answer = input('> ')
                if answer.lower() == 'y':
                    ur = UserRegistrator(
                        dev_name=self.name,
                        dev_address=self.address,
                        dev_port=self.port,
                        username=self.username,
                        public_key_file=public_key_file,
                        public_key_owner=public_key_owner,
                    )
                    return ur.run()
                else:
                    break

            raise SystemExit(1)
        except OSError as e:
            print(f'{e}')
            return False
        else:
            ssh.close()
            return True

    def ssh_connect(self) -> None:
        self.client = paramiko.SSHClient()
        self.client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        try:
            if self.conf.key:
                self.client.connect(
                    hostname=self.address,
                    port=self.port,
                    username=self.username,
                    pkey=self.conf.key,
                    look_for_keys=False,
                )
            else:
                self.client.connect(
                    hostname=self.address,
                    port=self.port,
                    username=self.username,
                    look_for_keys=True,
                )
            self.identity = self._get_identity()
        except paramiko.AuthenticationException as err:
            print(f'SSH err on {self.name}: {err}')
            raise

    def ssh_close(self) -> None:
        if self.client:
            self.client.close()
            self.client = None

    def ssh_call(self, remote_cmd: str) -> list:
        if not self.client:
            print('SSH not connected')
            raise SystemExit(1)
        output = []
        try:
            stdin, stdout, stderr = self.client.exec_command(remote_cmd)
            for line in stdout.readlines():
                output.append(line.strip('\n'))
            return output
        except Exception as e:
            print(e)
            raise

    def exec_command(self, remote_cmd: str) -> None:
        for line in self.ssh_call(remote_cmd):
            print(line)

    def _get_identity(self) -> str:
        if not self.client:
            print('SSH not connected')
            raise SystemExit(1)
        output = self.ssh_call('system identity print')
        return output[0].split()[1]

    def _get_channel(self) -> str:
        if not self.client:
            print('SSH not connected')
            raise SystemExit(1)
        output = self.ssh_call('system package update print')
        for line in output:
            if 'channel' in line:
                return line.split()[1]
        return ''

    def refresh_update_info(self, logger: Logger) -> None:
        if not self.client:
            print('SSH not connected')
            raise SystemExit(1)
        # set desired channel
        set_back_channel = False
        original_channel = self._get_channel()
        if original_channel != self.online_upgrade_channel:
            self._set_channel(logger, self.online_upgrade_channel)
            set_back_channel = True
        output = self.ssh_call('system package update check-for-updates')
        for line in output:
            if 'installed-version' in line:
                self.installed_version = line.split()[1]
                self.version_info_str = \
                    f'installed: {self.installed_version}, ' +\
                    f'available: {self.latest_version}'
            if 'latest-version' in line:
                self.latest_version = line.split()[1]
                self.version_info_str = \
                    f'installed: {self.installed_version}, ' +\
                    f'available: {self.latest_version}'
            if 'status:' in line:
                if 'New version is available' in line:
                    self.update_available = True
                    if set_back_channel:
                        self._set_channel(logger, original_channel)
                    return
                if 'Downloaded, please reboot' in line:
                    logger.log(
                        'warning',
                        self.name,
                        'update already downloaded. reboot manually',
                        stdout=True,
                    )
        self.update_available = False
        if set_back_channel:
            self._set_channel(logger, original_channel)

    def _download_update(self) -> bool:
        if not self.client:
            print('SSH not connected')
            raise SystemExit(1)
        output = self.ssh_call('system package update download')
        for line in output:
            if 'status:' in line:
                if 'Downloaded, please reboot' in line:
                    return True
        return False

    def _set_channel(self, logger: Logger, channel: str) -> None:
        if not self.client:
            print('SSH not connected')
            raise SystemExit(1)
        output = self.ssh_call(f'system package update set channel={channel}')
        if 'syntax error' in output:
            logger.log(
                'error',
                self.name,
                f'syntax error when setting channel {channel}',
                stdout=True,
            )

    def _delete_file(self, filename: str) -> None:
        if not self.client:
            print('SSH not connected')
            raise SystemExit(1)
        _ = self.ssh_call(f'file remove {filename}')

    def _reboot(self) -> None:
        if not self.client:
            print('SSH not connected')
            raise SystemExit(1)
        _ = self.ssh_call('system reboot\ny')

    def backup(self, logger: Logger) -> bool:
        # create backup
        if not self.client:
            print('SSH not connected')
            raise SystemExit(1)
        now = datetime.now()
        timestamp = now.strftime('%Y%m%d-%H%M')
        backup_file_name = f'{self.identity}-{timestamp}'
        self.backup_file_full_name = backup_file_name + '.backup'
        logger.log(
            'info',
            self.name,
            f'running backup to file {self.backup_file_full_name}',
        )
        output = self.ssh_call(f'system backup save name={backup_file_name}')
        if 'Configuration backup saved\r' not in output:
            print(output)
            logger.log(
                'error',
                self.name,
                f'backup failed: {output}',
            )
            return False
        else:
            logger.log(
                'info',
                self.name,
                f'backup saved to {self.backup_file_full_name}',
                stdout=True,
            )
        # download backup
        self.conf.backup_dir.mkdir(parents=True, exist_ok=True)
        logger.log(
            'info',
            self.name,
            f'downloading backup file to {self.conf.backup_dir}',
        )
        try:
            with SCPClient(self.client.get_transport()) as scp:
                scp.get(self.backup_file_full_name, self.conf.backup_dir)
        except Exception as e:
            logger.log(
                'error',
                self.name,
                f'{e}',
                stdout=True,
            )
            return False
        logger.log(
            'info',
            self.name,
            f'backup downloaded to {self.conf.backup_dir}',
            stdout=True,
        )
        if self.conf.delete_backup_after_download:
            logger.log(
                'info',
                self.name,
                'deleting backup on device',
                stdout=True,
            )
            self._delete_file(self.backup_file_full_name)
        return True

    def get_update_available(self, logger: Logger) -> bool:
        if not self.client:
            print('SSH not connected')
            raise SystemExit(1)
        self.refresh_update_info(logger=logger)
        return self.update_available

    def upgrade(self, logger: Logger) -> None:
        if not self.client:
            print('SSH not connected')
            raise SystemExit(1)
        if self.upgrade_type == 'online':
            # check channel
            if self._get_channel() != self.online_upgrade_channel:
                print(
                    'setting desired online update channel' +
                    f' {self.online_upgrade_channel}',
                )
                logger.log(
                    'info',
                    self.name,
                    'setting desired online update channel' +
                    f' {self.online_upgrade_channel}',
                    stdout=True,
                )
                # set channel
                self._set_channel(logger, self.online_upgrade_channel)
                time.sleep(1)
            # check update
            self.refresh_update_info(logger=logger)
            self._online_upgrade(logger=logger)

    def _online_upgrade(self, logger: Logger) -> None:
        if self.update_available:
            logger.log(
                'info',
                self.name,
                self.version_info_str,
                stdout=True,
            )
            # run backup
            if not self.backup(logger=logger):
                return
            logger.log(
                'info',
                self.name,
                'downloading update',
                stdout=True,
            )
            if self._download_update():
                logger.log(
                    'info',
                    self.name,
                    'download successful. rebooting',
                    stdout=True,
                )
                self._reboot()
                timer_start = round(default_timer())
                while True:
                    timer_current = round(default_timer())
                    timer_elapsed = timer_current - timer_start
                    remaining = self.conf.reboot_timeout - timer_elapsed
                    if remaining <= 0:
                        logger.log(
                            'warning',
                            self.name,
                            'timed out waiting for device after reboot',
                            stdout=True,
                        )
                        return
                    print(
                        'waiting for connection. remaining ' +
                        f'{remaining} seconds...',
                    )
                    time.sleep(5)
                    if self.simple_ssh_test():
                        break
                print('connection works again')
                self.ssh_connect()
                self.refresh_update_info(logger=logger)
                logger.log(
                    'info',
                    self.name,
                    self.version_info_str,
                    stdout=True,
                )
            else:
                logger.log(
                    'error',
                    self.name,
                    'download not successful',
                    stdout=True,
                )
        else:
            logger.log(
                'info',
                self.name,
                'update not available',
                stdout=True,
            )
