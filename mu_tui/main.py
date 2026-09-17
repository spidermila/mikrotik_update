"""
mu_tui — curses-based interactive TUI for the mu (mikrotik_update) tool.

Screens:
  1. YAML file selection (from a directory)
  2. Devices list with multi-select, live per-device job status and
     bulk actions (refresh, backup, update, firmware, reboot)
  3. Device detail with per-device actions (channel, backup, update)
  4. Jobs list  (press ``j`` from any screen)
  5. Job log viewer

SSH work runs in background threads. Each job captures its own stdout and
mu Logger output into a scrollable buffer viewable from the Jobs screen.
The main TUI thread never blocks on SSH.
"""
from __future__ import annotations

import argparse
import curses
import os
import sys
import threading
import time
import traceback
from datetime import datetime
from pathlib import Path
from typing import Callable

from mu.configmanager import ConfigManager
from mu.device import Device
from mu.logger import Logger


CHANNELS = ['stable', 'testing', 'development', 'long-term']

# Keys that navigate back to the previous menu level.
_BACK_KEYS = (
    ord('b'), ord('B'), 27,
    curses.KEY_BACKSPACE, 127, 8,
)

# Status markers shared by the device list, job list and status lines.
_MARKERS = {'queued': '…', 'running': '▶', 'done': '✓', 'error': '✗'}

# Set by each job thread so writes get routed into that job's buffer.
_current_job = threading.local()


class _JobStream:
    """sys.stdout/stderr replacement that routes writes to the current job.

    If no job is bound to the current thread, writes are dropped rather than
    reaching the real terminal (which would corrupt the curses display).
    """

    def __init__(self) -> None:
        self._buffers: dict[int, str] = {}

    def write(self, data: str) -> int:
        if not data:
            return 0
        job = getattr(_current_job, 'job', None)
        if job is None:
            return len(data)
        tid = threading.get_ident()
        buf = self._buffers.get(tid, '') + data
        *complete, tail = buf.split('\n')
        for line in complete:
            job.write(line)
        self._buffers[tid] = tail
        return len(data)

    def flush(self) -> None:
        job = getattr(_current_job, 'job', None)
        tid = threading.get_ident()
        # pop, not get: dead threads should not accumulate buffers.
        tail = self._buffers.pop(tid, '')
        if tail and job is not None:
            job.write(tail)

    def isatty(self) -> bool:
        return False


# ---------- job infrastructure ----------

class Job:
    """Background unit of work with a captured output buffer."""

    def __init__(self, name: str, device: str | None = None) -> None:
        self.name = name
        self.device = device
        self.lines: list[str] = []
        self.lock = threading.Lock()
        self.status = 'running'      # queued | running | done | error
        self.started = time.time()
        self.finished: float | None = None
        self.error: str | None = None

    def write(self, line: str) -> None:
        ts = datetime.now().strftime('%H:%M:%S')
        with self.lock:
            for sub in str(line).splitlines() or ['']:
                self.lines.append(f'{ts} {sub}')

    def snapshot(self) -> list[str]:
        with self.lock:
            return list(self.lines)

    def duration(self) -> float:
        end = self.finished if self.finished is not None else time.time()
        return end - self.started


class JobManager:
    def __init__(self) -> None:
        self.jobs: list[Job] = []
        self.lock = threading.Lock()

    def submit(
        self, name: str, target: Callable[[Job], None],
        device: str | None = None,
    ) -> Job:
        job = Job(name, device)
        with self.lock:
            self.jobs.append(job)

        def runner() -> None:
            _current_job.job = job
            job.write(f'=== {name} ===')
            try:
                target(job)
                job.status = 'done'
                job.write('=== finished ===')
            # Device raises SystemExit on SSH failures; it must mark the
            # job failed instead of silently ending the thread.
            except (Exception, SystemExit) as e:
                job.status = 'error'
                job.error = str(e) or type(e).__name__
                job.write(f'ERROR: {e}')
                job.write(traceback.format_exc())
            finally:
                # Flush any trailing partial line the job left in the
                # _JobStream buffer, otherwise it would be lost when
                # this thread exits.
                try:
                    sys.stdout.flush()
                    sys.stderr.flush()
                except Exception:
                    pass
                job.finished = time.time()
                _current_job.job = None

        threading.Thread(target=runner, daemon=True).start()
        return job

    def running_count(self) -> int:
        with self.lock:
            return sum(
                1 for j in self.jobs if j.status in ('queued', 'running')
            )

    def all(self) -> list[Job]:
        with self.lock:
            return list(self.jobs)

    def latest_for(self, device: str) -> Job | None:
        with self.lock:
            for j in reversed(self.jobs):
                if j.device == device:
                    return j
        return None

    def clear_finished(self) -> None:
        with self.lock:
            self.jobs = [
                j for j in self.jobs if j.status in ('queued', 'running')
            ]


_original_log: Callable | None = None
_original_stdout = None
_original_stderr = None


def _install_output_taps() -> None:
    """Route mu logger + bare print() calls into the current job's buffer.

    Idempotent: calling this more than once is a no-op.
    """
    global _original_log, _original_stdout, _original_stderr
    if _original_log is not None:
        return
    _original_log = Logger.log
    original_log = _original_log

    def wrapped(
        self, severity: str, device: str, msg: str, stdout: bool = False,
    ) -> None:
        # Never print to real stdout — it would corrupt the curses display.
        original_log(self, severity, device, msg, stdout=False)
        job = getattr(_current_job, 'job', None)
        if job is not None:
            job.write(f'[{severity}] {device}: {msg}')

    Logger.log = wrapped  # type: ignore[method-assign]

    _original_stdout = sys.stdout
    _original_stderr = sys.stderr
    sys.stdout = _JobStream()
    sys.stderr = _JobStream()


def _uninstall_output_taps() -> None:
    """Undo _install_output_taps. Safe to call when nothing was installed."""
    global _original_log, _original_stdout, _original_stderr
    if _original_log is None:
        return
    Logger.log = _original_log  # type: ignore[method-assign]
    sys.stdout = _original_stdout
    sys.stderr = _original_stderr
    _original_log = None
    _original_stdout = None
    _original_stderr = None


# ---------- TUI state ----------

class TuiState:
    def __init__(self, start_dir: str) -> None:
        self.start_dir = start_dir
        self.yaml_path: str | None = None
        self.devices: list[Device] = []
        self.logger: Logger | None = None
        self.info_fetched: dict[str, bool] = {}
        self.jobs = JobManager()
        # Per-device lock so concurrent jobs don't share an SSH client.
        self.device_locks: dict[str, threading.Lock] = {}

    def lock_for(self, device: Device) -> threading.Lock:
        lock = self.device_locks.get(device.name)
        if lock is None:
            lock = threading.Lock()
            self.device_locks[device.name] = lock
        return lock


# ---------- helpers ----------

def list_yaml_files(directory: str) -> list[str]:
    p = Path(directory)
    files = []
    try:
        for f in sorted(p.iterdir()):
            if f.is_file() and f.suffix in ('.yaml', '.yml'):
                files.append(str(f))
    except OSError:
        pass
    return files


def clip(s: str, n: int) -> str:
    if n <= 0:
        return ''
    return s if len(s) <= n else s[: max(0, n - 1)] + '…'


def safe_addstr(win, y: int, x: int, s: str, attr: int = 0) -> None:
    try:
        win.addstr(y, x, s, attr)
    except curses.error:
        pass


def draw_header(
    stdscr, title: str, help_line: str, state: TuiState,
) -> None:
    h, w = stdscr.getmaxyx()
    if w < 2 or h < 1:
        return
    running = state.jobs.running_count()
    total = len(state.jobs.all())
    badge = f' jobs: {running}▶ / {total} '
    left = title[: max(0, w - len(badge) - 1)]
    line = (left + ' ' * max(0, w - 1 - len(left) - len(badge)) + badge)
    safe_addstr(stdscr, 0, 0, line[: w - 1], curses.A_REVERSE)
    if h >= 2:
        hint = help_line + '  |  j=jobs'
        safe_addstr(stdscr, h - 1, 0, hint[: w - 1], curses.A_DIM)


def _make_popup(stdscr, box_w: int, box_h: int):
    """Create a centered curses popup window with border + keypad."""
    h, w = stdscr.getmaxyx()
    box_w = min(w - 2, box_w)
    box_h = min(h - 2, box_h)
    y = max(0, (h - box_h) // 2)
    x = max(0, (w - box_w) // 2)
    win = curses.newwin(box_h, box_w, y, x)
    win.keypad(True)
    win.nodelay(False)
    win.border()
    return win, box_w, box_h


def popup_message(stdscr, msg: str) -> None:
    lines = msg.split('\n')
    want_w = max(30, max(len(line) for line in lines) + 4)
    want_h = len(lines) + 4
    win, box_w, box_h = _make_popup(stdscr, want_w, want_h)
    for i, line in enumerate(lines):
        if i + 2 >= box_h - 1:
            break
        safe_addstr(win, 1 + i, 2, line[: box_w - 4])
    prompt = '[any key]'
    safe_addstr(
        win, box_h - 2, box_w - len(prompt) - 2, prompt, curses.A_DIM,
    )
    win.refresh()
    win.getch()


def popup_confirm(stdscr, msg: str) -> bool:
    win, box_w, _ = _make_popup(stdscr, max(40, len(msg) + 6), 5)
    safe_addstr(win, 1, 2, msg[: box_w - 4])
    safe_addstr(win, 3, 2, ' [y] yes    [n] no ')
    win.refresh()
    while True:
        c = win.getch()
        if c in (ord('y'), ord('Y')):
            return True
        if c in (ord('n'), ord('N'), 27):
            return False


def popup_select(stdscr, title: str, options: list[str]) -> str | None:
    if not options:
        return None
    want_w = max(30, len(title) + 4, max(len(o) for o in options) + 6)
    want_h = len(options) + 4
    win, box_w, box_h = _make_popup(stdscr, want_w, want_h)
    cur = 0
    while True:
        win.erase()
        win.border()
        safe_addstr(win, 0, 2, f' {title} ')
        for i, opt in enumerate(options):
            if 1 + i >= box_h - 2:
                break
            attr = curses.A_REVERSE if i == cur else curses.A_NORMAL
            safe_addstr(win, 1 + i, 2, f' {opt} '.ljust(box_w - 4), attr)
        safe_addstr(
            win, box_h - 2, 2, ' Enter=select  Esc=cancel ', curses.A_DIM,
        )
        win.refresh()
        c = win.getch()
        if c in (27, ord('q')):
            return None
        if c in (curses.KEY_UP, ord('k')):
            cur = max(0, cur - 1)
        elif c in (curses.KEY_DOWN, ord('j')):
            cur = min(len(options) - 1, cur + 1)
        elif c in (curses.KEY_ENTER, 10, 13):
            return options[cur]


# ---------- background SSH work ----------

def _with_device(state: TuiState, device: Device, job: Job, body):
    """Run body(device) with a per-device lock + connected SSH client.

    Raises on ssh_connect failure so the JobManager records the job as
    errored rather than silently marking it done.
    """
    lock = state.lock_for(device)
    acquired = lock.acquire(blocking=False)
    if not acquired:
        job.write(
            f'device {device.name} is busy with another job; waiting…',
        )
        job.status = 'queued'
        lock.acquire()
        job.status = 'running'
        job.write(f'device {device.name} lock acquired')
    try:
        device.ssh_connect()
        try:
            body(device)
        finally:
            try:
                device.ssh_close()
            except Exception as e:
                job.write(f'ssh_close error (ignored): {e}')
    finally:
        lock.release()


def _refresh_info(state: TuiState, dev: Device, job: Job) -> None:
    """Re-read channel, firmware and version info on a connected device."""
    dev.current_channel = dev.get_channel()
    dev.refresh_firmware_info()
    # A pending firmware reboot clears itself once the
    # device has rebooted and the versions match again.
    if dev.current_firmware == dev.upgrade_firmware:
        dev.firmware_reboot_pending = False
    dev.refresh_update_info()
    state.info_fetched[dev.name] = True
    job.write(f'identity:           {dev.identity}')
    job.write(f'installed version:  {dev.installed_version}')
    job.write(f'latest version:     {dev.latest_version}')
    job.write(f'channel on device:  {dev.current_channel}')
    job.write(f'configured channel: {dev.online_update_channel}')
    job.write(dev.firmware_info_str)


def _reconnect_and_refresh(state: TuiState, dev: Device, job: Job) -> None:
    """Refresh info after an action that may have rebooted the device."""
    dev.ssh_close()
    dev.ssh_connect()
    _refresh_info(state, dev, job)


def job_refresh(
    state: TuiState, device: Device,
) -> Callable[[Job], None]:
    def run(job: Job) -> None:
        state.info_fetched[device.name] = False
        _with_device(
            state, device, job, lambda dev: _refresh_info(state, dev, job),
        )
    return run


def job_apply_channel(
    state: TuiState, device: Device, channel: str,
) -> Callable[[Job], None]:
    def run(job: Job) -> None:
        state.info_fetched[device.name] = False

        def body(dev: Device) -> None:
            dev.set_channel(channel)
            dev.current_channel = dev.get_channel()
            job.write(f'channel on device now: {dev.current_channel}')
            dev.refresh_update_info()
            state.info_fetched[dev.name] = True
            job.write(dev.version_info_str)
        _with_device(state, device, job, body)
    return run


def job_backup(
    state: TuiState, device: Device,
) -> Callable[[Job], None]:
    def run(job: Job) -> None:
        def body(dev: Device) -> None:
            if not dev.backup():
                raise RuntimeError('backup or export failed')
            job.write('backup + export OK')
        _with_device(state, device, job, body)
    return run


def job_update(
    state: TuiState, device: Device,
) -> Callable[[Job], None]:
    def run(job: Job) -> None:
        def body(dev: Device) -> None:
            before = None
            if dev.get_update_available():
                before = dev.installed_version
                dev.update()
            else:
                job.write('no update available in the configured channel')
            if dev.update_firmware and not dev.firmware_update():
                raise RuntimeError('firmware update failed')
            _reconnect_and_refresh(state, dev, job)
            if before is not None and dev.installed_version == before:
                raise RuntimeError(f'still on {before} after update')
        _with_device(state, device, job, body)
    return run


def job_firmware_update(
    state: TuiState, device: Device,
) -> Callable[[Job], None]:
    """Upgrade routerboard firmware now, rebooting if needed."""
    def run(job: Job) -> None:
        def body(dev: Device) -> None:
            if not dev.firmware_update():
                raise RuntimeError('firmware update failed')
            dev.firmware_reboot_pending = False
            _reconnect_and_refresh(state, dev, job)
        _with_device(state, device, job, body)
    return run


def job_stage_firmware(
    state: TuiState, device: Device,
) -> Callable[[Job], None]:
    """Stage a routerboard firmware upgrade for the next reboot."""
    def run(job: Job) -> None:
        def body(dev: Device) -> None:
            dev.refresh_firmware_info()
            job.write(dev.firmware_info_str)
            if dev.current_firmware == dev.upgrade_firmware:
                dev.firmware_reboot_pending = False
                job.write('firmware already up to date; nothing to stage')
                return
            dev.stage_firmware_upgrade()
            dev.firmware_reboot_pending = True
            job.write(
                f'firmware upgrade staged: {dev.current_firmware} -> '
                f'{dev.upgrade_firmware} (reboot to apply)',
            )
        _with_device(state, device, job, body)
    return run


def job_reboot(
    state: TuiState, device: Device,
) -> Callable[[Job], None]:
    """Reboot the device and wait for it to come back before releasing.

    Uses Device.reboot_and_wait so the per-device lock is held until the
    router is reachable again. This prevents subsequent jobs from racing
    with a still-rebooting device. Only clears firmware_reboot_pending
    after the reboot is verified.
    """
    def run(job: Job) -> None:
        def body(dev: Device) -> None:
            job.write('rebooting device (waiting for it to come back)')
            if not dev.reboot_and_wait():
                raise RuntimeError('timed out waiting for device')
            dev.firmware_reboot_pending = False
            job.write('reboot complete')
            _reconnect_and_refresh(state, dev, job)
        _with_device(state, device, job, body)
    return run


# (menu label, job name, job factory, confirm warning; None = no confirm)
DEVICE_ACTIONS: list[tuple[str, str, Callable, str | None]] = [
    ('Refresh info', 'refresh', job_refresh, None),
    ('Backup + export config', 'backup', job_backup, ''),
    ('Update RouterOS', 'update', job_update, 'Devices will reboot.'),
    (
        'Update firmware', 'firmware', job_firmware_update,
        'Devices will reboot.',
    ),
    ('Reboot', 'reboot', job_reboot, 'Devices will be offline briefly.'),
]


# ---------- screens ----------

class YamlSelectScreen:
    def __init__(self, state: TuiState) -> None:
        self.state = state
        self.files = list_yaml_files(state.start_dir)
        self.cursor = 0
        self.top = 0

    def draw(self, stdscr) -> None:
        stdscr.erase()
        h, w = stdscr.getmaxyx()
        draw_header(
            stdscr,
            f' mu_tui — Select YAML config  '
            f'({self.state.start_dir}) ',
            ' ↑/↓ move  Enter select  r rescan  q quit ',
            self.state,
        )
        if not self.files:
            safe_addstr(
                stdscr, 2, 2,
                'No .yaml files found. Press r to rescan or q to quit.',
            )
            stdscr.refresh()
            return
        list_h = max(1, h - 3)
        if self.cursor < self.top:
            self.top = self.cursor
        elif self.cursor >= self.top + list_h:
            self.top = self.cursor - list_h + 1
        for i in range(list_h):
            idx = self.top + i
            if idx >= len(self.files):
                break
            name = os.path.basename(self.files[idx])
            attr = curses.A_REVERSE if idx == self.cursor else curses.A_NORMAL
            safe_addstr(
                stdscr, 1 + i, 2, clip(name, w - 4).ljust(w - 4), attr,
            )
        stdscr.refresh()

    def handle(self, stdscr, ch):
        if ch in (ord('q'), ord('Q')):
            return None
        if ch == -1 or ch == curses.KEY_RESIZE:
            return self
        if ch == ord('j'):
            return JobsScreen(self.state, self)
        if ch in (ord('r'), ord('R')):
            self.files = list_yaml_files(self.state.start_dir)
            self.cursor = 0
            self.top = 0
            return self
        if not self.files:
            return self
        if ch in (curses.KEY_UP, ord('k')):
            self.cursor = max(0, self.cursor - 1)
        elif ch in (curses.KEY_DOWN,):
            self.cursor = min(len(self.files) - 1, self.cursor + 1)
        elif ch == curses.KEY_HOME:
            self.cursor = 0
        elif ch == curses.KEY_END:
            self.cursor = len(self.files) - 1
        elif ch in (curses.KEY_ENTER, 10, 13):
            path = self.files[self.cursor]
            return self._load(stdscr, path)
        return self

    def _load(self, stdscr, path: str):
        cm = ConfigManager(path)
        try:
            if not cm.check_config_file():
                popup_message(stdscr, 'Config file check failed.')
                return self
            devices, logger = cm.load_config()
        except Exception as e:
            popup_message(stdscr, f'Failed to load config:\n{e}')
            return self
        self.state.yaml_path = path
        self.state.devices = devices
        self.state.logger = logger
        self.state.info_fetched = {}
        self.state.device_locks = {}
        return DevicesScreen(self.state)


def _job_status_line(job: Job | None) -> str:
    """One-line summary of a job for embedding in a menu screen.

    Returns an empty string when there is no job to report on.
    """
    if job is None:
        return ''
    marker = _MARKERS.get(job.status, '?')
    if job.status == 'queued':
        detail = 'waiting for device…'
    elif job.status == 'running':
        detail = 'running…'
    elif job.status == 'done':
        detail = f'success ({job.duration():.1f}s)'
    elif job.status == 'error':
        detail = f'FAILED: {job.error or "unknown error"}'
    else:
        detail = job.status
    return f'{marker} {job.name}: {detail}  (press j for log)'


def _device_job_badge(job: Job | None) -> str:
    """Short per-device status of its latest job, e.g. '▶ update'."""
    if job is None:
        return ''
    action = ' '.join(w for w in job.name.split() if w != job.device)
    badge = f'{_MARKERS.get(job.status, "?")} {action}'
    if job.status == 'error':
        badge += f': {job.error or "failed"}'
    return badge


def _arrow(old: str, new: str) -> str:
    return old if old == new else f'{old}→{new}'


def _table(rows: list[list[str]]) -> list[str]:
    """Align rows (first row = header) into columns just wide enough.

    Columns whose cells are all empty are dropped, header included.
    """
    widths = [
        max(len(r[i]) for r in rows) if any(r[i] for r in rows[1:]) else 0
        for i in range(len(rows[0]))
    ]
    return [
        '  '.join(c.ljust(wd) for c, wd in zip(r, widths) if wd).rstrip()
        for r in rows
    ]


_ID_HEADERS = ['', 'NAME', 'ADDRESS']
_INFO_HEADERS = ['IDENTITY', 'VERSION', 'CHANNEL', 'UPD', 'FIRMWARE', '']
_JOB_HEADER = 'LAST JOB'
# Second-row indent in the two-row layout: lines info up under NAME.
_INFO_INDENT = ' ' * 5


class DevicesScreen:
    def __init__(self, state: TuiState) -> None:
        self.state = state
        self.cursor = 0
        self.top = 0
        self.selected: set[int] = set()

    def _info_cells(self, d: Device) -> list[str]:
        pending = (
            '⚠ reboot pending'
            if getattr(d, 'firmware_reboot_pending', False) else ''
        )
        if not self.state.info_fetched.get(d.name):
            return ['(no info)', '', '', '', '', pending]
        avail = getattr(d, 'update_available', None)
        return [
            d.identity or '?',
            _arrow(d.installed_version, d.latest_version),
            getattr(d, 'current_channel', '') or '?',
            'yes' if avail else ('no' if avail is False else '?'),
            _arrow(d.current_firmware, d.upgrade_firmware),
            pending,
        ]

    def _layout(self, w: int) -> tuple[list[str], list[list[str]]]:
        """Return (header lines, per-device lines) fitted to width w.

        One row per device when the table (up to a short LAST JOB) fits,
        otherwise two: name +
        job on the first, device info on the second.
        """
        devs = self.state.devices
        ids = [
            ['[x]' if i in self.selected else '[ ]', d.name, d.address]
            for i, d in enumerate(devs)
        ]
        infos = [self._info_cells(d) for d in devs]
        jobs = [
            _device_job_badge(self.state.jobs.latest_for(d.name))
            for d in devs
        ]
        one = _table(
            [_ID_HEADERS + _INFO_HEADERS + [_JOB_HEADER]]
            + [i + f + [j] for i, f, j in zip(ids, infos, jobs)],
        )
        # LAST JOB is the last column and may be clipped (long error
        # text), so only the columns before it must fit.
        fixed = _table(
            [_ID_HEADERS + _INFO_HEADERS]
            + [i + f for i, f in zip(ids, infos)],
        )
        if max(len(ln) for ln in fixed) + len('  ✗ update') <= w - 4:
            return one[:1], [[ln] for ln in one[1:]]
        top = _table(
            [_ID_HEADERS + [_JOB_HEADER]]
            + [i + [j] for i, j in zip(ids, jobs)],
        )
        info = [_INFO_INDENT + ln for ln in _table([_INFO_HEADERS] + infos)]
        return [top[0], info[0]], [list(p) for p in zip(top[1:], info[1:])]

    def draw(self, stdscr) -> None:
        stdscr.erase()
        h, w = stdscr.getmaxyx()
        title = (
            f' Devices — {os.path.basename(self.state.yaml_path or "")}  '
            f'({len(self.state.devices)}, selected: {len(self.selected)}) '
        )
        draw_header(
            stdscr, title,
            ' ↑/↓ move  Space toggle  a all  n none  r refresh all/sel  '
            'x actions  Enter details  Bksp back  q quit ',
            self.state,
        )
        if not self.state.devices:
            safe_addstr(stdscr, 2, 2, 'No devices in this config.')
            stdscr.refresh()
            return
        bottom = h - 1
        heads, lines = self._layout(w)
        for i, head in enumerate(heads):
            if 1 + i < bottom:
                safe_addstr(stdscr, 1 + i, 2, clip(head, w - 4), curses.A_DIM)
        first = 1 + len(heads)
        rows_per = len(lines[0])
        visible = max(1, (bottom - first) // rows_per)
        if self.cursor < self.top:
            self.top = self.cursor
        elif self.cursor >= self.top + visible:
            self.top = self.cursor - visible + 1
        for i in range(visible):
            idx = self.top + i
            if idx >= len(lines):
                break
            job = self.state.jobs.latest_for(self.state.devices[idx].name)
            attr = curses.A_REVERSE if idx == self.cursor else curses.A_NORMAL
            if job is not None and job.status == 'error':
                attr |= curses.A_BOLD
            for k, ln in enumerate(lines[idx]):
                row = first + i * rows_per + k
                if row < bottom:
                    safe_addstr(
                        stdscr, row, 2, clip(ln, w - 4).ljust(w - 4), attr,
                    )
        stdscr.refresh()

    def _submit(self, label: str, factory, targets: list[Device]) -> None:
        """Start one independent job per device so they all run in parallel."""
        for d in targets:
            self.state.jobs.submit(
                f'{label} {d.name}', factory(self.state, d), device=d.name,
            )

    def _act_menu(self, stdscr) -> None:
        if self.selected:
            targets = [self.state.devices[i] for i in sorted(self.selected)]
        else:
            targets = [self.state.devices[self.cursor]]
        who = (
            targets[0].name if len(targets) == 1
            else f'{len(targets)} devices'
        )
        choice = popup_select(
            stdscr, f'Action for {who}', [a[0] for a in DEVICE_ACTIONS],
        )
        for label, name, factory, warning in DEVICE_ACTIONS:
            if label != choice:
                continue
            if warning is not None and not popup_confirm(
                stdscr, f'{label} on {who}? {warning}'.strip(),
            ):
                return
            self._submit(name, factory, targets)

    def handle(self, stdscr, ch):
        if ch in (ord('q'), ord('Q')):
            return None
        if ch == -1 or ch == curses.KEY_RESIZE:
            return self
        if ch == ord('j'):
            return JobsScreen(self.state, self)
        if ch in _BACK_KEYS:
            return YamlSelectScreen(self.state)
        if not self.state.devices:
            return self
        if ch in (curses.KEY_UP, ord('k')):
            self.cursor = max(0, self.cursor - 1)
        elif ch in (curses.KEY_DOWN,):
            self.cursor = min(len(self.state.devices) - 1, self.cursor + 1)
        elif ch == curses.KEY_HOME:
            self.cursor = 0
        elif ch == curses.KEY_END:
            self.cursor = len(self.state.devices) - 1
        elif ch == ord(' '):
            if self.cursor in self.selected:
                self.selected.remove(self.cursor)
            else:
                self.selected.add(self.cursor)
        elif ch in (ord('a'), ord('A')):
            self.selected = set(range(len(self.state.devices)))
        elif ch in (ord('n'), ord('N')):
            self.selected.clear()
        elif ch in (ord('r'), ord('R')):
            if self.selected:
                targets = [
                    self.state.devices[i] for i in sorted(self.selected)
                ]
            else:
                targets = list(self.state.devices)
            self._submit('refresh', job_refresh, targets)
        elif ch in (ord('x'), ord('X')):
            self._act_menu(stdscr)
        elif ch in (curses.KEY_ENTER, 10, 13):
            d = self.state.devices[self.cursor]
            return DeviceDetailScreen(self.state, d, self)
        return self


class DeviceDetailScreen:
    def __init__(
        self, state: TuiState, device: Device, parent: DevicesScreen,
    ) -> None:
        self.state = state
        self.device = device
        self.parent = parent
        self.actions: list[tuple[str, Callable[[object], Job | None]]] = [
            ('Refresh info', self.act_refresh),
            ('Change update channel', self.act_channel),
            ('Backup + export config', self.act_backup),
            ('Perform update', self.act_update),
            ('Update firmware now (reboots)', self.act_firmware),
            ('Stage firmware upgrade (next reboot)', self.act_stage_fw),
            ('Reboot device', self.act_reboot),
        ]
        self.cursor = 0
        self.last_job: Job | None = None

    def _info_lines(self) -> list[str]:
        d = self.device
        lines = [
            f'Name (config):       {d.name}',
            f'Address:             {d.address}:{d.port}',
            f'Username:            {d.username}',
            f'Update type:         {d.update_type}',
            f'Configured channel:  {d.online_update_channel}',
            f'Update firmware:     {d.update_firmware}',
            '',
        ]
        if self.state.info_fetched.get(d.name):
            avail = getattr(d, 'update_available', None)
            lines.extend([
                f'Identity:            {d.identity or "?"}',
                f'Installed version:   {d.installed_version}',
                f'Latest version:      {d.latest_version}',
                f'Update available:    {avail}',
                f'Channel on device:   '
                f'{getattr(d, "current_channel", "?")}',
                f'Current firmware:    {d.current_firmware}',
                f'Upgrade firmware:    {d.upgrade_firmware}',
            ])
        else:
            lines.append('(info not fetched — use "Refresh info" below)')
        if getattr(d, 'firmware_reboot_pending', False):
            lines.append('')
            lines.append(
                '⚠ Firmware upgrade staged — reboot the device to apply.',
            )
        if d.update_type == 'manual' and d.packages:
            lines.append('')
            lines.append('Packages:')
            for p in d.packages:
                lines.append(f'  {p}')
        return lines

    def draw(self, stdscr) -> None:
        stdscr.erase()
        h, w = stdscr.getmaxyx()
        draw_header(
            stdscr,
            f' Device: {self.device.name} ({self.device.address}) ',
            ' ↑/↓ move  Enter run action  Bksp back  q quit ',
            self.state,
        )
        y = 1
        for line in self._info_lines():
            if y >= h - 1:
                break
            safe_addstr(stdscr, y, 2, clip(line, w - 4))
            y += 1
        if y < h - 2:
            try:
                stdscr.hline(y, 2, curses.ACS_HLINE, max(0, w - 4))
            except curses.error:
                pass
            y += 1
        safe_addstr(stdscr, y, 2, 'Actions:', curses.A_BOLD)
        y += 1
        status = _job_status_line(self.last_job)
        # Leave the bottom row for the help hint (h - 1). If we have a
        # status line, reserve the row above it too.
        actions_bottom = h - 2 if status else h - 1
        for i, (label, _) in enumerate(self.actions):
            if y >= actions_bottom:
                break
            attr = curses.A_REVERSE if i == self.cursor else curses.A_NORMAL
            safe_addstr(
                stdscr, y, 2, f'  {label}  '.ljust(w - 4), attr,
            )
            y += 1
        if status:
            attr_s = curses.A_BOLD
            if self.last_job is not None and self.last_job.status == 'error':
                attr_s |= curses.A_REVERSE
            safe_addstr(stdscr, h - 2, 0, status[: w - 1], attr_s)
        stdscr.refresh()

    def handle(self, stdscr, ch):
        if ch in (ord('q'), ord('Q')):
            return None
        if ch == -1 or ch == curses.KEY_RESIZE:
            return self
        if ch == ord('j'):
            return JobsScreen(self.state, self)
        if ch in _BACK_KEYS:
            return self.parent
        if ch in (curses.KEY_UP, ord('k')):
            self.cursor = max(0, self.cursor - 1)
        elif ch in (curses.KEY_DOWN,):
            self.cursor = min(len(self.actions) - 1, self.cursor + 1)
        elif ch in (curses.KEY_ENTER, 10, 13):
            _, fn = self.actions[self.cursor]
            job = fn(stdscr)
            if job is not None:
                # Track only the most recent action so the status line
                # reflects what the user just triggered. Details remain
                # accessible via the Jobs screen (press j).
                self.last_job = job
        return self

    def act_refresh(self, stdscr) -> Job | None:
        return self.state.jobs.submit(
            f'refresh {self.device.name}',
            job_refresh(self.state, self.device),
            device=self.device.name,
        )

    def act_channel(self, stdscr) -> Job | None:
        choice = popup_select(stdscr, 'Select update channel', CHANNELS)
        if choice is None:
            return None
        if not popup_confirm(
            stdscr,
            f'Set channel to "{choice}" on {self.device.name}?',
        ):
            return None
        self.device.online_update_channel = choice
        return self.state.jobs.submit(
            f'channel {self.device.name} -> {choice}',
            job_apply_channel(self.state, self.device, choice),
            device=self.device.name,
        )

    def act_backup(self, stdscr) -> Job | None:
        if not popup_confirm(
            stdscr, f'Run backup + export on {self.device.name}?',
        ):
            return None
        return self.state.jobs.submit(
            f'backup {self.device.name}',
            job_backup(self.state, self.device),
            device=self.device.name,
        )

    def act_update(self, stdscr) -> Job | None:
        if not popup_confirm(
            stdscr,
            f'Perform update on {self.device.name}? '
            'The device will reboot.',
        ):
            return None
        return self.state.jobs.submit(
            f'update {self.device.name}',
            job_update(self.state, self.device),
            device=self.device.name,
        )

    def act_firmware(self, stdscr) -> Job | None:
        if not popup_confirm(
            stdscr,
            f'Update firmware on {self.device.name}? '
            'The device will reboot.',
        ):
            return None
        return self.state.jobs.submit(
            f'firmware {self.device.name}',
            job_firmware_update(self.state, self.device),
            device=self.device.name,
        )

    def act_stage_fw(self, stdscr) -> Job | None:
        if not popup_confirm(
            stdscr,
            f'Stage routerboard firmware upgrade on '
            f'{self.device.name}? Applied on next reboot.',
        ):
            return None
        return self.state.jobs.submit(
            f'stage firmware {self.device.name}',
            job_stage_firmware(self.state, self.device),
            device=self.device.name,
        )

    def act_reboot(self, stdscr) -> Job | None:
        if not popup_confirm(
            stdscr,
            f'Reboot {self.device.name}? Device will be offline briefly.',
        ):
            return None
        return self.state.jobs.submit(
            f'reboot {self.device.name}',
            job_reboot(self.state, self.device),
            device=self.device.name,
        )


class JobsScreen:
    def __init__(self, state: TuiState, parent) -> None:
        self.state = state
        self.parent = parent
        self.cursor = 0
        self.top = 0

    def draw(self, stdscr) -> None:
        stdscr.erase()
        h, w = stdscr.getmaxyx()
        draw_header(
            stdscr, ' Jobs ',
            ' ↑/↓ move  Enter view log  c clear finished  '
            'Bksp back  q quit ',
            self.state,
        )
        jobs = self.state.jobs.all()
        if not jobs:
            safe_addstr(stdscr, 2, 2, 'No jobs yet.')
            stdscr.refresh()
            return
        list_h = max(1, h - 3)
        if self.cursor >= len(jobs):
            self.cursor = len(jobs) - 1
        if self.cursor < self.top:
            self.top = self.cursor
        elif self.cursor >= self.top + list_h:
            self.top = self.cursor - list_h + 1
        for i in range(list_h):
            idx = self.top + i
            if idx >= len(jobs):
                break
            job = jobs[idx]
            marker = _MARKERS.get(job.status, '?')
            line = (
                f'{marker} {job.status:<7} '
                f'{job.duration():6.1f}s  {job.name}'
            )
            attr = curses.A_REVERSE if idx == self.cursor else curses.A_NORMAL
            if job.status == 'error':
                attr |= curses.A_BOLD
            safe_addstr(
                stdscr, 1 + i, 2, clip(line, w - 4).ljust(w - 4), attr,
            )
        stdscr.refresh()

    def handle(self, stdscr, ch):
        if ch in (ord('q'), ord('Q')):
            return None
        if ch == -1 or ch == curses.KEY_RESIZE:
            return self
        if ch == ord('j') or ch in _BACK_KEYS:
            return self.parent
        jobs = self.state.jobs.all()
        if not jobs:
            if ch in (ord('c'), ord('C')):
                self.state.jobs.clear_finished()
            return self
        if ch in (curses.KEY_UP, ord('k')):
            self.cursor = max(0, self.cursor - 1)
        elif ch in (curses.KEY_DOWN,):
            self.cursor = min(len(jobs) - 1, self.cursor + 1)
        elif ch == curses.KEY_HOME:
            self.cursor = 0
        elif ch == curses.KEY_END:
            self.cursor = len(jobs) - 1
        elif ch in (ord('c'), ord('C')):
            self.state.jobs.clear_finished()
            self.cursor = 0
            self.top = 0
        elif ch in (curses.KEY_ENTER, 10, 13):
            return JobLogScreen(self.state, jobs[self.cursor], self)
        return self


class JobLogScreen:
    def __init__(self, state: TuiState, job: Job, parent) -> None:
        self.state = state
        self.job = job
        self.parent = parent
        self.top = 0
        self.follow = True

    def draw(self, stdscr) -> None:
        stdscr.erase()
        h, w = stdscr.getmaxyx()
        title = (
            f' Log — {self.job.name}  [{self.job.status}]  '
            f'{self.job.duration():.1f}s '
        )
        draw_header(
            stdscr, title,
            ' ↑/↓ PgUp/PgDn scroll  End/f follow  Bksp back  q quit ',
            self.state,
        )
        lines = self.job.snapshot()
        # wrap long lines to width
        wrapped: list[str] = []
        wmax = max(1, w - 2)
        for line in lines:
            if not line:
                wrapped.append('')
                continue
            for i in range(0, len(line), wmax):
                wrapped.append(line[i:i + wmax])
        list_h = max(1, h - 3)
        if self.follow:
            self.top = max(0, len(wrapped) - list_h)
        self.top = max(0, min(self.top, max(0, len(wrapped) - 1)))
        for i in range(list_h):
            idx = self.top + i
            if idx >= len(wrapped):
                break
            safe_addstr(stdscr, 1 + i, 1, wrapped[idx][: w - 2])
        stdscr.refresh()

    def handle(self, stdscr, ch):
        if ch in (ord('q'), ord('Q')):
            return None
        if ch == -1 or ch == curses.KEY_RESIZE:
            return self
        if ch in _BACK_KEYS:
            return self.parent
        if ch == ord('j'):
            # self.parent is a JobsScreen; peel one level so 'j' toggles
            # back to whatever screen opened the Jobs list.
            grandparent = getattr(self.parent, 'parent', self.parent)
            return JobsScreen(self.state, grandparent)
        if ch in (curses.KEY_UP, ord('k')):
            self.follow = False
            self.top = max(0, self.top - 1)
        elif ch in (curses.KEY_DOWN,):
            self.follow = False
            self.top += 1
        elif ch == curses.KEY_PPAGE:
            self.follow = False
            self.top = max(0, self.top - 10)
        elif ch == curses.KEY_NPAGE:
            self.follow = False
            self.top += 10
        elif ch == curses.KEY_HOME:
            self.follow = False
            self.top = 0
        elif ch in (curses.KEY_END, ord('f'), ord('F')):
            self.follow = True
        return self


# ---------- entry ----------

def _run(stdscr, state: TuiState) -> None:
    curses.curs_set(0)
    stdscr.keypad(True)
    stdscr.timeout(500)  # ms; drives periodic redraw for live job status
    screen = YamlSelectScreen(state)
    while screen is not None:
        screen.draw(stdscr)
        ch = stdscr.getch()
        screen = screen.handle(stdscr, ch)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        prog='mu_tui',
        description='Curses interactive TUI for the mu tool.',
    )
    parser.add_argument(
        '-d', '--directory', default='.',
        help='Directory to scan for yaml configuration files '
             '(default: current directory).',
    )
    args = parser.parse_args(argv)
    if not os.path.isdir(args.directory):
        print(f'Directory not found: {args.directory}')
        return 1
    state = TuiState(os.path.abspath(args.directory))
    _install_output_taps()
    try:
        try:
            curses.wrapper(_run, state)
        except KeyboardInterrupt:
            pass
    finally:
        _uninstall_output_taps()
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
