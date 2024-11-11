import pathlib
from datetime import datetime


class Logger:
    def __init__(
            self,
            log_dir_str: str = '',
            file_name: str = 'mikrotik_update.log',
    ) -> None:
        if not log_dir_str:
            log_dir = pathlib.Path('.')
        else:
            log_dir = pathlib.Path(log_dir_str)
            log_dir.mkdir(parents=True, exist_ok=True)
        self.log_file = pathlib.Path.joinpath(log_dir, file_name)

    def log(
            self,
            severity: str,
            device: str,
            msg: str,
            stdout: bool = False,
    ) -> None:
        now = datetime.now()
        timestamp = now.strftime('%Y-%m-%d %H:%M:%S')
        log_line = f'{timestamp} - {severity} - {device} - {msg} \n'
        if stdout:
            print(log_line.strip())
        try:
            with open(self.log_file, 'a') as stream:
                stream.write(log_line)
        except PermissionError:
            print(f'Unable to write to {self.log_file}')
            raise SystemExit(1)
