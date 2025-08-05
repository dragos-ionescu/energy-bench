from typing import TextIO
import argparse

from scenario import Scenario

from .base import BaseCommand
from utils import *


class AnalyzeCommand(BaseCommand):
    name = "analyze"
    help = ""

    def add_args(self, parser: argparse.ArgumentParser) -> None:
        parser.add_argument("-f", "--fairness", action="store_true")
        parser.add_argument("-a", "--assembly", action="store_true")
        parser.add_argument("-c", "--code", action="store_true")
        parser.add_argument("scenario", type=str, help="")

    def handle(self, args: argparse.Namespace) -> None:
        if args.fairness:
            pass
        elif args.assembly:
            pass
        elif args.code:
            self.handle_code(args.scenario)

    def handle_assembly(self, file: TextIO) -> None:
        pass

    def handle_fairness(self, file1: TextIO, file2: TextIO) -> None:
        pass

    def handle_code(self, path: str) -> None:
        scenario = Scenario.from_yaml(path)
        if not scenario.code:
            raise ProgramError(f"no code in scenario")
        else:
            print(scenario.code)
