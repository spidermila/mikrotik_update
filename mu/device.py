import re
import time
from datetime import datetime
from pathlib import Path
from timeit import default_timer

import paramiko
from scp import SCPClient  # type: ignore

from mu.config import Config
from mu.logger import Logger
from mu.userregistrator import UserRegistrator
# paramiko.common.logging.basicConfig(level=paramiko.common.DEBUG)


class Device:
    """
    A class representation of a single Mikrotik device.
    Most of the properties are loaded from the configuration file.
    \n
    The class contains methods to communicate with the device,
    fetch information, perform backup and upgrade.
    """
    def __init__(
            self,
            conf: Config,
            name: str,
            address: str,
            port: int,
            username: str,
            upgrade_type: str,
            packages: list[str | None] = [],
    ) -> None:
        self.conf = conf
        self.name = name
        self.address = address
        self.port = port
        self.username = username
        self.upgrade_type = upgrade_type
        self.packages = packages
        self.online_upgrade_channel = 'stable'
        self.client: paramiko.SSHClient | None = None
        self.identity = ''
        self.public_key_file: str | None = None
        self.public_key_owner: str | None = None
        self.installed_version = 'unknown'
        self.latest_version = 'unknown'
        self.version_info_str = f'installed: {self.installed_version}, ' +\
                                f'available: {self.latest_version}'

    def backup(self, logger: Logger) -> bool:
        """
        Perform backup to a file.
        File name format: "identity-yyyymmdd-hhmm.backup" \n
        File name stored to self.backup_file_full_name variable.
        """
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

    def exec_command(self, remote_cmd: str) -> None:
        """
        Execute a command on the device using ssh_call
        and print the output to stdout.
        """
        for line in self.ssh_call(remote_cmd):
            print(line)

    def get_installed_packages(self, logger: Logger) -> list[str]:
        """
        Get the list of installed packages on the device,
        format the information as "packagename version"
        and return it as a list. \n
        example: \n
        ['wireless 7.15beta9', 'routeros 7.15beta9']
        """
        if not self.client:
            print('SSH not connected')
            raise SystemExit(1)
        output = self.ssh_call('system package print')
        if len(output) < 2:
            return []
        result = []
        for line in output:
            if len(line) > 1:
                elements = line.split()
                if elements[0] not in ('#', 'Columns:'):
                    result.append(' '.join(elements[1:3]))
        return result

    def get_update_available(self, logger: Logger) -> bool:
        """
        Runs the self.refresh_update_info() method
        and returns self.update_available property.
        """
        if not self.client:
            print('SSH not connected')
            raise SystemExit(1)
        self.refresh_update_info(logger=logger)
        return self.update_available

    def reboot_and_wait(self, logger: Logger, downgrade=False) -> bool:
        """
        Runs self._downgrade() or self._reboot() depending on the value
        of the "downgrade" parameter. \n
        Then attempts to connect to the device
        using the self.simple_ssh_test() method until the
        self.conf.reboot_timeout runs out.
        """
        if downgrade:
            logger.log(
                        'info',
                        self.name,
                        'rebooting (downgrade)',
                        stdout=True,
            )
        else:
            logger.log(
                        'info',
                        self.name,
                        'rebooting',
                        stdout=True,
            )
        if downgrade:
            self._downgrade()
        else:
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
                return False
            print(
                'waiting for connection. remaining ' +
                f'{remaining} seconds...',
            )
            time.sleep(5)
            if self.simple_ssh_test():
                break
        print('connection works again')
        return True

    def refresh_update_info(self, logger: Logger) -> None:
        """
        Connects to the device using ssh_call,
        sets the desired online upgrade channel
        (self.online_upgrade_channel) and runs the
        "system package update check-for-updates" command.
        Then updates the following properties with the result: \n
        self.update_available (bool - update available)\n
        self.latest_version (str - latest online version available)\n
        self.installed_version (str - installed version)\n
        self.version_info_str (str - printable version summary)\n
        If needed, sets back the original channel.
        """
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

    def simple_ssh_test(self) -> bool:
        """
        Tries to connect to the device using ssh.
        Returns True only if successful.
        """
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

    def ssh_call(self, remote_cmd: str) -> list:
        """
        Executes a command on the device using ssh - self.client.
        Returns the output as a list of lines (strings).
        """
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

    def ssh_close(self) -> None:
        """Close the ssh connection."""
        if self.client:
            self.client.close()
            self.client = None

    def ssh_connect(self) -> None:
        """
        Open a ssh connection to the device using paramiko SSHClient.
        The connection is kept alive and available as "self.client".
        """
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

    def ssh_test(self) -> bool:
        """
        A comprehensive SSH test which should be run before any other
        connection attempts. Intended to verify the configuration
        and connectivity. Returns True only when successful.
        """
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

    def upgrade(self, logger: Logger) -> None:
        """Wrapper method to trigger both online and manual upgrades."""
        if not self.client:
            print('SSH not connected')
            raise SystemExit(1)

        # online upgrade from Internet and reboot
        if self.upgrade_type == 'online':
            logger.log(
                severity='info',
                device=self.name,
                msg='online upgrade',
                stdout=True,
            )
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

        # Manual upgrade - will upload packages to device and reboot it
        if self.upgrade_type == 'manual':
            logger.log(
                severity='info',
                device=self.name,
                msg='manual upgrade',
                stdout=True,
            )
            installed = self.get_installed_packages(logger=logger)
            logger.log(
                severity='info',
                device=self.name,
                msg=f'installed packages {installed}',
                stdout=True,
            )
            self._manual_upgrade(logger=logger)

    def version_is_lower(self, ver_a: str, ver_b: str) -> bool:
        """
        A helper method which takes two RouterOS version strings, parses them
        and checks if the first version is lower than the second version. \n
        Testing versions are compared as follows: \n
        "alpha" < "beta" < %number%
        """
        a_split = ver_a.split('.')
        b_split = ver_b.split('.')
        assert a_split[0].isnumeric()
        assert b_split[0].isnumeric()
        if a_split[0] < b_split[0]:
            return True
        elif a_split[0] > b_split[0]:
            return False
        if any(char.isalpha() for char in a_split[1]):
            a_subversions = re.findall(r'\d+', a_split[1])
            if 'alpha' in a_split[1]:
                extra = '-2'
            elif 'beta' in a_split[1]:
                extra = '-1'
            else:
                extra = '0'
            a_subversions.insert(1, extra)
        else:
            a_subversions = a_split[1:]
            if len(a_subversions) == 1:
                a_subversions.append('0')
        if any(char.isalpha() for char in b_split[1]):
            b_subversions = re.findall(r'\d+', b_split[1])
            if 'alpha' in b_split[1]:
                extra = '-2'
            elif 'beta' in b_split[1]:
                extra = '-1'
            else:
                extra = '0'
            b_subversions.insert(1, extra)
        else:
            b_subversions = b_split[1:]
            if len(b_subversions) == 1:
                b_subversions.append('0')
        if a_subversions[0] < b_subversions[0]:
            return True
        elif a_subversions[0] > b_subversions[0]:
            return False
        if a_subversions[1] < b_subversions[1]:
            return True
        elif a_subversions[1] > b_subversions[1]:
            return False
        if len(a_subversions) > 2 and len(b_subversions) > 2:
            if a_subversions[2] < b_subversions[2]:
                return True
            elif a_subversions[2] > b_subversions[2]:
                return False
        return False

    def _delete_file(self, filename: str) -> None:
        """Delete file on the device using ssh_call."""
        if not self.client:
            print('SSH not connected')
            raise SystemExit(1)
        _ = self.ssh_call(f'file remove {filename}')

    def _downgrade(self) -> None:
        """
        Reboot the device using the system "package downgrade"
        command over ssh_call.
        """
        if not self.client:
            print('SSH not connected')
            raise SystemExit(1)
        _ = self.ssh_call('system package downgrade\ny')

    def _download_update(self) -> bool:
        """
        Run the "system package update download" command on the device
        and check the result. Returns True when the message is
        "Downloaded, please reboot".
        """
        if not self.client:
            print('SSH not connected')
            raise SystemExit(1)
        output = self.ssh_call('system package update download')
        for line in output:
            if 'status:' in line:
                if 'Downloaded, please reboot' in line:
                    return True
        return False

    def _online_upgrade(self, logger: Logger) -> None:
        """
        Perform online upgrade or prints 'update not available'.\n
        First downloads the package using self._download_update().
        Then reboots using self.reboot_and_wait().
        """
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
                    'download successful',
                    stdout=True,
                )
                if not self.reboot_and_wait(logger):
                    return
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

    def _get_identity(self) -> str:
        """Get the device identity using ssh_call."""
        if not self.client:
            print('SSH not connected')
            raise SystemExit(1)
        output = self.ssh_call('system identity print')
        return output[0].split()[1]

    def _get_channel(self) -> str:
        """Get the active channel from the device using ssh_call."""
        if not self.client:
            print('SSH not connected')
            raise SystemExit(1)
        output = self.ssh_call('system package update print')
        for line in output:
            if 'channel' in line:
                return line.split()[1]
        return ''

    def _manual_upgrade(self, logger: Logger) -> None:
        """Perform manual upgrade using packages from the local system."""
        if len(self.packages) == 0:
            logger.log(
                'error',
                self.name,
                'manual upgrade selected but no packages provided',
                stdout=True,
            )
            return
        do_downgrade = False
        for package in self.packages:
            assert isinstance(package, str)
            package_path = Path(package)
            if not package_path.is_file():
                logger.log(
                    'error',
                    self.name,
                    f'{package_path} does not exist',
                    stdout=True,
                )
                return
            # check if the installed package is newer
            # than the desired package
            # if yes, the /system package downgrade needs to be
            # executed instead of the /system reboot
            package_version = package_path.name.split('-')[1]
            package_name = package_path.name.split('-')[0]
            if not do_downgrade:
                for p in self.get_installed_packages(logger):
                    if p.split()[0] == package_name:
                        if self.version_is_lower(
                            package_version,
                            p.split()[1],
                        ):
                            do_downgrade = True
            logger.log(
                'info',
                self.name,
                f'uploading {package_path} to device',
                stdout=True,
            )
            # upload the package to the device
            if not self._upload_package(package_path, logger):
                logger.log(
                    'error',
                    self.name,
                    f'failed to upload {package_path} to device',
                    stdout=True,
                )
                return
        # run backup
        if not self.backup(logger=logger):
            return
        if not self.reboot_and_wait(logger, downgrade=do_downgrade):
            return
        self.ssh_connect()
        self.refresh_update_info(logger=logger)
        logger.log(
            'info',
            self.name,
            self.version_info_str,
            stdout=True,
        )

    def _reboot(self) -> None:
        """Execute system reboot using ssh_call."""
        if not self.client:
            print('SSH not connected')
            raise SystemExit(1)
        _ = self.ssh_call('system reboot\ny')

    def _set_channel(self, logger: Logger, channel: str) -> None:
        """Set channel on the device using ssh_call."""
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

    def _upload_package(self, package_path: Path, logger: Logger) -> bool:
        """Take a path to a file, upload the file to the device using scp."""
        if not self.client:
            print('SSH not connected')
            raise SystemExit(1)
        try:
            with SCPClient(self.client.get_transport()) as scp:
                # upload to / (RAM), use /flash to upload to persistent memory
                scp.put(package_path, '/')
        except Exception as e:
            logger.log(
                'error',
                self.name,
                f'{e}',
                stdout=True,
            )
            return False
        return True
