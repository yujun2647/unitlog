import os
import sys
import atexit
import logging
import traceback
from queue import Empty
import multiprocessing as mp
from multiprocessing.synchronize import Event

from unitlog.handlers import (LogBox, UnitHandler, UnitFileHandler,
                              UnitConsoleHandler)


class PoxyConsoleLogWriter(object):

    def __init__(self, stream=sys.stdout):
        self.stream = stream

    def emit(self, log_msg):
        self.stream.write(log_msg)
        self.stream.flush()

    def close(self):
        self.stream.close()


class PoxyFileLogWriter(PoxyConsoleLogWriter):
    def __init__(self, log_filepath, file_mode="a"):
        super().__init__(stream=open(log_filepath, file_mode))


class UnitLog(object):

    def __init__(self):
        self.started: Event = mp.Event()
        self.stopped: Event = mp.Event()
        self.log_num = mp.Value('i', 0)
        self.worker = mp.Process(target=self.listening_log_msg, daemon=False)
        self._proxy_handler_map = {}

    def _init_proxy_handler(self, log_box: LogBox) -> PoxyConsoleLogWriter:
        hkey = f"{log_box.log_type}-{log_box.log_filepath}"
        if hkey not in self._proxy_handler_map:
            if log_box.log_type == "console":
                self._proxy_handler_map[hkey] = PoxyConsoleLogWriter()
            elif log_box.log_type == "file":
                abs_log_filepath = os.path.abspath(log_box.log_filepath)
                dir_path = os.path.dirname(abs_log_filepath)
                if not os.path.exists(dir_path):
                    os.makedirs(dir_path, exist_ok=True)

                self._proxy_handler_map[hkey] = PoxyFileLogWriter(
                    log_filepath=abs_log_filepath,
                    file_mode=log_box.file_mode
                )
            else:
                raise TypeError(f"Unsupported log type: {log_box.log_type}")
        return self._proxy_handler_map[hkey]

    def listening_log_msg(self):
        while True:
            self.started.set()
            try:
                log_box: LogBox = UnitHandler.DEFAULT_LOG_QUEUE.get(timeout=0.1)
            except Empty:
                if self.stopped.is_set():
                    break
                continue
            try:
                handler = self._init_proxy_handler(log_box)

                handler.emit(log_box.log_msg)
                if os.environ.get("ENV-TEST", "prod") == "test":
                    self.log_num.value += 1
            except Exception as e:
                print(f"unexpect exception: {e}\n "
                      f"{traceback.format_exc()}")
        if os.environ.get("ENV-TEST", "prod") == "test":
            print(f"all log num: {self.log_num.value}")

    def register_logger(self, name, level=logging.INFO,
                        console_log=True, file_log=False, file_log_mode="a",
                        log_filepath=None,
                        parent_logger_name=None) -> logging.Logger:
        if not self.started.is_set():
            self.worker.start()
            if not self.started.wait(timeout=3):
                raise ValueError("unit log process is not started")

        logger = logging.getLogger(name)
        logger.setLevel(level)
        if parent_logger_name is not None:
            parent_logger = logging.getLogger(parent_logger_name)
            logger.parent = parent_logger
            logger.propagate = True
        else:
            logger.propagate = False

        simple_formatter = logging.Formatter(
            fmt="%(asctime)s [line:%(lineno)d] %(levelname)s %(message)s",
            datefmt="%a, %d %b %Y %H:%M:%S"
        )
        full_formatter = logging.Formatter(
            fmt="%(asctime)s %(filename)s [line:%(lineno)d] %(levelname)s "
                "%(message)s",
            datefmt="%a, %d %b %Y %H:%M:%S"
        )
        if console_log:
            console_handler = UnitConsoleHandler()
            console_handler.setFormatter(simple_formatter)
            logger.handlers.append(console_handler)
        if file_log:
            assert log_filepath, "log_filepath must be set"
            file_handler = UnitFileHandler(log_filepath, mode=file_log_mode)
            file_handler.setFormatter(full_formatter)
            logger.handlers.append(file_handler)
            logger.info("\nLog_filename: {}".format(log_filepath))

        return logger


DEFAULT_LOG = UnitLog()

register_logger = DEFAULT_LOG.register_logger
atexit.register(lambda: DEFAULT_LOG.stopped.set())

if __name__ == "__main__":
    import time

    _logger = logging.getLogger("test")
    register_logger(name="test", level=logging.DEBUG,
                    log_filepath="./temp/test.log")
    _logger.info("lllll")
