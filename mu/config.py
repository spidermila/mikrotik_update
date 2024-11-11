import pathlib

import paramiko


class Config:
    def __init__(
            self,
            backup_dir: str = '',
            private_key_file: str = '',
    ) -> None:
        self.username = ''
        self.public_key_file: str | None = None
        self.public_key_owner: str | None = None
        self.port: int | None = None
        self.log_dir: str = ''
        self.delete_backup_after_download = False
        self.upgrade_type = 'online'
        self.online_upgrade_channel = 'stable'
        self.reboot_timeout = 240
        self.backup_dir = pathlib.Path(backup_dir)
        self.private_key_file = private_key_file
        if len(self.private_key_file) > 0:
            self.key = paramiko.Ed25519Key.from_private_key_file(
                self.private_key_file,
            )
