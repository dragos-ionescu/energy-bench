from dataclasses import MISSING, asdict, dataclass, field, fields
from subprocess import CalledProcessError
from collections.abc import Iterator
from contextlib import nullcontext
from typing import Any, ClassVar
from abc import abstractmethod
from glob import glob
import subprocess
import signal
import shutil
import yaml
import json
import os

from environments import Environment
from workloads import Workload
from utils import *

from dataclasses import dataclass, field, fields, MISSING


def str_presenter(dumper, data):
    return dumper.represent_scalar("tag:yaml.org,2002:str", data, style="|")


yaml.add_representer(str, str_presenter, Dumper=yaml.SafeDumper)


@dataclass
class Test:
    id: str
    args: list[str] = field(default_factory=list)
    stdin: bytes = b""
    expected_stdout: bytes = b""

    @classmethod
    def from_dict(cls, data: dict) -> "Test":
        return cls(
            id=data["id"] if "id" in data else "default",
            args=[str(a) for a in data.get("args", [])],
            stdin=_to_bytes(data.get("stdin", b"")),
            expected_stdout=_to_bytes(data.get("expected_stdout", b"")),
        )


def _to_bytes(value: Any) -> bytes:
    if isinstance(value, bytes):
        return value
    if isinstance(value, str):
        return value.encode("utf-8")
    raise ProgramError("value must be str or bytes")


@dataclass
class Scenario:
    name: str
    implementation: str
    description: str
    dependencies: list[dict]

    options: list[str] = field(default_factory=list)
    roptions: list[str] = field(default_factory=list)
    hardware: str = "Ubuntu 22.04.5 LTS x86_64, Intel i7-8700 (12 cores @ 800MHz-4.6GHz), 16GB RAM, NVIDIA GTX 1060 3GB, Caches: L1d/L1i: 192KiB×6, L2: 1.5MiB×6, L3: 12MiB"
    model: str = "human"
    code: str = ""

    packages: list[dict] = field(
        default_factory=list
    )  # For language implementations with package managers e.g. .NET, Cargo
    target_framework: str = "net9.0"  # C# .NET specific
    class_paths: list[str] = field(default_factory=list)  # Java specific

    _yaml_path: str = field(repr=False, init=False, default="")

    @classmethod
    def from_yaml(cls, path: str) -> "Scenario":
        try:
            with open(path, "rb") as file:
                data = yaml.safe_load_all(file)
                scenario_data = next(data) or {}
        except Exception as ex:
            raise ProgramError(f"failed while loading scenario", ex)

        required = {
            f.name for f in fields(cls) if f.default is MISSING and f.default_factory is MISSING
        }
        provided = {k: v for k, v in scenario_data.items() if v is not None}
        if missing := required - provided.keys():
            raise ProgramError(f"scenario missing required mapping(s): {', '.join(missing)}")
        if " " in provided.get("name", ""):
            raise ProgramError("scenario 'name' must not have any spaces")

        for dependency in provided.get("dependencies", []):
            if not isinstance(dependency, dict) or "name" not in dependency:
                raise ProgramError(
                    "scenario dependencies must have a 'name' and optionally 'version'"
                )

        allowed = {f.name for f in fields(cls)}
        filtered = {k: v for k, v in provided.items() if k in allowed}

        obj = cls(**filtered)
        obj._yaml_path = path
        return obj

    def save(self, path: str) -> None:
        try:
            data = asdict(self)
            data.pop("_yaml_path", None)

            docs = [data]
            for test in self.get_tests():
                docs.append(
                    {
                        "id": test.id,
                        "args": test.args,
                        "stdin": test.stdin,
                        "expected_stdout": test.expected_stdout,
                    }
                )

            with open(path, "w") as file:
                yaml.safe_dump_all(docs, file, indent=4, sort_keys=False, allow_unicode=True)

            self._yaml_path = path
            print_info(f"saved scenario to {path}")
        except Exception as ex:
            raise ProgramError(f"failed while saving scenario: {ex}")

    def get_tests(self) -> Iterator[Test]:
        return self._make_test_iter(self._yaml_path)

    @staticmethod
    def _make_test_iter(path: str) -> Iterator[Test]:
        try:
            with open(path, "rb") as file:
                data = yaml.safe_load_all(file)
                next(data)
                for i, test in enumerate(data, 1):
                    if not test:
                        test = dict()

                    if "id" not in test:
                        test = {**test, "id": f"{i}"}
                    yield Test.from_dict(test)
        except Exception as ex:
            raise ProgramError(f"failed while loading tests: {ex}")


@dataclass
class Implementation:
    scenario: Scenario
    aliases: ClassVar[list[str]] = []
    target: str = ""
    source: str = ""
    base_dir: str = ""
    warmup: bool = False
    timeout: int = 60 * 10  # 10 minutes
    iterations: int = 1
    frequency: int = 100
    niceness: int = 0
    affinity: set[int] | None = None

    def __post_init__(self) -> None:
        os.makedirs(self.scenario_path, exist_ok=True)

    def __enter__(self):
        self.build()
        return self

    def __exit__(
        self, exc_type: type | None, exc_value: Exception | None, traceback: Any | None
    ) -> bool:
        self.clean()
        return False

    def _ensure_results_dir(
        self, test: Test, workload: Workload, env: Environment, timestamp: float
    ) -> str:
        env_str = env.__class__.__name__.lower()
        work_str = workload.__class__.__name__.lower()

        results_dir = timestamp
        if work_str == "workload":
            results_dir = f"none_{results_dir}"
        else:
            results_dir = f"{work_str}_{results_dir}"

        if env_str == "environment":
            results_dir = f"none_{results_dir}"
        else:
            results_dir = f"{env_str}_{results_dir}"

        warmup_dir = "warmup" if self.warmup else "no-warmup"
        impl_str = self.__class__.__name__
        results_dir = os.path.join(
            self.base_dir,
            results_dir,
            self.scenario.model,
            warmup_dir,
            impl_str,
            f"{self.scenario.name}_{test.id}",
        )
        os.makedirs(results_dir, exist_ok=True)
        return results_dir

    def _lib_wrapped(self, command: str) -> str:
        env = " ".join(
            [
                f"LIBRARY_PATH={self.base_dir}:$(echo $NIX_LDFLAGS | sed 's/-rpath //g; s/-L//g' | tr ' ' ':'):$LIBRARY_PATH",
                f"LD_LIBRARY_PATH={self.base_dir}:$(echo $NIX_LDFLAGS | sed 's/-rpath //g; s/-L//g' | tr ' ' ':'):$LD_LIBRARY_PATH",
                f"CPATH={self.base_dir}:$(echo $NIX_CFLAGS_COMPILE | sed -e 's/-frandom-seed=[^ ]*//g' -e 's/-isystem/ /g' | tr -s ' ' | sed 's/ /:/g'):$CPATH",
                "NIX_ENFORCE_NO_NATIVE=",
                f"ITERATIONS={self.iterations if self.warmup else 1}",
            ]
        )
        return f"{env} {command}"

    def _get_available_perf_events(self) -> list[str]:
        requested_events = get_requested_perf_events()
        captured_events: list[str] = []

        try:
            result = subprocess.run(
                args=["perf", "list", "--json", "--no-desc"], check=True, capture_output=True
            )
            available_events = iter(json.loads(result.stdout))

            while len(captured_events) < len(requested_events):
                evt = next(available_events, None)
                if evt is None:
                    break
                name = evt.get("EventName")
                if name in requested_events and name not in captured_events:
                    captured_events.append(name)

            if not captured_events:
                return ["cpu-clock", "cycles"]

            return captured_events

        except (subprocess.SubprocessError, json.JSONDecodeError):
            return ["cpu-clock", "cycles"]

    def _perf_wrapped(self, command: str) -> str:
        events = self._get_available_perf_events()
        perf_path = os.path.join(self.scenario_path, "result.json")
        perf_command = (
            f"perf stat --all-cpus --append -I {self.frequency} --json --output {perf_path} "
            f"-e probe_libenergy_signal:start_signal,probe_libenergy_signal:stop_signal "
            f"-e probe_libenergy_signal:startSignal,probe_libenergy_signal:stopSignal "
            f"-e {','.join(events)}"
        )
        return f"{perf_command} {command}"

    def _nice_wrapped(self, command: str) -> str:
        return f"nice -n {self.niceness} {command}"

    def _nix_wrapped(self, command: str) -> list[str]:
        nix_pkgs = [pkg["name"] for pkg in self.scenario.dependencies]
        if not nix_pkgs:
            return [command]
        return [
            "nix-shell",
            "--no-build-output",
            "--quiet",
            "--packages",
            *nix_pkgs,
            "--run",
            command,
        ]

    def _wrap_command(self, command: str, measuring: bool = False) -> list[str]:
        if measuring:
            command = self._perf_wrapped(command)
            command = self._nice_wrapped(command)
            command = self._lib_wrapped(command)
            command = f"sudo -E {command}"
        else:
            command = self._lib_wrapped(command)

        return self._nix_wrapped(command)

    @property
    def scenario_path(self) -> str:
        impl_str = self.__class__.__name__
        return os.path.join(self.base_dir, self.scenario.model, impl_str, self.scenario.name)

    @property
    def target_path(self) -> str:
        return os.path.join(self.scenario_path, self.target)

    @property
    def source_path(self) -> str:
        return os.path.join(self.scenario_path, self.source)

    def build(self) -> None:
        if not self.scenario.code:
            raise ProgramError("scenario doesn't have any code")

        write_file(self.scenario.code, self.source_path)
        cmd = " ".join(self.build_command)
        wrapped = self._wrap_command(cmd)

        try:
            subprocess.run(args=wrapped, check=True, capture_output=True)
        except CalledProcessError as ex:
            raise ProgramError(
                f"returned non-zero exit status {ex.returncode} while building: {ex.stderr}"
            )

    def measure_and_verify(self, test: Test, env: Environment, work: Workload) -> None:
        # Clears memory to minimise the energy overhead of the tool
        input_path = None
        if test.stdin:
            input_path = os.path.join(self.scenario_path, "input")
            write_file(test.stdin, input_path)
            test.stdin = b""

        expected_path = None
        if test.expected_stdout:
            expected_path = os.path.join(self.scenario_path, "expected")
            write_file(test.expected_stdout, expected_path)
            test.expected_stdout = b""

        self.scenario.description = ""

        output_path = os.path.join(self.scenario_path, "output")

        for _ in range(1 if self.warmup else self.iterations):
            with work, env:
                self.measure(test, input_path, output_path)
            self.verify(test, expected_path, output_path)

    def measure(self, test: Test, input_path: str | None, output_path: str) -> None:
        cmd = " ".join(self.measure_command + test.args)
        wrapped = self._wrap_command(cmd, measuring=True)

        preexec_fn = lambda: os.sched_setaffinity(0, self.affinity) if self.affinity else None

        with open(input_path, "rb") if input_path else nullcontext(None) as infile, open(
            output_path, "wb"
        ) as outfile:
            proc = subprocess.Popen(
                wrapped,
                stdout=outfile,
                stderr=subprocess.PIPE,
                stdin=infile,
                preexec_fn=preexec_fn,
                process_group=0,
            )
            try:
                proc.wait(self.timeout)
            except subprocess.TimeoutExpired:
                os.killpg(proc.pid, signal.SIGKILL)
                raise ProgramError(f"failed while measuring: timed out after {self.timeout}s")

            if proc.stderr:
                stderr_txt = proc.stderr.read().decode(errors="replace").strip()
                if proc.returncode != 0:
                    raise ProgramError(f"exit {proc.returncode}:\n{stderr_txt}")

    def verify(self, test: Test, expected_path: str | None, output_path: str) -> None:
        if not expected_path:
            return

        try:
            with open(expected_path, "rb") as expfile, open(output_path, "rb") as outfile:
                expected = expfile.read()

                for i in range(self.iterations if self.warmup else 1):
                    chunk = outfile.read(len(expected))
                    if len(chunk) != len(expected):
                        raise ProgramError(
                            f"test '{test.id}' got unexpected stdout for iteration {i + 1}: lengths unequal"
                        )
                    if chunk != expected:
                        raise ProgramError(
                            f"test '{test.id}' got unexpected stdout for iteration {i + 1}: content unequal"
                        )

                remaining = outfile.read(1)
                if remaining:
                    raise ProgramError(f"scenario has more output than expected")
        except IOError as ex:
            raise ProgramError(f"failed to verify: {ex}")

    def clean(self) -> None:
        try:
            cmd = " ".join(self.clean_command)
            wrapped = self._wrap_command(cmd)
            subprocess.run(args=wrapped, check=True, capture_output=True)
        except CalledProcessError as ex:
            raise ProgramError(f"failed to clean scenario: {ex.stderr}")
        except IOError as ex:
            raise ProgramError(f"failed to clean scenario: {ex}")
        finally:
            remove_files_if_exist(os.path.join(self.scenario_path, "input"))
            remove_files_if_exist(os.path.join(self.scenario_path, "expected"))

    def move_results(
        self, test: Test, workload: Workload, env: Environment, timestamp: float
    ) -> None:
        results = glob(os.path.join(self.scenario_path, "result.json"))
        if not results:
            raise ProgramError("scenario didn't generate a valid result")
        if len(results) > 1:
            raise ProgramError("found more than one result")

        results_dir = self._ensure_results_dir(test, workload, env, timestamp)
        try:
            shutil.move(results[0], results_dir)
        except IOError as ex:
            raise ProgramError(f"failed to move result: {ex}")

    @property
    def build_command(self) -> list[str]:
        return []

    @property
    @abstractmethod
    def measure_command(self) -> list[str]:
        raise NotImplementedError

    @property
    def clean_command(self) -> list[str]:
        return []
