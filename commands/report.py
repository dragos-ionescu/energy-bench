import pandas as pd
import argparse
import json
import re
import os

from .base import BaseCommand
from utils import *


class ReportCommand(BaseCommand):
    name = "report"
    help = "Build reports from raw measurements"

    def __init__(self, base_dir) -> None:
        super().__init__(base_dir)
        self.requested_events = get_requested_perf_events()
        self.unit_map = {"Pkg": "J", "Core": "J", "Uncore": "J", "Dram": "J", "Time": "s"}
        self.colorway = [
            "#000000",
            "#E69F00",
            "#56B4E9",
            "#009E73",
            "#F0E442",
            "#0072B2",
            "#D55E00",
            "#CC79A7",
        ]

    def add_args(self, parser: argparse.ArgumentParser) -> None:
        parser.add_argument(
            "-s", "--skip", type=int, default=0, help="Number of rows to skip for each measurement"
        )
        parser.add_argument(
            "-a",
            "--average",
            nargs="*",
            default=[],
            help="Produce a CSV table with averaged results",
        )
        # parser.add_argument(
        #     "-v",
        #     "--violin",
        #     action="store_true",
        #     help="Produce violin and box-plots for each measurement",
        # )
        # parser.add_argument(
        #     "-i",
        #     "--interactive",
        #     action="store_true",
        #     help="Produce interactive HTML plots for each measurement",
        # )
        parser.add_argument(
            "-f",
            "--format",
            choices=["csv", "json"],
            default="csv",
            help="Output format for results",
        )
        parser.add_argument("results", nargs="+", default=[], help="Scenario results")

    def handle(self, args: argparse.Namespace) -> None:
        result = None
        if args.average:
            result = self.handle_average(args)
        else:
            result = self.handle_compile(args)
        self.output_result(result, args)

    def handle_compile(self, args: argparse.Namespace) -> pd.DataFrame:
        compiled = []

        for result in args.results:
            _, work, _, mode, impl, scen, model = self.split_result_path(result)

            try:
                with open(result) as file:
                    data = []
                    for line in file:
                        fixed_line = re.sub(r"(\d+),(\d+)", r"\1.\2", line)
                        data.append(json.loads(fixed_line))
            except Exception as ex:
                raise ProgramError(f"failed while reading result - {ex}")

            df = pd.DataFrame(data)

            numeric_cols = ["counter-value", "interval"]
            for col in numeric_cols:
                if col in df.columns:
                    df[col] = pd.to_numeric(df[col], errors="coerce").astype(float)

            df["group"] = (
                df["interval"] < df["interval"].shift(1, fill_value=float("inf"))
            ).cumsum()

            cumsum_cols = {}
            for event in self.requested_events:
                mask = df["event"] == event
                cumsum = (mask * df["counter-value"]).cumsum()
                cumsum_cols[event] = cumsum

            iterations = []
            for _, group in df.groupby("group"):
                start_probes = [
                    "probe_libenergy_signal:start_signal",
                    "probe_libenergy_signal:startSignal",
                ]
                stop_probes = [
                    "probe_libenergy_signal:stop_signal",
                    "probe_libenergy_signal:stopSignal",
                ]
                starts = group.loc[
                    group["event"].isin(start_probes) & (group["counter-value"] == 1.0)
                ].index.tolist()

                stops = group.loc[
                    group["event"].isin(stop_probes) & (group["counter-value"] == 1.0)
                ].index.tolist()

                if not starts and not stops:
                    iterations.append((group.index[0], group.index[-1]))
                else:
                    for start, stop in zip(starts, stops[: len(starts)]):
                        iterations.append((start, stop))

            for i, (start, stop) in enumerate(iterations, 1):
                event_sums = {}
                for event in self.requested_events:
                    pre_start = cumsum_cols[event].get(start - 1, default=0)
                    sum_val = cumsum_cols[event].at[stop] - pre_start
                    event_sums[event] = round(sum_val, 2)

                start_s = df.at[start, "interval"]
                stop_s = df.at[stop, "interval"]
                time_s = round(stop_s - start_s, 2)

                compiled.append(
                    {
                        "iter": i,
                        "model": model,
                        "work": "_" if work == "none" else work,
                        "mode": mode,
                        "impl": impl,
                        "name": scen,
                        "time": time_s,
                        **event_sums,
                    }
                )
        return pd.DataFrame(compiled)

    def handle_average(self, args: argparse.Namespace) -> pd.DataFrame:
        raw_df = self.handle_compile(args)
        agg_cols = ["time"] + list(self.requested_events)
        return raw_df.groupby(args.average)[agg_cols].mean().round(2).reset_index()

    def output_result(self, result: str | pd.DataFrame, args: argparse.Namespace) -> None:
        if isinstance(result, pd.DataFrame):
            if args.format == "csv":
                output = result.to_csv(index=False)
            elif args.format == "json":
                output = result.to_json(orient="records")
            else:
                output = result.to_csv(index=False)
        else:
            output = result

        print(output)

    # def handle_interactive(self, args: argparse.Namespace):
    #     first_result = args.results[0]
    #     rapl_path, cpu_type = self.find_rapl_file(first_result)
    #     perf_path = os.path.join(first_result, "result.json")
    #     _, _, _, mode, impl, scenario, model = self.split_result_path(first_result)

    #     if not os.path.exists(perf_path):
    #         raise ProgramError(f"No perf measurements found in {first_result}")

    #     df, cpu_type, power_unit = self.read_rapl_file(rapl_path, args.skip)

    #     pkg, core, uncore, dram, time = self.calculate_energy(cpu_type, df, power_unit)
    #     time = time / 1000

    #     rapl_m = {"Pkg": pkg, "Core": core, "Uncore": uncore, "Dram": dram, "Time": time}
    #     rapl_n = self.normalize_metrics(rapl_m)

    #     fig = go.Figure()

    #     for k, v in rapl_n.items():
    #         txt = [f"{val} {self.unit_map.get(k, '')}" for val in rapl_m[k]]
    #         htemp = f"Iteration: <b>%{{x}}</b><br>{k}: <b>%{{text}}</b><extra></extra>"
    #         fig.add_trace(
    #             go.Scatter(
    #                 y=v,
    #                 name=k,
    #                 mode="markers+lines",
    #                 marker=dict(symbol="diamond"),
    #                 text=txt,
    #                 hovertemplate=htemp,
    #             )
    #         )

    #     p_data = self.parse_perf_file(perf_path)
    #     p_metrics = {}
    #     p_ts = {}

    #     for key, events in p_data.items():
    #         cvals = [float(ev["counter-value"]) for ev in events]
    #         unwrapped = self.unwrap_intervals(events)
    #         p_metrics[key] = cvals
    #         p_ts[key] = unwrapped

    #     p_norm = self.normalize_metrics(p_metrics)

    #     for key, valz in p_norm.items():
    #         if p_ts[key]:
    #             x_val = [x - p_ts[key][0] for x in p_ts[key]]
    #             txt = [str(x) for x in p_metrics[key]]
    #             htemp = f"Timestamp: <b>%{{x}}</b> s<br>{key}: <b>%{{text}}</b><extra></extra>"
    #             fig.add_trace(
    #                 go.Scatter(
    #                     x=x_val,
    #                     y=valz,
    #                     name=key,
    #                     mode="lines",
    #                     text=txt,
    #                     xaxis="x2",
    #                     hovertemplate=htemp,
    #                 )
    #             )

    #     fig.update_layout(
    #         title=f"Interactive RAPL & Perf Metrics<br>{mode} {impl} {scenario}",
    #         xaxis=dict(title="Iterations"),
    #         xaxis2=dict(title="Elapsed Time (s)", overlaying="x", side="top"),
    #         yaxis_title="Normalized Measurements",
    #         legend_title="Metrics",
    #         colorway=self.colorway,
    #     )
    #     fig.show()

    # def adjust_perf_measurements(self, compiled: list[dict], trial_map: dict) -> list[dict]:
    #     adjusted = []
    #     for row in compiled:
    #         mode = row["Mode"]
    #         time_ms = row["Avg. Time (ms)"]
    #         r = row.copy()
    #         if mode in trial_map:
    #             tr_time, tr_counters = trial_map[mode]
    #             if tr_time > 0 and time_ms > 0:
    #                 scale_factor = time_ms / tr_time
    #                 for ev in self.requested_events:
    #                     key = f"Avg. {ev}"
    #                     r[key] = round(r[key] - tr_counters[ev] * scale_factor, 2)
    #         adjusted.append(r)
    #     return adjusted

    def split_result_path(self, result: str) -> tuple[str, str, str, str, str, str, str]:
        path = os.path.abspath(os.path.expanduser(result)).rstrip(os.sep)
        if os.path.isfile(path):
            path = os.path.dirname(path)

        parts = path.split(os.sep)
        if len(parts) < 5:
            raise ProgramError(f"result {result!r} has unexpected structure")

        scenario = parts[-1]
        impl = parts[-2]
        warmup = parts[-3]
        model = parts[-4]
        run_dir = parts[-5]

        if run_dir.count("_") < 2:
            raise ProgramError(f"result {result!r} has unexpected structure")

        env, work, time = run_dir.split("_", 2)
        return env, work, time, warmup, impl, scenario, model

    # def unwrap_intervals(self, events: list[dict[str, Any]]) -> list[float]:
    #     ts = [float(ev["interval"]) for ev in events]
    #     unwrapped = []
    #     offset = 0.0
    #     last_val = None

    #     for val in ts:
    #         if last_val is not None and val < last_val:
    #             offset += last_val
    #         unwrapped.append(val + offset)
    #         last_val = val

    #     return unwrapped

    # def normalize_metrics(self, metrics: dict[str, Any]) -> dict[str, Any]:
    #     out = {}

    #     for k, v in metrics.items():
    #         if v is not None and len(v) > 0:
    #             if hasattr(v, "min") and hasattr(v, "max"):
    #                 mn, mx = v.min(), v.max()
    #                 out[k] = (v - mn) / (mx - mn) if mx > mn else v
    #             else:
    #                 mn, mx = min(v), max(v)
    #                 if mx > mn:
    #                     out[k] = [(x - mn) / (mx - mn) for x in v]
    #                 else:
    #                     out[k] = v
    #         else:
    #             out[k] = v

    #     return out
