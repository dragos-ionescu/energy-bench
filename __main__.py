#!/usr/bin/env python3
import argparse
import os

from environments import *
from workloads import *
from commands import *
from utils import *


def main():
    base_dir = os.path.join(os.path.expanduser("~"), ".energy-bench")
    if not os.path.exists(base_dir) or not os.path.isdir(base_dir):
        raise ProgramError("base dir does not exist. Please install first with `make install`")

    parser = argparse.ArgumentParser(
        prog="energy-bench", description="Measure and analyze the energy consumption of your code."
    )
    subparsers = parser.add_subparsers(dest="command", required=True, help="Available commands")

    for name, cls in BaseCommand.registry.items():
        sub = subparsers.add_parser(name, help=cls.help)
        cmd = cls(base_dir)
        cmd.add_args(sub)
        sub.set_defaults(instance=cmd)

    args = parser.parse_args()

    try:
        args.instance.handle(args)
    except ProgramError as ex:
        print_error(str(ex))


if __name__ == "__main__":
    errors = False
    try:
        main()
    except ProgramError as ex:
        print_error(str(ex))
        errors = True

    if errors:
        print_warning(f"program finished with errors")
