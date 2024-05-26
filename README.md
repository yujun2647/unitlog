# unitlog

## About

manage log sending through one process

## Usage

```python
import logging

from unitlog.unit import register_logger

logger1 = logging.getLogger("test1")

register_logger(name=logger1.name, file_log=True,
                log_filepath="./temp/test1.log")

logger1.info("hello")

```
