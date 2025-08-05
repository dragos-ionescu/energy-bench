import argparse

from .base import BaseCommand
from environments import *
from utils import *


class TuneCommand(BaseCommand):
    name = "tune"
    help = ""

    def add_args(self, parser: argparse.ArgumentParser) -> None:
        parser.add_argument(
            "--prod", action="store_true", help="Enter the 'production' environment"
        )
        parser.add_argument("--lab", action="store_true", help="Enter the 'lab' environment")
        parser.add_argument(
            "--light", action="store_true", help="Enter the 'lightweight' environment"
        )

    def handle(self, args: argparse.Namespace) -> None:
        if args.lab:
            envrionment = Lab()
        elif args.light:
            envrionment = Lightweight()
        elif args.prod:
            envrionment = Production()
        else:
            envrionment = Environment()
        envrionment.enter()
