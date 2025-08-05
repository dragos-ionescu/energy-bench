from abc import ABC, abstractmethod
from dotenv import load_dotenv
import argparse
import logging
import time
import os

from utils import format_time, elapsed_time


def positive_int(value):
    ivalue = int(value)
    if ivalue < 0:
        raise argparse.ArgumentTypeError(f"{value} is not a positive integer")
    return ivalue


class BaseCommand(ABC):
    registry = {}
    name: str | None = None
    help: str = ""

    def __init_subclass__(cls, **kwargs):
        super().__init_subclass__(**kwargs)
        cls.name = cls.name or cls.__name__.lower()
        BaseCommand.registry[cls.name] = cls

    def __init__(self, base_dir) -> None:
        self.base_dir = base_dir
        self.error_count = self.warning_count = 0
        self.timestamp = time.time()

        self.log_path = os.path.join(self.base_dir, "logs.txt")
        self.logger = logging.getLogger("EnergyBench")
        logging.basicConfig(
            filename=self.log_path, level=logging.INFO, format="[%(levelname)s] %(message)s"
        )

        load_dotenv()

    def record_issue(self, msg: str, is_error: bool):
        if is_error:
            self.error_count += 1
            self.logger.error(msg)
            exit(self.error_count)
        else:
            self.warning_count += 1
            self.logger.warning(msg)

    def goodbye(self) -> None:
        end = time.time()
        formatted = format_time(end)
        elapsed = elapsed_time(end - self.timestamp)
        err = self.error_count
        warn = self.warning_count
        err_color = "\033[32m" if err == 0 else "\033[31m"
        warn_color = "\033[1m" if warn == 0 else "\033[33m"
        print(
            f"\033[1mEnded\033[0m {formatted} "
            f"\033[1mTotal Time\033[0m {elapsed} "
            f"\033[1mErrors\033[0m {err_color}{err}\033[0m "
            f"\033[1mWarnings\033[0m {warn_color}{warn}\033[0m\n"
        )

    @abstractmethod
    def add_args(self, parser: argparse.ArgumentParser) -> None:
        ...

    @abstractmethod
    def handle(self, args: argparse.Namespace) -> None:
        ...
