from typing import Any
import argparse
import os

from scenario import Scenario
from .base import BaseCommand
from implementations import *
from llms.base import *
from utils import *
from llms import *


class GenerateCommand(BaseCommand):
    name = "generate"
    help = "Use LLMs to generate and save a scenario solution"

    PROVIDER_CONFIG = {
        "ollama": {"llm_class": OllamaLLM},
        "openai": {"llm_class": OpenAILLM},
        "deepseek": {"llm_class": DeepSeekLLM},
        "anthropic": {"llm_class": AnthropicLLM},
    }

    IMPLEMENTATION_MAPPING = {
        "C": {"aliases": C.aliases, "istr": "c", "instructions": CInstructions},
        "Cs": {"aliases": Cs.aliases, "istr": "cs", "instructions": CsInstructions},
        "Cpp": {"aliases": Cpp.aliases, "istr": "cpp", "instructions": CppInstructions},
        "GraalVm": {
            "aliases": GraalVm.aliases,
            "istr": "graalvm",
            "instructions": JavaInstructions,
        },
        "OpenJdk": {
            "aliases": OpenJdk.aliases,
            "istr": "openjdk",
            "instructions": JavaInstructions,
        },
        "Python": {"aliases": Python.aliases, "istr": "python", "instructions": PythonInstructions},
        "Ruby": {"aliases": Ruby.aliases, "istr": "ruby", "instructions": RubyInstructions},
        "Rust": {"aliases": Rust.aliases, "istr": "rust", "instructions": RustInstructions},
    }

    def add_args(self, parser: argparse.ArgumentParser) -> None:
        parser.add_argument("--ollama", nargs="*", help="defaults to a predefined list of models")
        parser.add_argument("--openai", nargs="*", help="defaults to a predefined list of models")
        parser.add_argument("--deepseek", nargs="*", help="defaults to a predefined list of models")
        parser.add_argument(
            "--anthropic", nargs="*", help="defaults to a predefined list of models"
        )

        parser.add_argument(
            "-s",
            "--single",
            nargs="+",
            default=[],
            help="generates solutions immediately for each scenario",
        )
        parser.add_argument(
            "-b",
            "--batch",
            nargs="+",
            default=[],
            help="creates a batch for all scenarios so that you can fetch them later",
        )
        parser.add_argument("-f", "--fetch", action="store_true", help="fetch batches")
        parser.add_argument(
            "--stop", action="store_true", help="stop immediately if something wrong happened"
        )
        parser.add_argument("-g", "--signal", action="store_true", help="add signal instructions")
        parser.add_argument(
            "-o",
            "--energy-optimize",
            action="store_true",
            help="adds energy optimization instructions",
        )
        parser.add_argument(
            "-r",
            "--runtime-optimize",
            action="store_true",
            help="adds runtime optimization instructions",
        )
        parser.add_argument(
            "-e",
            "--example",
            action="store_true",
            help="adds one-shot example for the specified optimization",
        )

    def get_implementation_config(self, implementation: str) -> dict[str, Any]:
        for _, config in self.IMPLEMENTATION_MAPPING.items():
            if implementation in config["aliases"]:
                return config
        raise ProgramError(f"{implementation} not supported")

    def get_example_file(self, args: argparse.Namespace) -> str:
        if args.signal and args.energy_optimize:
            return "signal_optimized.yml"
        elif args.signal:
            return "signal.yml"
        elif args.energy_optimize:
            return "optimized_energy.yml"
        else:
            return "unoptimized.yml"

    def build_instructions(self, scenario: Scenario, args: argparse.Namespace) -> list[Any]:
        instructions = []

        if args.signal:
            instructions.append(SignalInstructions())
        if args.energy_optimize:
            instructions.append(EnergyOptimizationInstructions())
        if args.runtime_optimize:
            instructions.append(RuntimeOptimizationInstructions())

        impl_config = self.get_implementation_config(scenario.implementation)
        instructions.append(impl_config["instructions"]())

        return instructions

    def build_examples(self, scenario: Scenario, args: argparse.Namespace) -> list[Any]:
        examples = []

        if args.example:
            impl_config = self.get_implementation_config(scenario.implementation)
            example_file = self.get_example_file(args)
            example_path = os.path.join(
                self.base_dir, "examples", impl_config["istr"], example_file
            )

            try:
                example = Scenario.from_yaml(example_path)
                examples.append(ExampleTask(example))
            except Exception as ex:
                self.record_issue(f"failed to load example from {example_path}: {ex}", True)

        return examples

    def get_prompt(self, scenario: Scenario, args: argparse.Namespace) -> str:
        try:
            task = ScenarioTask(scenario)
            instructions = self.build_instructions(scenario, args)
            examples = self.build_examples(scenario, args)

            prompt = Prompt(task, examples, instructions)
            return prompt.build_prompt()
        except Exception as ex:
            raise ProgramError(f"failed to build prompt for {scenario.name}: {ex}")

    def get_requested_models(self, args: argparse.Namespace) -> dict[str, dict[str, Any]]:
        requested_models = {}

        for provider, config in self.PROVIDER_CONFIG.items():
            models = getattr(args, provider, None)
            if models is None:
                continue

            if models == []:
                llm_class = config["llm_class"]
                models = llm_class.chat_models + llm_class.reasoning_models

            if models:
                requested_models[provider] = {"models": models, "llm_class": config["llm_class"]}

        return requested_models

    def validate_models(
        self, provider: str, models: list[str], available: set[str], args: argparse.Namespace
    ) -> list[str]:
        valid_models = []
        for model in models:
            if model in available:
                valid_models.append(model)
            else:
                self.record_issue(f"{model} is not a valid {provider} model", args.stop)
        return valid_models

    def process_single_scenarios(
        self, args: argparse.Namespace, llm: Any, models: list[str]
    ) -> None:
        for file in args.single:
            try:
                scenario = Scenario.from_yaml(file)
                prompt = self.get_prompt(scenario, args)
                print(prompt)
                exit(1)
                for model in models:
                    try:
                        content = llm.single(model, prompt)
                        if not content:
                            self.record_issue(f"{model} returned empty response", args.stop)
                            continue

                        code = llm.get_code(content)
                        if not code:
                            self.record_issue(f"{model} didn't output any code", args.stop)
                            continue

                        cid = llm.hash_from_message(prompt)
                        scenario_path = llm.save_code(model, scenario, cid, code)
                        print_success(f"{model} saved {scenario_path}")

                    except Exception as ex:
                        self.record_issue(
                            f"{model} error processing scenario {file}: {ex}", args.stop
                        )

            except ProgramError as ex:
                self.record_issue(str(ex), args.stop)

    def process_batch_scenarios(
        self, args: argparse.Namespace, llm: Any, models: list[str]
    ) -> None:
        if not args.batch:
            return

        batch_data = []
        for file in args.batch:
            try:
                scenario = Scenario.from_yaml(file)
                prompt = self.get_prompt(scenario, args)
                batch_data.append((scenario, prompt))
            except ProgramError as ex:
                self.record_issue(str(ex), args.stop)

        if not batch_data:
            return

        scenarios, batch_prompts = zip(*batch_data)

        for model in models:
            try:
                requests = llm.batch(model, list(batch_prompts))
                if not requests:
                    print_warning(f"{model} batch creation returned no requests")
                    continue

                for scenario, request in zip(scenarios, requests):
                    if "custom_id" in request:
                        cid = request["custom_id"]
                        try:
                            llm.save_code(model, scenario, cid)
                        except Exception as ex:
                            print_warning(f"failed to save code metadata for {scenario.name}: {ex}")

            except Exception as ex:
                self.record_issue(f"{model} batch processing error: {ex}", args.stop)

    def process_fetch(self, llm: Any, models: list[str]) -> None:
        for model in models:
            try:
                fetched = llm.fetch(model)
                if fetched < 0:
                    print_info(f"{model} no ongoing batches")
                elif fetched == 0:
                    print_info(f"{model} batch not ready or no results")
                else:
                    print_info(f"{model} fetched {fetched} results")
            except Exception as ex:
                print_warning(f"{model} fetch error: {ex}")

    def handle(self, args: argparse.Namespace) -> None:
        self.welcome()
        requested_models = self.get_requested_models(args)

        if not requested_models:
            print_info("No models specified")
            return

        for provider, config in requested_models.items():
            models = config["models"]
            llm_class = config["llm_class"]

            try:
                llm = llm_class(self.base_dir)
                available = llm.available()

                valid_models = self.validate_models(provider, models, available, args)
                if not valid_models:
                    print_warning(f"No valid models for {provider}")
                    continue

                if args.fetch:
                    self.process_fetch(llm, valid_models)
                else:
                    self.process_single_scenarios(args, llm, valid_models)
                    self.process_batch_scenarios(args, llm, valid_models)

            except Exception as ex:
                self.record_issue(f"failed to initialize {provider} LLM: {ex}", args.stop)

        self.goodbye()
