import subprocess
from datetime import datetime

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
        self.client: paramiko.SSHClient | None = None
        self.identity = ''
        self.public_key_file: str | None = None
        self.public_key_owner: str | None = None

    def test_connection(self) -> list[bool]:
        result = [False, False]
        if self._ping_test():
            result[0] = True
            if self.ssh_test():
                result[1] = True
        return result

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
            paramiko.SSHException,
        ) as err:
            print(f'ssh err on {self.name}: {err}')
            print('-' * 20)
            print(f'The user {self.username} might not exist on {self.name}')
            print('Do you want to log in and create the user? (yY/nN)')
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
                    UserRegistrator(
                        dev_name=self.name,
                        dev_address=self.address,
                        dev_port=self.port,
                        username=self.username,
                        public_key_file=public_key_file,
                        public_key_owner=public_key_owner,
                    )
                    break
                else:
                    break

            raise SystemExit(1)
        else:
            # remote_cmd = 'interface print terse'
            # stdin, stdout, stderr = ssh.exec_command(remote_cmd)
            # for line in stdout.readlines():
            #     print(line.strip('\n'))
            # print((
            #   "Options available to deal with the "
            #   f"connectios are many like\n{dir(ssh)}"
            # ))
            ssh.close()
            return True

    def _ping_test(self) -> bool:
        result = subprocess.run(
            [
                'ping',
                '-c1',
                self.address,
            ],
            shell=False,
            stdin=None,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
        )
        if result.returncode != 0:
            print('-'*20)
            print(f'Error when pinging {self.name}')
            print('stdout:')
            print(f"{result.stdout.decode('utf-8')}")
            print('stderr:')
            print(f"{result.stderr.decode('utf-8')}")
            print('-'*20)
            return False
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
            print(f'ssh err on {self.name}: {err}')
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
        return output

    def exec_command(self, remote_cmd: str) -> None:
        for line in self.ssh_call(remote_cmd):
            print(line)

    def _get_identity(self) -> str:
        if not self.client:
            print('SSH not connected')
            raise SystemExit(1)
        output = self.ssh_call('system identity print')
        return output[0].split()[1]

    def _delete_file(self, filename: str) -> None:
        if not self.client:
            print('SSH not connected')
            raise SystemExit(1)
        _ = self.ssh_call(f'file remove {filename}')

    def backup(self, logger: Logger) -> None:
        # create backup
        if not self.client:
            print('SSH not connected')
            raise SystemExit(1)
        now = datetime.now()
        timestamp = now.strftime('%Y%m%d-%H%M')
        backup_file_name = f'{self.identity}-{timestamp}'
        self.backup_file_full_name = backup_file_name + '.backup'
        logger.log(f'running backup to file {self.backup_file_full_name}')
        output = self.ssh_call(f'system backup save name={backup_file_name}')
        if 'Configuration backup saved\r' not in output:
            print(output)
            logger.log(f'Backup failed: {output}')
            return
        else:
            print(f'Backup saved to {self.backup_file_full_name}')
        # download backup
        logger.log(f'downloading backup file to {self.conf.backup_dir}')
        try:
            with SCPClient(self.client.get_transport()) as scp:
                scp.get(self.backup_file_full_name, self.conf.backup_dir)
        except Exception as e:
            logger.log(f'{e}')
            raise
        print(f'Backup downloaded to {self.conf.backup_dir}')
        if self.conf.delete_backup_after_download:
            print('Deleting backup on device.')
            logger.log('deleting backup on device')
            self._delete_file(self.backup_file_full_name)
