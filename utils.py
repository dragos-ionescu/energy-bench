from datetime import datetime, timezone
from typing import Any
from glob import glob
import subprocess
import os

import yaml


def str_presenter(dumper, data):
    return dumper.represent_scalar("tag:yaml.org,2002:str", data, style="|")


yaml.add_representer(str, str_presenter)


class ProgramError(Exception):
    def __init__(self, failed: str | None = None, ex: Exception | None = None, *args) -> None:
        self.failed = failed
        self.ex = ex
        super().__init__(*args)

    def __str__(self) -> str:
        err_msg = ""
        if self.failed:
            err_msg += f"{self.failed}"
        if self.ex:
            if self.failed:
                err_msg += f" - {self.ex}"
            else:
                err_msg += str(self.ex)
        if not err_msg:
            return "failed."
        return f"{err_msg}."


def get_requested_perf_events() -> list[str]:
    requested_events = os.getenv("PERF_EVENTS", "").split(",")
    requested_events = [event.strip() for event in requested_events if event.strip()]
    return requested_events


def remove_files_if_exist(path) -> None:
    files = glob(path)
    for file in files:
        if os.path.exists(file):
            os.remove(file)


def all_subclasses(cls):
    return cls.__subclasses__() + [g for s in cls.__subclasses__() for g in all_subclasses(s)]


def format_time(timestamp: float) -> str:
    return datetime.fromtimestamp(timestamp, timezone.utc).strftime("%d-%m-%Y %H:%M:%S UTC")


def elapsed_time(seconds: float) -> str:
    hours, remainder = divmod(seconds, 3600)
    minutes, seconds = divmod(remainder, 60)
    return f"{int(hours):02d}:{int(minutes):02d}:{seconds:05.2f}"


def filter_existing_yamls(yaml_paths: list[str]) -> list[str]:
    existing_paths = []
    for path in yaml_paths:
        if os.path.exists(path) and is_yaml(path):
            existing_paths.append(path)
    return existing_paths


def is_yaml(path: str) -> bool:
    filename = os.path.basename(path)
    split = os.path.splitext(filename)
    if len(split) < 2:
        return False
    ext = os.path.splitext(path)[1].lower()
    return ext in [".yaml", ".yml"]


def write_file(data: str | bytes, path: str) -> None:
    try:
        with open(path, "wb") as file:
            if isinstance(data, str):
                file.write(data.encode())
            else:
                file.write(data)
    except OSError as ex:
        raise ProgramError("failed while writing file", ex)


def write_file_sudo(data: str | bytes, path: str) -> None:
    if isinstance(data, str):
        data = data.encode()
    try:
        subprocess.run(["sudo", "tee", path], input=data, check=True, stdout=subprocess.DEVNULL)
    except subprocess.CalledProcessError as ex:
        raise ProgramError("failed while writing file with superuser priviledges", ex)


def read_file(path: str) -> str:
    if not os.path.exists(path):
        raise ProgramError(f"file {path} doesn't exist")

    try:
        with open(path, "r") as file:
            return file.read().strip()
    except OSError as ex:
        raise ProgramError("failed while reading file", ex)


def tail_file(path: str, n: int = 10, block_size: int = 1024) -> str:
    if n <= 0 or not os.path.exists(path):
        return ""

    with open(path, "rb") as f:
        f.seek(0, os.SEEK_END)
        pos = f.tell()
        buf = bytearray()
        nl_seen = 0

        while pos > 0 and nl_seen < n + 1:
            read_size = min(block_size, pos)
            pos -= read_size
            f.seek(pos)
            chunk = f.read(read_size)
            buf[:0] = chunk
            nl_seen += chunk.count(b"\n")

        lines = buf.split(b"\n")[-n:]
        return b"\n".join(lines).decode(errors="replace")


def load_yaml(path: str) -> Any:
    try:
        with open(path, "rb") as file:
            return yaml.safe_load(file)
    except Exception as ex:
        raise ProgramError(f"failed while loading yaml", ex)


def ensure_dir_exists(path: str) -> None:
    if os.path.isdir(path) and not os.path.exists(path):
        os.makedirs(path)


def bold(text: str) -> str:
    return f"\033[1m{text}\033[0m"


def colored(text: str, color_code: str = "36") -> str:
    return f"\033[{color_code}m{text}\033[0m"


def fmt(label: str, value: str, value_width: int = 10, label_width: int = 12) -> str:
    if len(value) > value_width:
        value = value[: value_width - 1] + "…"
    label = bold(label)
    return f"{label:<{label_width}} {value:<{value_width}}"


def print_error(text: str) -> None:
    print(f'{colored("Error", "31")} {text}')


def print_success(text: str) -> None:
    print(f'{colored(text, "32")}.')


def print_info(text: str) -> None:
    print(f'{colored("Info", "34")} {text}')


def print_warning(text: str) -> None:
    print(f'{colored("Info", "33")} {text}')
