from dataclasses import dataclass
from typing import Any
import subprocess
import os

from utils import *


class Cpu:
    def __init__(self, value: int) -> None:
        self.cpu_path = f"/sys/devices/system/cpu/cpu{value}"
        if os.path.isdir(self.cpu_path):
            self.value = value
        else:
            raise ProgramError(f"Cpu {value} doesn't exist.")

    @property
    def enabled(self) -> bool:
        path = f"{self.cpu_path}/online"
        if os.path.exists(path):
            with open(path, "r") as file:
                value = file.read().strip()
                return value == "1"
        return True

    @enabled.setter
    def enabled(self, value: bool) -> None:
        path = f"{self.cpu_path}/online"
        if self.value != 0:
            write_file_sudo("1" if value else "0", path)

    @property
    def hyperthread(self) -> bool:
        path = f"{self.cpu_path}/topology/thread_siblings_list"

        try:
            siblings_str = read_file(path)
        except ProgramError:
            return False

        siblings = []
        for part in siblings_str.split(","):
            part = part.strip()
            if "-" in part:
                start, end = part.split("-")
                siblings.extend([str(i) for i in range(int(start), int(end) + 1)])
            elif part:
                siblings.append(part)

        siblings = sorted(siblings, key=int)
        if len(siblings) < 2:
            return False

        return str(self.value) in siblings[1:]

    @property
    def governor(self) -> str:
        path = f"{self.cpu_path}/cpufreq/scaling_governor"
        return read_file(path)

    @governor.setter
    def governor(self, value: str) -> None:
        path = f"{self.cpu_path}/cpufreq/scaling_governor"
        if value not in self.available_governors:
            raise ProgramError(f"governor '{value}' not available on CPU {self.value}.")
        write_file_sudo(value, path)

    @property
    def available_governors(self) -> list[str]:
        path = f"{self.cpu_path}/cpufreq/scaling_available_governors"
        return read_file(path).split()

    @property
    def min_hw_freq(self) -> int:
        path = f"{self.cpu_path}/cpufreq/cpuinfo_min_freq"
        return int(read_file(path))

    @property
    def max_hw_freq(self) -> int:
        path = f"{self.cpu_path}/cpufreq/cpuinfo_max_freq"
        return int(read_file(path))

    @property
    def min_freq(self) -> int:
        path = f"{self.cpu_path}/cpufreq/scaling_min_freq"
        return int(read_file(path))

    @min_freq.setter
    def min_freq(self, value: int) -> None:
        hw_min = self.min_hw_freq
        hw_max = self.max_hw_freq
        path = f"{self.cpu_path}/cpufreq/scaling_min_freq"
        if not (hw_min <= value <= hw_max):
            raise ProgramError(
                f"frequency {value} cannot be outside hardware limits [{hw_min}, {hw_max}]"
            )
        write_file_sudo(str(value), path)

    @property
    def max_freq(self) -> int:
        path = f"{self.cpu_path}/cpufreq/scaling_max_freq"
        return int(read_file(path))

    @max_freq.setter
    def max_freq(self, value: int) -> None:
        hw_min = self.min_hw_freq
        hw_max = self.max_hw_freq
        path = f"{self.cpu_path}/cpufreq/scaling_max_freq"
        if not (hw_min <= value <= hw_max):
            raise ProgramError(
                f"frequency {value} cannot be outside hardware limits [{hw_min}, {hw_max}]"
            )
        write_file_sudo(str(value), path)


def get_cpu_vendor() -> str:
    cpuinfo = read_file("/proc/cpuinfo")
    if "GenuineIntel" in cpuinfo:
        return "intel"
    if "AuthenticAMD" in cpuinfo:
        return "amd"
    raise ProgramError("Unknown CPU vendor")


def get_cpus(value: str) -> list[Cpu]:
    available_modes = ["online", "offline", "present", "possible"]
    if value not in available_modes:
        raise ProgramError(f"can only get {','.join(available_modes)} CPUs")

    cpus: list[Cpu] = []
    content = read_file(f"/sys/devices/system/cpu/{value}")
    if not content:
        return []

    for part in content.split(","):
        rng = part.split("-")
        if len(rng) == 2:
            cpus.extend([Cpu(v) for v in range(int(rng[0]), int(rng[1]) + 1)])
        else:
            cpus.append(Cpu(int(rng[0])))
    return cpus


def get_aslr() -> int:
    val = read_file("/proc/sys/kernel/randomize_va_space")
    return int(val)


def set_aslr(value: int) -> None:
    if value not in [0, 1, 2]:
        raise ProgramError(f"unsupported ASLR mode {value}")
    write_file_sudo(str(value), "/proc/sys/kernel/randomize_va_space")


def get_intel_boost() -> bool:
    path = "/sys/devices/system/cpu/intel_pstate/no_turbo"
    value = read_file(path)
    return not (value == "1")


def set_intel_boost(enable: bool) -> None:
    path = "/sys/devices/system/cpu/intel_pstate/no_turbo"
    if not os.path.exists(path):
        raise ProgramError(f"file {path} doesn't exist")
    write_file_sudo("0" if enable else "1", path)


def set_drop_caches(value: int = 3) -> None:
    """
    mode = 1 page cache only
    mode = 2 dentries & inodes only
    mode = 3 both (default)
    """
    if value not in [1, 2, 3]:
        raise ProgramError(f"unsupported drop_cache mode {value}")

    try:
        subprocess.run(["sync"], check=True)
    except subprocess.CalledProcessError as ex:
        raise ProgramError(f"failed while synchronizing - {ex}")
    write_file_sudo(str(value), "/proc/sys/vm/drop_caches")


def get_swaps() -> list[str]:
    devices = []
    try:
        if os.path.exists("/proc/swaps"):
            with open("/proc/swaps") as f:
                next(f, None)
                for line in f:
                    fields = line.split()
                    if fields:
                        devices.append(fields[0])
        return devices
    except Exception as ex:
        raise ProgramError(f"failed while getting swap - {ex}")


def set_swaps(enable: bool, devices: list[str] | None = None) -> None:
    try:
        if devices:
            for dev in devices:
                if enable:
                    subprocess.run(["sudo", "swapon", dev], check=True)
                else:
                    subprocess.run(["sudo", "swapoff", dev], check=True)
        else:
            if enable:
                subprocess.run(["sudo", "swapon", "-a"], check=True)
            else:
                subprocess.run(["sudo", "swapoff", "-a"], check=True)
    except Exception as ex:
        raise ProgramError(f"failed while setting swap - {ex}")


@dataclass
class Environment:
    """Controls Linux-specific OS environment"""

    def record_original(self):
        self._orig_aslr = get_aslr()
        if get_cpu_vendor() == "intel":
            try:
                self._orig_intel_boost = get_intel_boost()
            except ProgramError:
                self._orig_intel_boost = None

        self._orig_cpus = {}
        for cpu in get_cpus("present"):
            if cpu.enabled:
                self._orig_cpus[cpu.value] = {
                    "enabled": True,
                    "governor": cpu.governor,
                    "max_freq": cpu.max_freq,
                    "min_freq": cpu.min_freq,
                }
            else:
                self._orig_cpus[cpu.value] = {"enabled": False}

        self._orig_swaps = get_swaps()

    def restore_original(self):
        set_aslr(self._orig_aslr)
        if (
            get_cpu_vendor() == "intel"
            and hasattr(self, "_orig_intel_boost")
            and self._orig_intel_boost is not None
        ):
            try:
                set_intel_boost(self._orig_intel_boost)
            except ProgramError:
                pass  # Intel boost not available on this system

        for cpu in get_cpus("present"):
            orig_cpu = self._orig_cpus[cpu.value]
            if orig_cpu["enabled"]:
                cpu.enabled = True
                cpu.governor = orig_cpu["governor"]
                cpu.max_freq = orig_cpu["max_freq"]
                cpu.min_freq = orig_cpu["min_freq"]
            else:
                cpu.enabled = False

        set_swaps(False)  # First disable all swaps
        if self._orig_swaps:  # Only enable if there were original swaps
            set_swaps(True, self._orig_swaps)  # Then enable the ones that were on

    def __enter__(self):
        self.record_original()
        self.enter()
        return self

    def __exit__(
        self, exc_type: type | None, exc_value: Exception | None, traceback: Any | None
    ) -> bool:
        self.restore_original()
        return False

    def enter(self) -> None:
        pass


@dataclass
class Production(Environment):
    def enter(self) -> None:
        set_aslr(2)  # Enable ASLR

        if get_cpu_vendor() == "intel":
            try:
                set_intel_boost(True)  # Enable Turbo Boost on Intel
            except ProgramError:
                pass  # Intel boost not available on this system

        set_swaps(True)  # Enable All Swaps

        for cpu in get_cpus("present"):
            cpu.enabled = True  # Enable all CPUs
            cpu.governor = "performance"  # Performance Governor on all CPUs
            cpu.max_freq = cpu.max_hw_freq  # Max Hardware Frequency on all CPUs
            cpu.min_freq = max(
                cpu.min_hw_freq, 1000000
            )  # at least 1 GHz Min Hardware Frequency on all CPUs


@dataclass
class Lightweight(Environment):
    pass


@dataclass
class Lab(Environment):
    def enter(self) -> None:
        set_aslr(0)  # Disable ASLR

        if get_cpu_vendor() == "intel":
            try:
                set_intel_boost(False)  # Disable Turbo Boost on Intel
            except ProgramError:
                pass  # Intel boost not available on this system

        set_swaps(False)  # Disable All Swaps

        set_drop_caches(3)  # Drop Page Cache, Dentries & Inodes

        # First disable hyperthreads, then disable cores beyond 0-3
        online_cpus = get_cpus("online")

        # Disable hyperthreads
        for cpu in online_cpus:
            if cpu.hyperthread:
                cpu.enabled = False

        # Get currently online CPUs after disabling hyperthreads
        online_cpus = get_cpus("online")

        # Disable all but cores 0, 1, 2, 3
        for cpu in online_cpus:
            if cpu.value > 3:
                cpu.enabled = False

        # Configure remaining online CPUs
        for cpu in get_cpus("online"):
            cpu.governor = "powersave"  # Powersave Governor on all CPUs
            cpu.max_freq = cpu.min_hw_freq  # Min Hardware Frequency on all CPUs
            cpu.min_freq = cpu.min_hw_freq  # Min Hardware Frequency on all CPUs
