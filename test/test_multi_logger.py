import os
import logging

import multiprocessing as mp
import time

from threading import Thread
from unitlog.unit import register_logger, DEFAULT_LOG
from unittest import TestCase

os.environ["ENV-TEST"] = "test"

logger1 = logging.getLogger("test1")
logger2 = logging.getLogger("test2")
logger3 = logging.getLogger("test3")


def test_thread(start=0, end=100):
    for i in range(start, end):
        logger1.info(i)


def test_thread2(start=0, end=100):
    for i in range(start, end):
        logger2.info(i)


def test_thread3(start=0, end=100):
    for i in range(start, end):
        logger3.info(i)


class TestMultiLogger(TestCase):

    def setUp(self):
        DEFAULT_LOG.log_num.value = 0
        logger1.parent = None
        logger1.propagate = False
        logger2.parent = None
        logger2.propagate = False
        logger3.parent = None
        logger3.propagate = False
        logger1.handlers.clear()
        logger2.handlers.clear()
        logger3.handlers.clear()

    def test_multi_logger(self):
        register_logger(name=logger1.name, file_log=True,
                        log_filepath="./temp/test_logger1.log")
        register_logger(name=logger2.name, file_log=True,
                        log_filepath="./temp/test_logger2.log",
                        parent_logger_name=logger1.name)
        register_logger(name=logger3.name, file_log=True,
                        log_filepath="./temp/test_logger3.log",
                        parent_logger_name=logger2.name)

        Thread(target=test_thread, args=(1, 101)).start()
        Thread(target=test_thread, args=(101, 201)).start()
        Thread(target=test_thread2, args=(201, 301)).start()
        Thread(target=test_thread2, args=(301, 401)).start()
        mp.Process(target=test_thread3, args=(401, 501)).start()
        mp.Process(target=test_thread3, args=(501, 601)).start()
        time.sleep(1)

        expect_log_num = 201 * 2 + 201 * 2 * 2 + 201 * 2 * 3
        assert DEFAULT_LOG.log_num.value == expect_log_num, \
            f"log num is {DEFAULT_LOG.log_num.value}"

    def test_multi_worker(self):
        logger = register_logger(name=logger1.name)

        Thread(target=test_thread, args=(1, 101)).start()
        Thread(target=test_thread, args=(101, 201)).start()
        Thread(target=test_thread, args=(201, 301)).start()
        Thread(target=test_thread, args=(301, 401)).start()
        mp.Process(target=test_thread, args=(401, 501)).start()
        mp.Process(target=test_thread, args=(501, 601)).start()
        mp.Process(target=test_thread, args=(601, 701)).start()
        mp.Process(target=test_thread, args=(701, 801)).start()
        mp.Process(target=test_thread, args=(801, 901)).start()
        mp.Process(target=test_thread, args=(901, 1001)).start()

        time.sleep(1)
        assert DEFAULT_LOG.log_num.value == 1000, \
            f"log num is {DEFAULT_LOG.log_num.value}"

    def test_multi_worker_with_file_log(self):
        register_logger(
            name=logger1.name, file_log=True,
            log_filepath="./temp/multi_worker_with_file_log.log")

        Thread(target=test_thread, args=(1, 101)).start()
        Thread(target=test_thread, args=(101, 201)).start()
        Thread(target=test_thread, args=(201, 301)).start()
        Thread(target=test_thread, args=(301, 401)).start()
        mp.Process(target=test_thread, args=(401, 501)).start()
        mp.Process(target=test_thread, args=(501, 601)).start()
        mp.Process(target=test_thread, args=(601, 701)).start()
        mp.Process(target=test_thread, args=(701, 801)).start()
        mp.Process(target=test_thread, args=(801, 901)).start()
        mp.Process(target=test_thread, args=(901, 1001)).start()

        time.sleep(1)
        assert DEFAULT_LOG.log_num.value == 2002, \
            f"log num is {DEFAULT_LOG.log_num.value}"
