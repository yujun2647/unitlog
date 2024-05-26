import logging
import multiprocessing as mp


class LogBox(object):
    def __init__(self, log_msg, log_type="console",
                 log_filepath="", file_mode="a"):
        self.log_msg = log_msg
        self.log_type = log_type
        self.log_filepath = log_filepath
        self.file_mode = file_mode


class UnitHandler(logging.StreamHandler):
    LOG_TYPE = "console"
    DEFAULT_LOG_QUEUE = mp.Queue()

    def handle(self, record):
        """ without acquiring lock
        """
        rv = self.filter(record)
        if rv:
            self.emit(record)
            # self.acquire()
            # try:
            #     self.emit(record)
            # finally:
            #     self.release()
        return rv

    def wrap_msg(self, log_msg) -> LogBox:
        return LogBox(log_msg=log_msg, log_type=self.LOG_TYPE)

    def emit(self, record):
        """ send to queue
        """
        # noinspection PyBroadException
        try:
            msg = self.format(record)
            # issue 35046: merged two stream.writes into one.
            log_msg = msg + self.terminator
            UnitHandler.DEFAULT_LOG_QUEUE.put(self.wrap_msg(log_msg))
        except RecursionError:  # See issue 36272
            raise
        except Exception:
            self.handleError(record)


class UnitConsoleHandler(UnitHandler):
    LOG_TYPE = "console"


class UnitFileHandler(UnitHandler):
    LOG_TYPE = "file"

    def __init__(self, log_filepath, mode):
        super().__init__()
        self.log_filepath = log_filepath
        self.mode = mode

    def wrap_msg(self, log_msg) -> LogBox:
        return LogBox(log_msg=log_msg, log_type=self.LOG_TYPE,
                      log_filepath=self.log_filepath,
                      file_mode=self.mode)
