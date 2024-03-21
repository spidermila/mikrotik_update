import paramiko


class Config:
    def __init__(
            self,
            username: str,
            backup_dir: str = '',
            key_file: str = '',
    ) -> None:
        self.username = username
        self.backup_dir = backup_dir
        self.key_file = key_file
        self.key: paramiko.Ed25519Key | None = None
        if len(self.key_file) > 0:
            self.key = paramiko.Ed25519Key.from_private_key_file(self.key_file)
