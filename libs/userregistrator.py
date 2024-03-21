import getpass
import pathlib
from time import sleep

import paramiko
from scp import SCPClient  # type: ignore


class UserRegistrator:
    def __init__(
            self,
            dev_name: str,
            dev_address: str,
            dev_port: int,
            username: str,
            *args,
            **kwargs,
    ) -> None:
        self.dev_name = dev_name
        self.dev_address = dev_address
        self.dev_port = dev_port
        self.username = username
        self.client: paramiko.SSHClient | None = None

        # kwargs
        self.public_key_file: pathlib.Path | None = None
        if 'public_key_file' in kwargs:
            _public_key_file = kwargs['public_key_file']
            if isinstance(_public_key_file, str):
                self.public_key_file = pathlib.Path(_public_key_file)

        self.public_key_owner: str | None = None
        if 'public_key_owner' in kwargs:
            print('key owner found')
            _public_key_owner = kwargs['public_key_owner']
            if isinstance(_public_key_owner, str):
                self.public_key_owner = _public_key_owner

        print('Enter a valid user name to log in.')
        self._admin_user = input('> ')
        self._admin_pwd = getpass.getpass()
        self.ssh_connect()
        print('Connecting...')
        if self.user_exists():
            print(f'User {self.username} exists.')
        else:
            self.register_user()

        if not self.public_key_file:
            print(
                'Full path to the public key ' +
                f'file to upload to {self.dev_name}',
            )
            self.public_key_file = pathlib.Path(input('> '))

        if not self.public_key_owner:
            print('Key owner')
            self.public_key_owner = input('> ')

        if not self.check_key_file():
            print(f'Key not present on {self.dev_name}. Uploading...')
            self.upload_key_file()
        sleep(1)
        if not self.check_key_file():
            print('Upload failed.')
            return
        print('Uploaded successfully.')
        self.add_key_to_user()
        print('Done.')

    def ssh_connect(self) -> None:
        self.client = paramiko.SSHClient()
        self.client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        try:
            self.client.connect(
                hostname=self.dev_address,
                port=self.dev_port,
                username=self._admin_user,
                password=self._admin_pwd,
                look_for_keys=False,
            )
        except paramiko.AuthenticationException as err:
            print(f'ssh err on {self.dev_name}: {err}')
            raise

    def upload_key_file(self) -> None:
        if not self.client:
            return
        with SCPClient(self.client.get_transport()) as scp:
            scp.put(self.public_key_file)

    def check_key_file(self) -> bool:
        if not self.public_key_file:
            return False
        if not self.client:
            return False
        _cmd = 'file print'
        try:
            stdin, stdout, stderr = self.client.exec_command(_cmd)
            for line in stdout.readlines():
                if len(line.split()) > 2:
                    if self.public_key_file.name == line.split()[1]:
                        return True
        except Exception as e:
            print(e)
            raise
        return False

    def user_exists(self) -> bool:
        if not self.client:
            return False
        _cmd = 'user print'
        try:
            stdin, stdout, stderr = self.client.exec_command(_cmd)
            for line in stdout.readlines():
                if len(line.split()) > 2:
                    if self.username == line.split()[1]:
                        return True
        except Exception as e:
            print(e)
            raise
        return False

    def register_user(self) -> None:
        if not self.client:
            return
        print(f'Attempting to create user {self.username} in group full')
        import string
        import random
        _randpwd = ''.join(
            random.choice(
                string.ascii_letters+string.digits,
            ) for _ in range(12)
        )
        _cmd = f'user add name={self.username} password={_randpwd} group=full'
        try:
            stdin, stdout, stderr = self.client.exec_command(_cmd)
            for line in stdout.readlines():
                _msg = 'input does not match any value of group'
                if _msg in line:
                    print(f"Group full doesn't exist on {self.dev_name}")
        except Exception as e:
            print(e)
            raise
        if self.user_exists():
            print(f'User {self.username} created.')
        else:
            return

    def add_key_to_user(self) -> None:
        if (
            not self.client or
            not isinstance(self.public_key_file, pathlib.Path)
        ):
            return
        print('Adding key to user...')
        _cmd = f'user ssh-keys import user={self.username} ' \
            f'public-key-file={self.public_key_file.name} ' \
            f'key-owner={self.public_key_owner}'
        try:
            stdin, stdout, stderr = self.client.exec_command(_cmd)
            for line in stdout.readlines():
                _msg = 'input does not match any value of group'
                if _msg in line:
                    print(f"Group full doesn't exist on {self.dev_name}")
        except Exception as e:
            print(e)
            raise
