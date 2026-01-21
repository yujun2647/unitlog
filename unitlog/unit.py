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
        self.worker = mp.Process(target=self.listening_log_msg, daemon=True)
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
            except KeyboardInterrupt:
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
                        parent_logger_name=None,
                        force_all_console_log_to_file=False) -> logging.Logger:
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

            if force_all_console_log_to_file: # 强制控制所有标准输出到 文件
                self.force_all_console_log_to_file(log_filepath)

        return logger


    @classmethod
    def force_all_console_log_to_file(cls, log_filepath):
        # ==========================================
        # 新增函数：重定向底层 C/C++ 输出
        # ==========================================
        def _redirect_c_libraries_output(log_path):
            """
            使用 os.dup2 强制将底层 C/C++ 的 stdout/stderr 重定向到日志文件。
            解决 sherpa-onnx, PyQt, OpenCV 等 C 库打印无法被 Python 捕获的问题。
            """
            # 1. 打开日志文件 (使用 append 模式)
            # 这里的 buffer 设置为 0 (unbuffered) 或者 line buffered，确保 C 代码崩溃前能写入
            try:
                # 打开文件获取文件描述符
                # distinct file object specifically for low-level redirection
                log_file = open(log_path, 'a+')
                log_fd = log_file.fileno()

                # 2. 刷新 Python 的缓冲区，防止重定向导致之前的日志丢失
                sys.stdout.flush()
                sys.stderr.flush()

                # 3. 核心：重定向 FD 1 (stdout) 和 FD 2 (stderr)
                # 这一步之后，所有的 C printf/std::cout 都会直接写进文件
                os.dup2(log_fd, 1)
                os.dup2(log_fd, 2)

                # 保持 log_file 对象引用，防止被垃圾回收导致 FD 关闭
                return log_file
            except Exception as e:
                print(f"Failed to redirect C logs: {e}")
                return None

        class Logger(object):
            def __init__(self, filename):
                self.terminal = sys.stdout  # 记录原来的控制台，防止 IDE 里看不到了
                self.log = open(filename, "a", encoding="utf-8")  # 'a' 追加模式

            def write(self, message):
                # 1. 尝试写回控制台（方便开发调试）
                try:
                    if self.terminal:
                        self.terminal.write(message)
                except:
                    pass  # 打包成 no console 后这里可能会报错，直接忽略

                # 2. 写入文件
                try:
                    self.log.write(message)
                    # 【关键】立即刷新缓冲区，否则崩溃瞬间可能来不及写入文件
                    self.log.flush()
                except:
                    pass

            def flush(self):
                # 兼容性函数，必须保留
                try:
                    if self.terminal:
                        self.terminal.flush()
                    self.log.flush()
                except:
                    pass

        # 3. 【关键改动】区分环境进行重定向
        # 判断是否是打包后的环境
        # 逻辑：如果是 PyInstaller 打包 (frozen) 或者 环境变量 MIT_LOG=1，都视为需要重定向
        FORCE_ALL_CONSOLE_LOG_TO_FILE = os.environ.get("FORCE_ALL_CONSOLE_LOG_TO_FILE") == "1"
        IS_FROZEN = getattr(sys, 'frozen', False) or FORCE_ALL_CONSOLE_LOG_TO_FILE
        print(f"FORCE_ALL_CONSOLE_LOG_TO_FILE: {FORCE_ALL_CONSOLE_LOG_TO_FILE} \t IS_FROZEN: {IS_FROZEN}")

        if IS_FROZEN:
            # --- 打包环境 (Exe) ---
            # 1. 接管 Python 层面 (你原来的做法)
            sys.stdout = Logger(log_filepath)
            sys.stderr = sys.stdout

            # 2. 接管 C/C++ 层面 (新增的做法)
            # 这会让 sherpa-onnx 的报错也进文件
            # 注意：在 Linux/Mac 上非常有效，Windows 上通常也有效
            _c_log_ref = _redirect_c_libraries_output(log_filepath)

            print(f"Native C++ stdout/stderr redirected to {log_filepath}")

        else:
            # --- 开发环境 (IDE) ---
            # 在开发时，我们通常不希望 C++ 输出消失在控制台
            # 所以这里我们 *只* 使用你原来的 Logger 记录 Python print
            # 这样 IDE 控制台里既能看到 Python print，也能看到 C++ print (IDE 会自己捕获 FD)
            # 同时 Python print 也会被写入文件

            # 如果你确实希望开发时文件里也有 sherpa-onnx 的日志，
            # 你可以把上面的 redirect_c_libraries_output 打开，
            # 但代价是你的 PyCharm 控制台里那行红色的警告会消失。
            sys.stdout = Logger(log_filepath)
            sys.stderr = sys.stdout

DEFAULT_LOG = UnitLog()

register_logger: UnitLog.register_logger = DEFAULT_LOG.register_logger
atexit.register(lambda: DEFAULT_LOG.stopped.set())

if __name__ == "__main__":
    import time

    _logger = logging.getLogger("test")
    register_logger(name="test", level=logging.DEBUG,
                    log_filepath="./temp/test.log")
    _logger.info("lllll")
