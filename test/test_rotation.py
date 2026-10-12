import os
import time
import datetime

from unitlog.unit import PoxyFileLogWriter
from unitlog.handlers import UnitFileHandler

DATE_FORMAT = "%Y-%m-%d"


def _make_file(path, content="x\n", age_days=0):
    with open(path, "w", encoding="utf-8") as f:
        f.write(content)
    if age_days:
        old = time.time() - age_days * 24 * 3600
        os.utime(path, (old, old))
    return path


def test_rotate_on_date_change(tmp_path):
    log_path = str(tmp_path / "app.log")
    writer = PoxyFileLogWriter(log_path, keep_days=7)
    try:
        writer.emit("today\n")

        yesterday = datetime.date.today() - datetime.timedelta(days=1)
        writer._current_period = yesterday  # 模拟跨天
        writer.emit("tomorrow\n")

        rotated = "{}.{}".format(log_path, yesterday.strftime(DATE_FORMAT))
        assert os.path.exists(rotated)
        with open(rotated, encoding="utf-8") as f:
            assert f.read() == "today\n"
        with open(log_path, encoding="utf-8") as f:
            assert f.read() == "tomorrow\n"
    finally:
        writer.stream.close()


def test_cleanup_removes_files_older_than_keep_days(tmp_path):
    log_path = str(tmp_path / "app.log")
    expired = _make_file(str(tmp_path / ("app.log.2026-01-01")), age_days=10)
    fresh = _make_file(str(tmp_path / ("app.log.2026-01-09")), age_days=1)

    writer = PoxyFileLogWriter(log_path, keep_days=7)
    try:
        assert not os.path.exists(expired)
        assert os.path.exists(fresh)
    finally:
        writer.stream.close()


def test_cleanup_ignores_foreign_files(tmp_path):
    log_path = str(tmp_path / "app.log")
    foreign = _make_file(str(tmp_path / "other.log.2026-01-01"), age_days=30)
    backup = _make_file(str(tmp_path / "app.log.bak"), age_days=30)
    not_date = _make_file(str(tmp_path / "app.log.20260101"), age_days=30)

    writer = PoxyFileLogWriter(log_path, keep_days=7)
    try:
        assert os.path.exists(foreign)
        assert os.path.exists(backup)
        assert os.path.exists(not_date)
    finally:
        writer.stream.close()


def test_disable_rotation_and_cleanup(tmp_path):
    log_path = str(tmp_path / "app.log")
    expired = _make_file(str(tmp_path / "app.log.2026-01-01"), age_days=30)

    writer = PoxyFileLogWriter(log_path, keep_days=0, rotate=False)
    try:
        writer.emit("today\n")
        yesterday = datetime.date.today() - datetime.timedelta(days=1)
        writer._current_period = yesterday
        writer.emit("tomorrow\n")

        assert os.path.exists(expired)
        assert not os.path.exists(
            "{}.{}".format(log_path, yesterday.strftime(DATE_FORMAT)))
        with open(log_path, encoding="utf-8") as f:
            assert f.read() == "today\ntomorrow\n"
    finally:
        writer.stream.close()


def test_rotation_options_travel_with_log_box():
    handler = UnitFileHandler("/tmp/unitlog_test.log", mode="a",
                              bus_queue=None, rotate=False, keep_days=3)
    box = handler.wrap_msg("msg")
    assert box.log_filepath == "/tmp/unitlog_test.log"
    assert box.file_log_rotate is False
    assert box.file_log_keep_days == 3


def test_proxy_handler_receives_rotation_options(tmp_path):
    from unitlog.unit import UnitLog
    from unitlog.handlers import LogBox

    log_path = str(tmp_path / "app.log")
    unit_log = UnitLog()  # 只构造，不启动日志子进程
    box = LogBox(log_msg="m", log_type="file", log_filepath=log_path,
                 file_log_rotate=True, file_log_keep_days=3)

    writer = unit_log._init_proxy_handler(box)
    try:
        assert writer.rotate is True
        assert writer.keep_days == 3
    finally:
        writer.stream.close()
