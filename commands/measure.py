import subprocess
import argparse
import getpass
import random
import time
import os

from rich.progress import Progress, BarColumn, TextColumn, TimeElapsedColumn
from rich.padding import Padding
from rich.columns import Columns
from rich.layout import Layout
from rich.panel import Panel
from rich.live import Live
from rich.text import Text

from implementations import get_implementation_class
from .base import BaseCommand, positive_int
from workloads import Workload
from scenario import Scenario
from environments import *
from utils import *


class MeasureCommand(BaseCommand):
    name = "measure"
    help = "Perform measurements on scenario files"

    def __init__(self, base_dir) -> None:
        super().__init__(base_dir)

    def ensure_superuser(self) -> None:
        try:
            subprocess.run(
                ["sudo", "-n", "true"],
                check=True,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
        except subprocess.CalledProcessError:
            password = getpass.getpass("sudo password: ")
            try:
                subprocess.run(
                    ["sudo", "-S", "-v"],
                    input=password + "\n",
                    text=True,
                    check=True,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                )
            except subprocess.CalledProcessError as ex:
                self.record_issue("superuser authentication failed", True)
                exit(ex.returncode)

    def add_args(self, parser: argparse.ArgumentParser) -> None:
        parser.add_argument(
            "-i",
            "--iterations",
            type=positive_int,
            default=1,
            help="Number of measurement iterations",
        )
        parser.add_argument(
            "-f",
            "--frequency",
            type=positive_int,
            default=100,
            help="Measurement frequency in milliseconds",
        )
        parser.add_argument(
            "-s",
            "--sleep",
            type=positive_int,
            default=0,
            help="Seconds to sleep between each successful measurement",
        )
        parser.add_argument(
            "-t",
            "--timeout",
            type=positive_int,
            default=60 * 10,  # 10 minutes
            help="Seconds before a measurement is stopped automatically",
        )
        parser.add_argument(
            "--no-warmup",
            action="store_true",
            help="Perform measure iterations around the scenario",
        )
        parser.add_argument(
            "--warmup", action="store_true", help="Perform measure iterations inside the scenario"
        )
        parser.add_argument(
            "--prod",
            action="store_true",
            help="Enter the 'production' environment before measuring",
        )
        parser.add_argument(
            "--light",
            action="store_true",
            help="Enter the 'lightweight' environment before measuring",
        )
        parser.add_argument(
            "--lab", action="store_true", help="Enter the 'lab' environment before measuring"
        )
        parser.add_argument(
            "--workloads", nargs="*", default=[], help="Specify workloads to enter before measuring"
        )
        parser.add_argument("--stop", action="store_true", help="Stop after any failures")
        parser.add_argument(
            "--trial", action="store_true", help="Adds a trial run to the experiments"
        )
        parser.add_argument("scenarios", nargs="*", default=[], help="Scenarios to run")

    def handle(self, args: argparse.Namespace) -> None:
        self.ensure_superuser()

        environments = []
        if args.lab:
            environments.append(Lab())
        if args.light:
            environments.append(Lightweight())
        if args.prod:
            environments.append(Production())
        if not environments:
            environments = [Environment()]

        workloads = [Workload()]
        workload_strs = {w.lower() for w in args.workloads}
        for wstr in workload_strs:
            found = False
            for cls in Workload.__subclasses__():
                if wstr == cls.__name__.lower():
                    workloads.append(cls())
                    found = True
            if not found:
                self.record_issue(f"'{wstr}' is not a known workload", args.stop)

        modes = []
        if args.warmup:
            modes.append("warmup")
        if args.no_warmup:
            modes.append("no-warmup")
        if not modes:
            modes = ["warmup", "no-warmup"]

        random.shuffle(args.scenarios)
        random.shuffle(modes)
        random.shuffle(workloads)

        if args.trial:
            args.scenarios.insert(0, os.path.join(self.base_dir, "trial.yml"))

        self.iterations = args.iterations
        self.timeout = args.timeout
        self.sleep = args.sleep
        self.stop = args.stop

        self.progress = Progress(
            TextColumn("[bold blue]{task.description}", justify="right"),
            BarColumn(bar_width=None),
            "[progress.percentage]{task.percentage:>3.1f}%",
            "•",
            TimeElapsedColumn(),
        )

        total = len(args.scenarios) * len(environments) * len(workloads) * len(modes)
        self.scenarios_tid = self.progress.add_task("Running Scenarios", total=total)

        with Live(auto_refresh=False) as live:
            for file in args.scenarios:
                scenario = Scenario.from_yaml(file)
                iclass = get_implementation_class(scenario.implementation)
                self.implementation = iclass(
                    scenario=scenario,
                    base_dir=self.base_dir,
                    iterations=args.iterations,
                    frequency=args.frequency,
                    niceness=-20 if args.lab else 0,
                    affinity={0} if args.lab else None,
                )
                self.environments = environments
                self.workloads = workloads
                self.modes = modes
                self.run_scenario(live)
        self.goodbye()

    def run_scenario(self, live: Live) -> None:
        interrupted = False

        for env in self.environments:
            for work in self.workloads:
                for mode in self.modes:
                    if mode == "warmup":
                        self.implementation.warmup = True
                        self.implementation.timeout = self.timeout * self.iterations
                    else:
                        self.implementation.warmup = False
                        self.implementation.timeout = self.timeout

                    try:
                        with self.implementation:
                            live.update(self.render_interface(env, work), refresh=True)
                            for test in self.implementation.scenario.get_tests():
                                self.logger.info(
                                    f"running '{self.implementation.scenario.name}' test '{test.id}' with {mode}"
                                )
                                self.implementation.measure_and_verify(test, env, work)
                                self.implementation.move_results(test, work, env, self.timestamp)
                        self.progress.advance(self.scenarios_tid)
                        self.logger.info("ok!")
                    except ProgramError as ex:
                        self.record_issue(str(ex), self.stop)
                    except KeyboardInterrupt:
                        interrupted = True
                        self.record_issue("manually exited", True)
                    finally:
                        remove_files_if_exist(
                            os.path.join(self.implementation.scenario_path, "result.json")
                        )
                        if not interrupted and self.sleep:
                            try:
                                print_info(f"sleeping for {self.sleep} seconds")
                                time.sleep(self.sleep)
                            except KeyboardInterrupt:
                                self.record_issue("manually exited", True)

    def render_field(self, label: str, value: str | None = None) -> Text:
        if not value:
            value = "─"
        return Text.assemble((f"{label}: ", "bold"), value)

    def render_scenario_cols(self, env: Environment, work: Workload) -> list:
        scenario_name = self.implementation.scenario.name
        implementation_name = self.implementation.scenario.implementation
        is_warmup = "On" if self.implementation.warmup else "Off"

        scenario_field = self.render_field("Scenario", scenario_name)
        implementation_field = self.render_field("Implementation", implementation_name)
        warmup_field = self.render_field("Warmup", is_warmup)

        env_name = env.__class__.__name__.lower()
        env_field = self.render_field(
            "Environment", None if env_name == "environment" else env_name
        )

        work_name = work.__class__.__name__.lower()
        work_field = self.render_field("Workload", None if work_name == "workload" else work_name)

        gov = {c.governor for c in get_cpus("online")}
        freqs = {round(c.max_freq * 1e-6, 2) for c in get_cpus("online")}
        min_freqs = {round(c.min_freq * 1e-6, 2) for c in get_cpus("online")}

        gov_str = gov.pop() if len(gov) == 1 else ("Mixed" if gov else "Unknown")
        max_freq = freqs.pop() if len(freqs) == 1 else None
        min_freq = min_freqs.pop() if len(min_freqs) == 1 else None
        max_freq_str = f"{max_freq}GHz" if max_freq else ("Mixed" if freqs else "Unknown")
        min_freq_str = f"{min_freq}GHz" if min_freq else ("Mixed" if min_freqs else "Unknown")

        cpus_on = len(get_cpus("online"))
        cpus_off = len(get_cpus("offline"))
        swaps_on = len(get_swaps())
        dropped = "All" if isinstance(env, Lab) else "─"

        scenario_field = self.render_field("Scenario", scenario_name)
        implementation_field = self.render_field("Implementation", implementation_name)
        warmup_field = self.render_field("Warmup", is_warmup)
        env_field = self.render_field(
            "Environment",
            None if env_name == "environment" else env_name,
        )
        work_field = self.render_field(
            "Workload",
            None if work_name == "workload" else work_name,
        )
        gov_field = self.render_field("Governor", gov_str)
        swaps_field = self.render_field("Swaps", str(swaps_on))
        dropped_field = self.render_field("OS Caches Dropped", dropped)

        freq_field = self.render_field("Frequencies", f"{min_freq_str} ↔ {max_freq_str}")
        cpu_field = self.render_field("CPUs", f"{cpus_on} on / {cpus_off} off")

        return [
            scenario_field,
            implementation_field,
            warmup_field,
            env_field,
            work_field,
            gov_field,
            freq_field,
            cpu_field,
            swaps_field,
            dropped_field,
        ]

    def render_scenario_panel(self, cols: list):
        columns = Columns(cols, equal=True, expand=True)
        return Panel(columns, title="Current Scenario")

    def render_logs_panel(self):
        tail = tail_file(self.log_path, 18)
        tail = Text(tail)
        return Panel(tail, title="Logs")

    def render_layout(self, logs_panel: Panel, scenario_panel: Panel, progress_panel: Panel):
        layout = Layout()
        layout.split_column(
            Layout(logs_panel, name="upper", size=20), Layout(name="lower", size=10)
        )
        layout["lower"].split_row(
            Layout(scenario_panel, name="left"),
            Layout(progress_panel, name="right"),
        )
        return Padding(layout, (1, 0, 0, 0))

    def render_progress(self) -> Panel:
        return Panel(self.progress, title="Progress")

    def render_interface(self, env: Environment, work: Workload):
        logs_panel = self.render_logs_panel()
        scenario_cols = self.render_scenario_cols(env, work)
        scenario_panel = self.render_scenario_panel(scenario_cols)
        progress_panel = self.render_progress()
        return self.render_layout(logs_panel, scenario_panel, progress_panel)
