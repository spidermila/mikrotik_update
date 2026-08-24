"""Tests for the mu_tui package.

The TUI is curses-based; we exercise it through fake curses windows and by
driving screen ``handle`` methods with synthetic key codes.
"""
from __future__ import annotations

import curses
import sys
import threading
import time
from unittest.mock import MagicMock

import pytest

from mu.logger import Logger
from mu_tui import main as tui


# ---------- fakes ----------


class FakeWin:
    """Minimal curses window/pad stand-in used by the tests."""

    def __init__(self, h: int = 24, w: int = 80) -> None:
        self.h = h
        self.w = w
        self.calls: list[tuple] = []
        self.keys: list[int] = []
        self.timeout_val: int | None = None
        self.raise_on_addstr = False

    # queue key codes to be returned by successive getch() calls
    def queue(self, *keys) -> None:
        for k in keys:
            self.keys.append(ord(k) if isinstance(k, str) else k)

    def getmaxyx(self) -> tuple[int, int]:
        return (self.h, self.w)

    def erase(self) -> None:
        self.calls.append(('erase',))

    def refresh(self) -> None:
        self.calls.append(('refresh',))

    def addstr(self, y: int, x: int, s: str, attr: int = 0) -> None:
        if self.raise_on_addstr:
            raise curses.error('boom')
        self.calls.append(('addstr', y, x, s, attr))

    def hline(self, y: int, x: int, ch, n: int) -> None:
        self.calls.append(('hline', y, x, n))

    def border(self) -> None:
        self.calls.append(('border',))

    def keypad(self, val: bool) -> None:
        self.calls.append(('keypad', val))

    def nodelay(self, val: bool) -> None:
        self.calls.append(('nodelay', val))

    def timeout(self, ms: int) -> None:
        self.timeout_val = ms

    def getch(self) -> int:
        if not self.keys:
            return -1
        return self.keys.pop(0)


@pytest.fixture(autouse=True)
def _restore_stdio():
    """Undo any sys.stdout/stderr/Logger.log monkey-patching between tests."""
    orig_stdout = sys.stdout
    orig_stderr = sys.stderr
    orig_log = Logger.log
    yield
    sys.stdout = orig_stdout
    sys.stderr = orig_stderr
    Logger.log = orig_log
    # Reset module-level install state so each test starts clean.
    tui._original_log = None
    tui._original_stdout = None
    tui._original_stderr = None


@pytest.fixture(autouse=True)
def _stub_curses_acs(monkeypatch):
    """curses.ACS_HLINE only exists after initscr(); provide a stub."""
    if not hasattr(curses, 'ACS_HLINE'):
        monkeypatch.setattr(curses, 'ACS_HLINE', ord('-'), raising=False)


@pytest.fixture
def state(tmp_path):
    return tui.TuiState(str(tmp_path))


def _mock_device(
    name: str = 'router',
    address: str = '10.0.0.1',
    **overrides,
):
    """Build a fully-populated MagicMock Device stand-in.

    Every attribute the TUI touches is set to a sensible default so
    tests don't have to repeat the boilerplate. Pass ``**overrides`` to
    change individual attributes.
    """
    d = MagicMock()
    d.name = name
    d.address = address
    d.port = 22
    d.username = 'admin'
    d.update_type = 'online'
    d.online_update_channel = 'stable'
    d.update_firmware = False
    d.identity = name
    d.installed_version = '7.15'
    d.latest_version = '7.16'
    d.current_channel = 'stable'
    d.current_firmware = '7.15'
    d.upgrade_firmware = '7.15'
    d.version_info_str = 'installed: 7.15, available: 7.16'
    d.firmware_info_str = 'current firmware: 7.15, upgrade firmware: 7.15'
    d.update_available = True
    d.packages = []
    d.firmware_reboot_pending = False
    d.get_channel.return_value = 'stable'
    for k, v in overrides.items():
        setattr(d, k, v)
    return d


def _armed_newwin_factory(key_sequence):
    """Return a ``curses.newwin`` replacement that yields ``FakeWin``s
    pre-armed with the given key codes."""
    seq = list(key_sequence)

    class ArmedWin(FakeWin):
        def __init__(self, h, w):
            super().__init__(h, w)
            self.queue(*seq)

    return lambda h, w, y, x: ArmedWin(h, w)


@pytest.fixture
def fake_device():
    return _mock_device()


# ---------- _JobStream ----------


def test_job_stream_write_without_job_is_dropped():
    stream = tui._JobStream()
    assert stream.write('hello\n') == len('hello\n')
    assert stream.write('') == 0
    assert stream.isatty() is False


def test_job_stream_write_and_flush_route_to_job():
    stream = tui._JobStream()
    job = tui.Job('t')
    tui._current_job.job = job
    try:
        # partial line then completion
        stream.write('hel')
        stream.write('lo\nworld')
        stream.flush()
        # first flush with no tail is a no-op
        tui._current_job.job = None
        stream.flush()
    finally:
        tui._current_job.job = None
    text = '\n'.join(job.snapshot())
    assert 'hello' in text
    assert 'world' in text


# ---------- Job / JobManager ----------


def test_job_write_handles_empty_string():
    job = tui.Job('x')
    job.write('')
    # `'' .splitlines()` is [], so the `or ['']` fallback fires
    assert len(job.snapshot()) == 1


def test_job_duration_uses_finished_when_set():
    job = tui.Job('x')
    job.started = 100.0
    job.finished = 105.0
    assert job.duration() == pytest.approx(5.0)


def test_job_duration_uses_now_when_running():
    job = tui.Job('x')
    d = job.duration()
    assert d >= 0.0


def _wait_finished(job: tui.Job, timeout: float = 2.0) -> None:
    end = time.time() + timeout
    while time.time() < end and job.finished is None:
        time.sleep(0.01)
    assert job.finished is not None, f'job stuck in status {job.status}'


def test_jobmanager_submit_success_and_running_count():
    mgr = tui.JobManager()
    done = threading.Event()

    def target(job: tui.Job) -> None:
        job.write('working')
        done.set()

    job = mgr.submit('good', target)
    done.wait(timeout=1)
    _wait_finished(job)
    assert job.status == 'done'
    assert 'working' in '\n'.join(job.snapshot())
    assert mgr.running_count() == 0
    assert mgr.all() == [job]


def test_jobmanager_submit_error_captures_traceback():
    mgr = tui.JobManager()

    def target(job: tui.Job) -> None:
        raise RuntimeError('boom')

    job = mgr.submit('bad', target)
    _wait_finished(job)
    assert job.status == 'error'
    assert job.error == 'boom'
    text = '\n'.join(job.snapshot())
    assert 'RuntimeError: boom' in text
    assert 'Traceback' in text


def test_jobmanager_flushes_partial_stdout_line(tmp_path):
    """A job that writes a partial (unterminated) line via ``print`` /
    ``sys.stdout.write`` must still see that tail appear in its log —
    the runner is responsible for flushing before the thread exits."""
    tui._install_output_taps()
    try:
        mgr = tui.JobManager()

        def target(job):
            sys.stdout.write('no-newline-tail')

        job = mgr.submit('tail', target)
        _wait_finished(job)
    finally:
        tui._uninstall_output_taps()
    assert any('no-newline-tail' in ln for ln in job.snapshot())


def test_jobmanager_clear_finished():
    mgr = tui.JobManager()
    j1 = mgr.submit('a', lambda job: None)
    _wait_finished(j1)
    # add a "running" job by inserting a Job directly under the lock
    stuck = tui.Job('stuck')
    with mgr.lock:
        mgr.jobs.append(stuck)
    assert len(mgr.all()) == 2
    mgr.clear_finished()
    remaining = mgr.all()
    assert remaining == [stuck]


# ---------- _install_output_taps ----------


def test_install_output_taps_routes_logger_and_stdout(tmp_path):
    logger = Logger(str(tmp_path))
    tui._install_output_taps()
    job = tui.Job('t')
    tui._current_job.job = job
    try:
        logger.log('info', 'dev', 'hello')
        print('via stdout')
        sys.stdout.flush()
    finally:
        tui._current_job.job = None
    text = '\n'.join(job.snapshot())
    assert '[info] dev: hello' in text
    assert 'via stdout' in text
    # Logger.log without an active job must not write to real stdout;
    # `_JobStream.write` just drops it -> no exception here.
    logger.log('info', 'dev', 'no-job')
    tui._uninstall_output_taps()


def test_install_output_taps_is_idempotent(tmp_path):
    logger = Logger(str(tmp_path))
    tui._install_output_taps()
    tui._install_output_taps()  # must not double-wrap
    job = tui.Job('t')
    tui._current_job.job = job
    try:
        logger.log('info', 'dev', 'once')
    finally:
        tui._current_job.job = None
    text = '\n'.join(job.snapshot())
    assert text.count('[info] dev: once') == 1
    tui._uninstall_output_taps()


def test_uninstall_output_taps_restores_originals():
    orig_stdout = sys.stdout
    orig_log = Logger.log
    tui._install_output_taps()
    assert sys.stdout is not orig_stdout
    assert Logger.log is not orig_log
    tui._uninstall_output_taps()
    assert sys.stdout is orig_stdout
    assert Logger.log is orig_log
    # calling again with nothing installed is a no-op
    tui._uninstall_output_taps()


# ---------- TuiState ----------


def test_tuistate_lock_for_is_stable(state, fake_device):
    lock1 = state.lock_for(fake_device)
    lock2 = state.lock_for(fake_device)
    assert lock1 is lock2


# ---------- helpers ----------


def test_list_yaml_files(tmp_path):
    (tmp_path / 'a.yaml').write_text('x')
    (tmp_path / 'b.yml').write_text('x')
    (tmp_path / 'c.txt').write_text('x')
    (tmp_path / 'sub').mkdir()
    files = tui.list_yaml_files(str(tmp_path))
    names = sorted(f.rsplit('/', 1)[-1] for f in files)
    assert names == ['a.yaml', 'b.yml']


def test_list_yaml_files_missing_dir():
    assert tui.list_yaml_files('/no/such/dir/here') == []


def test_clip_edge_cases():
    assert tui.clip('hello', 0) == ''
    assert tui.clip('hi', 10) == 'hi'
    assert tui.clip('hello world', 5) == 'hell…'


def test_safe_addstr_swallows_curses_error():
    win = FakeWin()
    win.raise_on_addstr = True
    tui.safe_addstr(win, 0, 0, 'x')  # must not raise


def test_safe_addstr_normal_path():
    win = FakeWin()
    tui.safe_addstr(win, 1, 2, 'x')
    assert ('addstr', 1, 2, 'x', 0) in win.calls


def test_draw_header_normal_and_tiny(state):
    win = FakeWin(24, 80)
    tui.draw_header(win, 'title', 'help', state)
    assert any(c[0] == 'addstr' for c in win.calls)
    tiny = FakeWin(0, 0)
    tui.draw_header(tiny, 'title', 'help', state)  # early return


def test_draw_header_h_less_than_two(state):
    win = FakeWin(1, 80)
    tui.draw_header(win, 'title', 'help', state)
    # only title bar drawn; no bottom hint
    addstr_ys = [c[1] for c in win.calls if c[0] == 'addstr']
    assert addstr_ys == [0]


# ---------- popup helpers ----------


def test_popup_message(monkeypatch):
    monkeypatch.setattr(
        tui.curses, 'newwin', _armed_newwin_factory([ord(' ')]),
    )
    tui.popup_message(FakeWin(24, 80), 'hello\nworld')
    # tiny screen forces the overflow break inside the render loop
    tui.popup_message(
        FakeWin(6, 80), 'a\nb\nc\nd\ne\nf\ng',
    )


def test_popup_confirm_yes_no_and_esc(monkeypatch):
    stdscr = FakeWin(24, 80)

    monkeypatch.setattr(
        tui.curses, 'newwin', _armed_newwin_factory([ord('y')]),
    )
    assert tui.popup_confirm(stdscr, 'ok?') is True

    monkeypatch.setattr(
        tui.curses, 'newwin', _armed_newwin_factory([ord('n')]),
    )
    assert tui.popup_confirm(stdscr, 'ok?') is False

    monkeypatch.setattr(
        tui.curses, 'newwin', _armed_newwin_factory([27]),
    )
    assert tui.popup_confirm(stdscr, 'ok?') is False

    # ignored key, then 'y'
    monkeypatch.setattr(
        tui.curses, 'newwin',
        _armed_newwin_factory([ord('x'), ord('Y')]),
    )
    assert tui.popup_confirm(stdscr, 'ok?') is True


def test_popup_select_navigation(monkeypatch):
    stdscr = FakeWin(24, 80)

    # down, down, up, enter -> options[1]
    monkeypatch.setattr(
        tui.curses, 'newwin',
        _armed_newwin_factory([
            curses.KEY_DOWN, curses.KEY_DOWN, curses.KEY_UP,
            curses.KEY_ENTER,
        ]),
    )
    assert tui.popup_select(
        stdscr, 'pick', ['a', 'b', 'c'],
    ) == 'b'

    # esc cancels
    monkeypatch.setattr(
        tui.curses, 'newwin', _armed_newwin_factory([27]),
    )
    assert tui.popup_select(stdscr, 'pick', ['a']) is None
    # 'q' also cancels
    monkeypatch.setattr(
        tui.curses, 'newwin', _armed_newwin_factory([ord('q')]),
    )
    assert tui.popup_select(stdscr, 'pick', ['a']) is None
    # tiny screen so the options loop hits its break overflow guard
    monkeypatch.setattr(
        tui.curses, 'newwin',
        _armed_newwin_factory([curses.KEY_ENTER]),
    )
    tiny = FakeWin(6, 80)
    assert tui.popup_select(
        tiny, 'pick', ['a', 'b', 'c', 'd', 'e', 'f'],
    ) == 'a'


# ---------- _with_device / job factories ----------


def test_with_device_success(state, fake_device):
    job = tui.Job('t')
    called = []

    def body(dev):
        called.append(dev)

    tui._with_device(state, fake_device, job, body)
    assert called == [fake_device]
    fake_device.ssh_connect.assert_called_once()
    fake_device.ssh_close.assert_called_once()


def test_with_device_lock_busy_path(state, fake_device):
    job = tui.Job('t')
    # pre-acquire the device lock in another thread
    lock = state.lock_for(fake_device)
    lock.acquire()
    released = threading.Event()

    def hold_then_release():
        time.sleep(0.05)
        lock.release()
        released.set()

    threading.Thread(target=hold_then_release, daemon=True).start()

    body_called = []
    tui._with_device(state, fake_device, job, lambda d: body_called.append(1))
    released.wait(timeout=1)
    assert body_called == [1]
    assert any('busy with another job' in ln for ln in job.snapshot())


def test_with_device_connect_failure(state, fake_device):
    job = tui.Job('t')
    fake_device.ssh_connect.side_effect = RuntimeError('nope')
    with pytest.raises(RuntimeError):
        tui._with_device(state, fake_device, job, lambda d: None)
    fake_device.ssh_close.assert_not_called()


def test_with_device_connect_failure_surfaces_as_error_job(
    state, fake_device,
):
    fake_device.ssh_connect.side_effect = RuntimeError('nope')
    mgr = tui.JobManager()

    def target(job):
        tui._with_device(state, fake_device, job, lambda d: None)

    job = mgr.submit('bad', target)
    _wait_finished(job)
    assert job.status == 'error'


def test_with_device_body_raises_still_closes(state, fake_device):
    job = tui.Job('t')

    def body(dev):
        raise ValueError('bad')

    with pytest.raises(ValueError):
        tui._with_device(state, fake_device, job, body)
    fake_device.ssh_close.assert_called_once()


def test_with_device_ssh_close_error_swallowed(state, fake_device):
    job = tui.Job('t')
    fake_device.ssh_close.side_effect = RuntimeError('bad close')
    tui._with_device(state, fake_device, job, lambda d: None)  # no raise
    assert any('ssh_close error' in ln for ln in job.snapshot())


def test_job_refresh_clears_firmware_pending(state, fake_device):
    fake_device.firmware_reboot_pending = True
    fake_device.current_firmware = '7.15'
    fake_device.upgrade_firmware = '7.15'
    fake_device.get_channel.return_value = 'stable'
    job = tui.Job('r')
    tui.job_refresh(state, [fake_device])(job)
    assert fake_device.firmware_reboot_pending is False
    assert state.info_fetched[fake_device.name] is True


def test_job_refresh_clears_info_fetched_upfront(state, fake_device):
    """info_fetched must be reset to False before the fetch so the UI
    doesn't show a stale snapshot while a refresh is running."""
    state.info_fetched[fake_device.name] = True
    fake_device.get_channel.return_value = 'stable'
    seen: list[bool] = []

    def watch_ssh_connect():
        seen.append(state.info_fetched.get(fake_device.name, False))

    fake_device.ssh_connect.side_effect = watch_ssh_connect
    job = tui.Job('r')
    tui.job_refresh(state, [fake_device])(job)
    assert seen == [False]
    assert state.info_fetched[fake_device.name] is True


def test_job_refresh_parallel_for_multiple_devices(state):
    """Refreshing multiple devices should fan out across a worker pool
    (cap = 3) so a slow router doesn't serialise the whole batch.

    We prove parallelism deterministically with a ``threading.Barrier``:
    if the pool actually runs work in parallel, ``parties=3`` workers
    will all reach the barrier and it releases. If the pool serialises,
    the barrier times out and BrokenBarrierError is raised.
    """
    # Exactly _REFRESH_MAX_PARALLEL devices so a single barrier trip
    # suffices; adding more would leave a short second batch that could
    # never fill the barrier and would time out.
    n = tui._REFRESH_MAX_PARALLEL
    barrier = threading.Barrier(parties=n, timeout=2.0)

    def connect_at_barrier():
        # Blocks until enough peers arrive (or the barrier times out).
        barrier.wait()

    devices = [
        _mock_device(name=f'r{i}', address=f'10.0.0.{i + 1}')
        for i in range(n)
    ]
    for d in devices:
        d.ssh_connect.side_effect = connect_at_barrier

    job = tui.Job('bulk')
    # If parallelism is broken, connect_at_barrier will raise
    # BrokenBarrierError, which _with_device surfaces via the job log.
    tui.job_refresh(state, devices)(job)

    for d in devices:
        assert state.info_fetched[d.name] is True
    assert not any(
        'BrokenBarrierError' in ln for ln in job.snapshot()
    ), 'refresh did not fan out concurrently'


def test_job_refresh_continues_on_per_device_error(state):
    """One device raising must not abort the batch for the others."""
    good = _mock_device(name='good', address='10.0.0.1')
    bad = _mock_device(name='bad', address='10.0.0.2')
    bad.ssh_connect.side_effect = RuntimeError('boom')

    job = tui.Job('bulk')
    tui.job_refresh(state, [bad, good])(job)
    assert state.info_fetched.get('good') is True
    assert any('ERROR on bad' in ln for ln in job.snapshot())


def test_job_apply_channel(state, fake_device):
    fake_device.get_channel.return_value = 'testing'
    job = tui.Job('c')
    tui.job_apply_channel(state, fake_device, 'testing')(job)
    fake_device.set_channel.assert_called_once_with('testing')
    assert state.info_fetched[fake_device.name] is True


def test_job_apply_channel_clears_info_fetched_upfront(state, fake_device):
    state.info_fetched[fake_device.name] = True
    fake_device.get_channel.return_value = 'testing'
    seen: list[bool] = []
    fake_device.ssh_connect.side_effect = (
        lambda: seen.append(state.info_fetched.get(fake_device.name, False))
    )
    job = tui.Job('c')
    tui.job_apply_channel(state, fake_device, 'testing')(job)
    assert seen == [False]
    assert state.info_fetched[fake_device.name] is True


def test_job_backup_success_and_failure(state, fake_device):
    job = tui.Job('b')
    fake_device.backup.return_value = True
    tui.job_backup(state, fake_device)(job)
    fake_device.backup.return_value = False
    tui.job_backup(state, fake_device)(job)
    text = '\n'.join(job.snapshot())
    assert 'backup + export OK' in text
    assert 'backup FAILED' in text


def test_job_update_paths(state, fake_device):
    # update available + firmware update
    fake_device.get_update_available.return_value = True
    fake_device.update_firmware = True
    job = tui.Job('u')
    tui.job_update(state, fake_device)(job)
    fake_device.update.assert_called_once()
    fake_device.firmware_update.assert_called_once()

    # no update available
    fake_device.reset_mock()
    fake_device.get_update_available.return_value = False
    fake_device.update_firmware = False
    job2 = tui.Job('u2')
    tui.job_update(state, fake_device)(job2)
    fake_device.update.assert_not_called()
    fake_device.firmware_update.assert_not_called()
    assert any(
        'no update available' in ln for ln in job2.snapshot()
    )


def test_job_stage_firmware_stages_and_noops(state, fake_device):
    # firmware differs -> stages
    fake_device.current_firmware = '7.15'
    fake_device.upgrade_firmware = '7.16'
    fake_device.firmware_reboot_pending = False
    job = tui.Job('f')
    tui.job_stage_firmware(state, fake_device)(job)
    fake_device.stage_firmware_upgrade.assert_called_once()
    assert fake_device.firmware_reboot_pending is True

    # firmware equal -> noop, clears pending
    fake_device.reset_mock()
    fake_device.current_firmware = '7.16'
    fake_device.upgrade_firmware = '7.16'
    fake_device.firmware_reboot_pending = True
    job2 = tui.Job('f2')
    tui.job_stage_firmware(state, fake_device)(job2)
    fake_device.stage_firmware_upgrade.assert_not_called()
    assert fake_device.firmware_reboot_pending is False


def test_job_reboot_clears_firmware_pending_on_success(state, fake_device):
    fake_device.firmware_reboot_pending = True
    fake_device.reboot_and_wait.return_value = True
    job = tui.Job('rb')
    tui.job_reboot(state, fake_device)(job)
    fake_device.reboot_and_wait.assert_called_once()
    assert fake_device.firmware_reboot_pending is False
    assert any('reboot complete' in ln for ln in job.snapshot())


def test_job_reboot_keeps_firmware_pending_on_timeout(state, fake_device):
    fake_device.firmware_reboot_pending = True
    fake_device.reboot_and_wait.return_value = False
    job = tui.Job('rb')
    tui.job_reboot(state, fake_device)(job)
    assert fake_device.firmware_reboot_pending is True
    assert any('timed out' in ln for ln in job.snapshot())


# ---------- YamlSelectScreen ----------


def test_yaml_select_draw_empty(state):
    s = tui.YamlSelectScreen(state)
    s.draw(FakeWin())


def test_yaml_select_draw_with_files(tmp_path):
    for i in range(10):
        (tmp_path / f'a{i}.yaml').write_text('x')
    st = tui.TuiState(str(tmp_path))
    s = tui.YamlSelectScreen(st)
    # cursor beyond visible bottom -> top adjusts forward
    s.cursor = 9
    s.draw(FakeWin(5, 40))
    # cursor above current top -> top adjusts backward
    s.top = 8
    s.cursor = 2
    s.draw(FakeWin(5, 40))
    # bigger window than the file list -> hits the break-past-end guard
    s.top = 0
    s.cursor = 0
    s.draw(FakeWin(40, 40))


def test_yaml_select_handle_quit_resize_jobs_rescan(state):
    s = tui.YamlSelectScreen(state)
    assert s.handle(FakeWin(), ord('q')) is None
    assert s.handle(FakeWin(), curses.KEY_RESIZE) is s
    assert s.handle(FakeWin(), -1) is s
    js = s.handle(FakeWin(), ord('j'))
    assert isinstance(js, tui.JobsScreen)
    assert s.handle(FakeWin(), ord('r')) is s


def test_yaml_select_no_files_ignores_navigation(state):
    s = tui.YamlSelectScreen(state)
    # no files; navigation keys should be no-ops but not error
    assert s.handle(FakeWin(), curses.KEY_DOWN) is s


def test_yaml_select_navigation_and_enter_load_success(tmp_path, monkeypatch):
    yaml_path = tmp_path / 'x.yaml'
    yaml_path.write_text('x')
    st = tui.TuiState(str(tmp_path))
    s = tui.YamlSelectScreen(st)

    # navigation branches
    s.handle(FakeWin(), curses.KEY_DOWN)
    s.handle(FakeWin(), curses.KEY_UP)
    s.handle(FakeWin(), ord('k'))
    s.handle(FakeWin(), curses.KEY_END)
    s.handle(FakeWin(), curses.KEY_HOME)

    fake_cm = MagicMock()
    fake_cm.check_config_file.return_value = True
    fake_cm.load_config.return_value = ([MagicMock(name='dev')], MagicMock())
    monkeypatch.setattr(tui, 'ConfigManager', lambda p: fake_cm)

    next_screen = s.handle(FakeWin(), curses.KEY_ENTER)
    assert isinstance(next_screen, tui.DevicesScreen)
    assert st.yaml_path == str(yaml_path)


def test_yaml_select_load_check_fails(tmp_path, monkeypatch):
    (tmp_path / 'x.yaml').write_text('x')
    st = tui.TuiState(str(tmp_path))
    s = tui.YamlSelectScreen(st)

    fake_cm = MagicMock()
    fake_cm.check_config_file.return_value = False
    monkeypatch.setattr(tui, 'ConfigManager', lambda p: fake_cm)
    monkeypatch.setattr(
        tui.curses, 'newwin', _armed_newwin_factory([ord(' ')]),
    )
    result = s.handle(FakeWin(), curses.KEY_ENTER)
    assert result is s


def test_yaml_select_load_raises(tmp_path, monkeypatch):
    (tmp_path / 'x.yaml').write_text('x')
    st = tui.TuiState(str(tmp_path))
    s = tui.YamlSelectScreen(st)

    fake_cm = MagicMock()
    fake_cm.check_config_file.side_effect = RuntimeError('bad')
    monkeypatch.setattr(tui, 'ConfigManager', lambda p: fake_cm)
    monkeypatch.setattr(
        tui.curses, 'newwin', _armed_newwin_factory([ord(' ')]),
    )
    assert s.handle(FakeWin(), curses.KEY_ENTER) is s


# ---------- DevicesScreen ----------


def _screen_with_devices(fake_device):
    other = _mock_device(
        name='ap', address='10.0.0.2',
        installed_version='?', latest_version='?',
        current_channel='?', current_firmware='?', upgrade_firmware='?',
        update_available=False,
    )
    st = tui.TuiState('/tmp')
    st.yaml_path = '/tmp/x.yaml'
    st.devices = [fake_device, other]
    return st, tui.DevicesScreen(st)


def test_devices_screen_draw_wide_and_narrow(fake_device):
    st, screen = _screen_with_devices(fake_device)
    # narrow — 2 rows per item
    screen.draw(FakeWin(24, 60))
    # wide — 1 row per item
    st.info_fetched[fake_device.name] = True
    fake_device.firmware_reboot_pending = True
    screen.draw(FakeWin(24, 120))
    # empty list
    st.devices = []
    screen.draw(FakeWin(24, 80))


def test_devices_screen_draw_scroll_and_overflow(fake_device):
    st, screen = _screen_with_devices(fake_device)
    # add many devices so cursor beyond bottom triggers scrolling and
    # the loop hits the break-past-end guard
    extras = [
        _mock_device(
            name=f'd{i}', address=f'10.0.1.{i}', identity='',
            installed_version='?', latest_version='?',
            current_channel='?', current_firmware='?',
            upgrade_firmware='?', update_available=False,
        )
        for i in range(20)
    ]
    st.devices = st.devices + extras
    screen.cursor = len(st.devices) - 1
    screen.draw(FakeWin(6, 60))  # scroll top forward
    screen.top = len(st.devices) - 1
    screen.cursor = 0
    screen.draw(FakeWin(6, 60))  # scroll top backward


def test_devices_screen_info_line_all_variants(state, fake_device):
    screen = tui.DevicesScreen(state)
    # not fetched
    assert 'no info' in screen._info_line(fake_device)
    # fetched, avail True
    state.info_fetched[fake_device.name] = True
    assert 'upd:yes' in screen._info_line(fake_device)
    # avail False
    fake_device.update_available = False
    assert 'upd:no' in screen._info_line(fake_device)
    # avail None (unknown)
    fake_device.update_available = None
    assert 'upd:?' in screen._info_line(fake_device)
    # firmware pending appended
    fake_device.firmware_reboot_pending = True
    assert 'REBOOT PENDING' in screen._info_line(fake_device)
    # missing identity path
    fake_device.identity = ''
    assert 'id:?' in screen._info_line(fake_device)


def test_devices_screen_handle_all_keys(fake_device, monkeypatch):
    st, screen = _screen_with_devices(fake_device)
    assert screen.handle(FakeWin(), ord('q')) is None
    assert screen.handle(FakeWin(), curses.KEY_RESIZE) is screen
    assert screen.handle(FakeWin(), -1) is screen
    assert isinstance(
        screen.handle(FakeWin(), ord('j')), tui.JobsScreen,
    )
    assert isinstance(
        screen.handle(FakeWin(), curses.KEY_BACKSPACE),
        tui.YamlSelectScreen,
    )

    st, screen = _screen_with_devices(fake_device)
    screen.handle(FakeWin(), curses.KEY_DOWN)
    screen.handle(FakeWin(), curses.KEY_UP)
    screen.handle(FakeWin(), ord('k'))
    screen.handle(FakeWin(), curses.KEY_END)
    screen.handle(FakeWin(), curses.KEY_HOME)
    screen.handle(FakeWin(), ord(' '))  # select
    screen.handle(FakeWin(), ord(' '))  # deselect
    screen.handle(FakeWin(), ord('a'))  # all
    screen.handle(FakeWin(), ord('n'))  # none

    # 'r' refresh with selected -> stays on screen, records last_refresh_job
    screen.handle(FakeWin(), ord('a'))
    monkeypatch.setattr(tui, 'job_refresh', lambda s, ds: (lambda job: None))
    assert screen.handle(FakeWin(), ord('r')) is screen
    assert screen.last_refresh_job is not None
    # 'r' refresh with none selected -> same behaviour
    screen.handle(FakeWin(), ord('n'))
    assert screen.handle(FakeWin(), ord('r')) is screen

    # Enter -> DeviceDetailScreen
    result = screen.handle(FakeWin(), curses.KEY_ENTER)
    assert isinstance(result, tui.DeviceDetailScreen)


def test_devices_screen_empty_ignores_nav(state):
    screen = tui.DevicesScreen(state)  # state has no devices
    assert screen.handle(FakeWin(), curses.KEY_DOWN) is screen


# ---------- DeviceDetailScreen ----------


def _detail_screen(fake_device):
    st = tui.TuiState('/tmp')
    st.devices = [fake_device]
    parent = tui.DevicesScreen(st)
    return st, parent, tui.DeviceDetailScreen(st, fake_device, parent)


def test_device_detail_info_lines_variants(fake_device):
    st, _, screen = _detail_screen(fake_device)
    # not fetched, no manual packages
    lines = screen._info_lines()
    assert any('info not fetched' in ln for ln in lines)
    # fetched + firmware pending + manual packages
    st.info_fetched[fake_device.name] = True
    fake_device.firmware_reboot_pending = True
    fake_device.update_type = 'manual'
    fake_device.packages = ['/tmp/a.npk']
    lines = screen._info_lines()
    assert any('Firmware upgrade staged' in ln for ln in lines)
    assert any('Packages:' in ln for ln in lines)


def test_device_detail_draw(fake_device):
    _, _, screen = _detail_screen(fake_device)
    screen.draw(FakeWin(24, 80))
    # tiny screen too — should not raise
    screen.draw(FakeWin(3, 20))


def test_device_detail_draw_hline_raises(fake_device):
    _, _, screen = _detail_screen(fake_device)

    class HlineFailWin(FakeWin):
        def hline(self, y, x, ch, n):
            raise curses.error('nope')

    screen.draw(HlineFailWin(24, 80))


def test_device_detail_handle_navigation(fake_device):
    st, parent, screen = _detail_screen(fake_device)
    assert screen.handle(FakeWin(), ord('q')) is None
    assert screen.handle(FakeWin(), curses.KEY_RESIZE) is screen
    assert screen.handle(FakeWin(), -1) is screen
    assert isinstance(screen.handle(FakeWin(), ord('j')), tui.JobsScreen)
    assert screen.handle(FakeWin(), curses.KEY_BACKSPACE) is parent
    screen.handle(FakeWin(), curses.KEY_DOWN)
    screen.handle(FakeWin(), curses.KEY_UP)
    screen.handle(FakeWin(), ord('k'))


def test_device_detail_action_invocations(fake_device, monkeypatch):
    st, _, screen = _detail_screen(fake_device)

    # Refresh: no popup, just submits
    submitted = []
    monkeypatch.setattr(
        st.jobs, 'submit',
        lambda name, target: submitted.append(name) or tui.Job(name),
    )
    screen.act_refresh(FakeWin())
    assert submitted[-1].startswith('refresh ')

    # Channel: cancel via popup_select
    monkeypatch.setattr(tui, 'popup_select', lambda *a, **k: None)
    screen.act_channel(FakeWin())
    # Channel: pick, but confirm=no
    monkeypatch.setattr(tui, 'popup_select', lambda *a, **k: 'testing')
    monkeypatch.setattr(tui, 'popup_confirm', lambda *a, **k: False)
    screen.act_channel(FakeWin())
    # Channel: pick + confirm
    monkeypatch.setattr(tui, 'popup_confirm', lambda *a, **k: True)
    screen.act_channel(FakeWin())
    assert fake_device.online_update_channel == 'testing'

    # Backup: cancel
    monkeypatch.setattr(tui, 'popup_confirm', lambda *a, **k: False)
    screen.act_backup(FakeWin())
    # Backup: confirm
    monkeypatch.setattr(tui, 'popup_confirm', lambda *a, **k: True)
    screen.act_backup(FakeWin())

    # Update: cancel + confirm
    monkeypatch.setattr(tui, 'popup_confirm', lambda *a, **k: False)
    screen.act_update(FakeWin())
    monkeypatch.setattr(tui, 'popup_confirm', lambda *a, **k: True)
    screen.act_update(FakeWin())

    # Stage FW: cancel + confirm
    monkeypatch.setattr(tui, 'popup_confirm', lambda *a, **k: False)
    screen.act_stage_fw(FakeWin())
    monkeypatch.setattr(tui, 'popup_confirm', lambda *a, **k: True)
    screen.act_stage_fw(FakeWin())

    # Reboot: cancel + confirm
    monkeypatch.setattr(tui, 'popup_confirm', lambda *a, **k: False)
    screen.act_reboot(FakeWin())
    monkeypatch.setattr(tui, 'popup_confirm', lambda *a, **k: True)
    screen.act_reboot(FakeWin())


def test_device_detail_enter_runs_action(fake_device, monkeypatch):
    _, _, screen = _detail_screen(fake_device)
    called = []
    # action returns None -> stay on the detail screen
    screen.actions = [('t', lambda s: called.append(1) or None)]
    screen.cursor = 0
    result = screen.handle(FakeWin(), curses.KEY_ENTER)
    assert called == [1]
    assert result is screen


def test_device_detail_enter_records_last_job_and_stays(fake_device):
    _, _, screen = _detail_screen(fake_device)
    job = tui.Job('t')
    screen.actions = [('t', lambda s: job)]
    screen.cursor = 0
    result = screen.handle(FakeWin(), curses.KEY_ENTER)
    assert result is screen
    assert screen.last_job is job


def test_job_status_line_variants():
    assert tui._job_status_line(None) == ''
    job = tui.Job('t')
    running = tui._job_status_line(job)
    assert '▶' in running and 'running' in running
    job.status = 'done'
    job.finished = job.started + 1
    done = tui._job_status_line(job)
    assert '✓' in done and 'success' in done
    job.status = 'error'
    job.error = 'boom'
    err = tui._job_status_line(job)
    assert '✗' in err and 'FAILED' in err and 'boom' in err
    job.status = 'weird'
    other = tui._job_status_line(job)
    assert '?' in other


def test_devices_screen_draws_status_line(fake_device):
    st, screen = _screen_with_devices(fake_device)
    screen.last_refresh_job = tui.Job('r')
    screen.last_refresh_job.status = 'done'
    screen.last_refresh_job.finished = screen.last_refresh_job.started + 1
    win = FakeWin(24, 120)
    screen.draw(win)
    rendered = [c for c in win.calls if c[0] == 'addstr']
    assert any('success' in c[3] for c in rendered)


def test_devices_screen_draws_status_line_when_empty(state):
    screen = tui.DevicesScreen(state)
    screen.last_refresh_job = tui.Job('r')
    screen.last_refresh_job.status = 'error'
    screen.last_refresh_job.error = 'nope'
    win = FakeWin(24, 80)
    screen.draw(win)
    rendered = [c for c in win.calls if c[0] == 'addstr']
    assert any('FAILED' in c[3] for c in rendered)


def test_device_detail_draws_status_line(fake_device):
    _, _, screen = _detail_screen(fake_device)
    job = tui.Job('backup router')
    job.status = 'done'
    job.finished = job.started + 0.5
    screen.last_job = job
    win = FakeWin(24, 80)
    screen.draw(win)
    rendered = [c for c in win.calls if c[0] == 'addstr']
    assert any(
        'backup router' in c[3] and 'success' in c[3] for c in rendered
    )


# ---------- JobsScreen ----------


def test_jobs_screen_empty(state):
    screen = tui.JobsScreen(state, MagicMock())
    screen.draw(FakeWin())
    assert screen.handle(FakeWin(), ord('c')) is screen
    assert screen.handle(FakeWin(), ord('q')) is None
    assert screen.handle(FakeWin(), curses.KEY_RESIZE) is screen
    assert screen.handle(FakeWin(), -1) is screen
    parent = screen.parent
    assert screen.handle(FakeWin(), ord('j')) is parent
    assert screen.handle(FakeWin(), curses.KEY_BACKSPACE) is parent


def test_jobs_screen_with_jobs(state):
    # add jobs of every status
    done_job = tui.Job('done')
    done_job.status = 'done'
    done_job.finished = done_job.started + 1
    err_job = tui.Job('err')
    err_job.status = 'error'
    err_job.finished = err_job.started + 2
    run_job = tui.Job('running')
    unknown = tui.Job('unk')
    unknown.status = 'weird'
    state.jobs.jobs.extend([done_job, err_job, run_job, unknown])
    # bigger window than the job list first -> hits the break-past-end
    parent0 = MagicMock()
    tui.JobsScreen(state, parent0).draw(FakeWin(40, 80))
    # extras to force scrolling
    for i in range(15):
        j = tui.Job(f'j{i}')
        j.status = 'done'
        j.finished = j.started + 0.1
        state.jobs.jobs.append(j)

    parent = MagicMock()
    screen = tui.JobsScreen(state, parent)
    # tiny window forces cursor clamp
    screen.cursor = 99
    screen.draw(FakeWin(5, 60))
    # bigger window renders all jobs including the error one (A_BOLD)
    screen.cursor = 0
    screen.draw(FakeWin(20, 80))
    # top adjust backward: top ahead of cursor
    screen.top = 10
    screen.cursor = 0
    screen.draw(FakeWin(5, 60))

    # nav
    screen.cursor = 0
    screen.handle(FakeWin(), curses.KEY_DOWN)
    screen.handle(FakeWin(), curses.KEY_UP)
    screen.handle(FakeWin(), ord('k'))
    screen.handle(FakeWin(), curses.KEY_END)
    screen.handle(FakeWin(), curses.KEY_HOME)

    # 'c' clears finished
    screen.handle(FakeWin(), ord('c'))
    assert all(j.status == 'running' for j in state.jobs.all())

    # Enter -> log screen
    result = screen.handle(FakeWin(), curses.KEY_ENTER)
    assert isinstance(result, tui.JobLogScreen)


# ---------- JobLogScreen ----------


def test_job_log_screen_draw_and_handle(state):
    job = tui.Job('l')
    for i in range(50):
        job.write(f'line {i} ' + 'x' * 200)
    parent = MagicMock()
    parent.parent = MagicMock()
    screen = tui.JobLogScreen(state, job, parent)

    # follow mode
    screen.draw(FakeWin(10, 40))
    # cursor scrolling disables follow
    screen.handle(FakeWin(), curses.KEY_UP)
    assert screen.follow is False
    screen.handle(FakeWin(), curses.KEY_DOWN)
    screen.handle(FakeWin(), curses.KEY_PPAGE)
    screen.handle(FakeWin(), curses.KEY_NPAGE)
    screen.handle(FakeWin(), curses.KEY_HOME)
    screen.handle(FakeWin(), curses.KEY_END)  # follow back on
    assert screen.follow is True
    screen.handle(FakeWin(), ord('f'))
    assert screen.follow is True

    # nav to jobs / parent / quit
    assert screen.handle(FakeWin(), ord('q')) is None
    assert screen.handle(FakeWin(), curses.KEY_RESIZE) is screen
    assert screen.handle(FakeWin(), -1) is screen
    assert screen.handle(FakeWin(), curses.KEY_BACKSPACE) is parent
    result = screen.handle(FakeWin(), ord('j'))
    assert isinstance(result, tui.JobsScreen)

    # parent without .parent attribute -> falls back to parent
    plain_parent = object()
    screen2 = tui.JobLogScreen(state, job, plain_parent)
    result2 = screen2.handle(FakeWin(), ord('j'))
    assert isinstance(result2, tui.JobsScreen)


def test_job_log_screen_handles_empty_lines_in_log(state):
    job = tui.Job('l')
    with job.lock:
        job.lines.append('')  # bare empty line in the buffer
        job.lines.append('non-empty')
    parent = MagicMock()
    screen = tui.JobLogScreen(state, job, parent)
    screen.draw(FakeWin(10, 40))


# ---------- entry ----------


def test_run_loop_advances_through_screens(state, monkeypatch):
    stdscr = FakeWin(24, 80)
    monkeypatch.setattr(tui.curses, 'curs_set', lambda n: None)
    # queue keys: 'q' quits from YamlSelect (no files present)
    stdscr.queue(ord('q'))
    tui._run(stdscr, state)
    assert stdscr.timeout_val == 500


def test_main_missing_directory(capsys):
    rc = tui.main(['-d', '/no/such/dir/at/all'])
    assert rc == 1
    assert 'not found' in capsys.readouterr().out


def test_main_success(monkeypatch, tmp_path):
    def fake_wrapper(func, *args, **kwargs):
        func(FakeWin(), *args, **kwargs)

    monkeypatch.setattr(tui.curses, 'wrapper', fake_wrapper)
    monkeypatch.setattr(tui.curses, 'curs_set', lambda n: None)
    # Provide a key for _run's initial getch
    monkeypatch.setattr(
        tui.YamlSelectScreen, 'draw', lambda self, s: None,
    )

    calls = {'i': 0}

    def fake_handle(self, stdscr, ch):
        calls['i'] += 1
        return None  # quit immediately

    monkeypatch.setattr(tui.YamlSelectScreen, 'handle', fake_handle)
    rc = tui.main(['-d', str(tmp_path)])
    assert rc == 0
    assert calls['i'] == 1


def test_main_keyboard_interrupt(monkeypatch, tmp_path):
    def fake_wrapper(func, *args, **kwargs):
        raise KeyboardInterrupt

    monkeypatch.setattr(tui.curses, 'wrapper', fake_wrapper)
    assert tui.main(['-d', str(tmp_path)]) == 0


def test_main_py_executed_as_script(monkeypatch):
    import runpy
    monkeypatch.setattr(sys, 'argv', ['mu_tui', '-d', '/no/such/at/all'])
    with pytest.raises(SystemExit) as ei:
        runpy.run_module('mu_tui.main', run_name='__main__')
    assert ei.value.code == 1


def test_dunder_main_executed_as_script(monkeypatch):
    import runpy
    monkeypatch.setattr(sys, 'argv', ['mu_tui', '-d', '/no/such/at/all'])
    with pytest.raises(SystemExit) as ei:
        runpy.run_module('mu_tui', run_name='__main__')
    assert ei.value.code == 1
