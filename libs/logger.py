import pathlib
from datetime import datetime


class Logger:
    def __init__(
            self,
            log_dir: str | None,
            file_name: str = 'mikrotik_update.log',
    ) -> None:
        if not log_dir:
            log_dir = '.'
        self.log_file = pathlib.Path(log_dir) / file_name

    def log(self, msg: str) -> None:
        now = datetime.now()
        timestamp = now.strftime('%Y-%m-%d %H:%M:%S')
        log_line = f'{timestamp} - {msg} \n'
        try:
            with open(self.log_file, 'a') as stream:
                stream.write(log_line)
        except PermissionError:
            print(f'Unable to write to {self.log_file}')
            raise SystemExit(1)
