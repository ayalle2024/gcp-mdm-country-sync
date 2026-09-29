import json
import logging
import os
import sys


class JsonFormatter(logging.Formatter):
    def __init__(self, fmt=None, datefmt=None, style="%"):
        super().__init__(fmt=fmt, datefmt=datefmt, style=style)
        self.fmt = fmt

    def format(self, record):
        record.asctime = self.formatTime(record, self.datefmt)

        if record.exc_info:
            message = record.getMessage() + "\n" + self.formatException(record.exc_info)
        else:
            message = record.getMessage()

        formatted_message = self.fmt % {
            "asctime": record.asctime,
            "name": record.name,
            "levelname": record.levelname,
            "message": message,
        }

        log_record = {
            "severity": record.levelname,
            "message": formatted_message,
        }

        return json.dumps(log_record, ensure_ascii=False)


def create_json_handler(fmt=None, datefmt=None, style="%", level="INFO"):
    handler = logging.StreamHandler(sys.stdout)
    handler.setLevel(getattr(logging, level))
    handler.setFormatter(JsonFormatter(fmt=fmt, datefmt=datefmt, style=style))
    return handler


def create_std_handler(fmt=None, datefmt=None, style="%", level="INFO"):
    handler = logging.StreamHandler(sys.stdout)
    handler.setLevel(getattr(logging, level))
    handler.setFormatter(logging.Formatter(fmt=fmt, datefmt=datefmt))
    return handler


class GCPLogger(logging.Logger):
    def __init__(self, name: str, level="INFO") -> None:
        super().__init__(name, level)
        self.propagate = False

        log_format = "%(levelname)s - [%(asctime)s] - [%(name)s] - %(message)s"
        log_ts_format = "%Y-%m-%d %H:%M:%S"

        if not self.handlers:
            if self.is_running_on_cloudrun():
                self.addHandler(
                    create_json_handler(
                        fmt=log_format,
                        datefmt=log_ts_format,
                    )
                )
            else:
                self.addHandler(
                    create_std_handler(
                        fmt=log_format,
                        datefmt=log_ts_format,
                    )
                )

    @staticmethod
    def is_running_on_cloudrun() -> bool:
        return bool(os.getenv("K_SERVICE"))

    @classmethod
    def get_logger(cls, name: str, level="INFO") -> "GCPLogger":
        previous_logger_class = logging.getLoggerClass()

        logging.setLoggerClass(cls)
        logger = logging.getLogger(name)
        logger.setLevel(level)

        logging.setLoggerClass(previous_logger_class)

        return logger  # type: ignore
