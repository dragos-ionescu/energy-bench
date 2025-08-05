from abc import ABC, abstractmethod
from dotenv import load_dotenv
import itertools
import hashlib
import json
import os
import re

from scenario import Scenario
from implementations import *


class LLM(ABC):
    chat_models = []
    reasoning_models = []

    DEFAULT_TEMPERATURE = 0
    DEFAULT_MAX_TOKENS = 8192
    REASONING_MAX_TOKENS = 25_000

    def __init__(self, base_dir: str) -> None:
        load_dotenv()
        self.base_dir = base_dir

    @abstractmethod
    def single(self, model: str, message: str) -> str | None:
        return None

    @abstractmethod
    def batch(self, model: str, messages: list[str]) -> list[dict]:
        return []

    @abstractmethod
    def fetch(self, model: str) -> int:
        return 0

    @abstractmethod
    def available(self) -> set[str]:
        return set()

    def hash_from_message(self, message: str) -> str:
        return hashlib.sha256(message.encode()).hexdigest()[:64]

    def save_code(self, model: str, scenario: Scenario, cid: str, code: str | None = None) -> str:
        scenario_dir = os.path.join(self.base_dir, "scenarios", model, scenario.implementation)
        os.makedirs(scenario_dir, exist_ok=True)
        scenario_path = os.path.join(scenario_dir, f"{cid}.yml" if cid else f"{scenario.name}.yml")
        scenario.model = model
        if code:
            scenario.code = code
        scenario.save(scenario_path)
        return scenario_path

    def save_batch(self, model: str, data: list[dict], bid: str) -> str:
        batch_dir = os.path.join(self.base_dir, "batches", model)
        os.makedirs(batch_dir, exist_ok=True)
        batch_path = os.path.join(batch_dir, f"{bid}.jsonl")
        with open(batch_path, "w") as f:
            for d in data:
                f.write(json.dumps(d) + "\n")
        return batch_path

    def remove_batch(self, model: str, bid: str) -> None:
        batch_dir = os.path.join(self.base_dir, "batches", model)
        batch_path = os.path.join(batch_dir, f"{bid}.jsonl")
        if os.path.exists(batch_path):
            os.remove(batch_path)

    def clean_response(self, response: str) -> str:
        if "<code>" in response and "</code>" in response:
            return response

        patterns = [
            (
                r"```(?:c|cpp|java|csharp|python|javascript|js|py|ruby|rust)?\s*\n(.*?)\n```",
                r"<code>\1</code>",
            ),
            (
                r"```(?:c|cpp|java|csharp|python|javascript|js|py|ruby|rust)?\s*(.*?)```",
                r"<code>\1</code>",
            ),
        ]

        cleaned = response
        for pattern, replacement in patterns:
            cleaned = re.sub(pattern, replacement, cleaned, flags=re.DOTALL)

        return cleaned

    def get_code(self, content: str) -> str | None:
        content = self.clean_response(content)

        xml_match = re.search(r"<code>(.*?)</code>", content, flags=re.DOTALL)
        if xml_match:
            code = xml_match.group(1).strip()
            if code:
                return code

        markdown_patterns = [
            r"```(?:c|cpp|java|csharp|python|javascript|js|py|ruby|rust)?\s*\n(.*?)\n```",
            r"```(?:c|cpp|java|csharp|python|javascript|js|py|ruby|rust)?\s*(.*?)```",
        ]

        for pattern in markdown_patterns:
            markdown_match = re.search(pattern, content, flags=re.DOTALL)
            if markdown_match:
                code = markdown_match.group(1).strip()
                if code:
                    return code

        fallback_match = re.search(r"```[^`]*```", content, flags=re.DOTALL)
        if fallback_match:
            block = fallback_match.group(0)
            lines = block.split("\n")
            if len(lines) > 2:
                code_lines = lines[1:-1]
                code = "\n".join(code_lines).strip()
                if code:
                    return code

        return None

    def latest_batch(self, model: str) -> str | None:
        batch_dir = os.path.join(self.base_dir, "batches", model)
        if not os.path.exists(batch_dir):
            return None
        entries = (os.path.join(batch_dir, fn) for fn in os.listdir(batch_dir))
        files = [f for f in entries if os.path.isfile(f)]
        files.sort(key=os.path.getctime)
        if files:
            latest_file = files[-1]
            return os.path.splitext(os.path.basename(latest_file))[0]
        return None


class Instructions:
    instructions = []

    def get_instructions(self) -> str:
        instruction_list = ""
        for i in self.instructions:
            instruction_list += f"- {i}\n"
        return instruction_list


class Task:
    def __init__(self, scenario: Scenario) -> None:
        self.scenario = scenario

    def get_task(self) -> str:
        task = (
            f"## NAME: {self.scenario.name}\n"
            f"## IMPLEMENTATION: {self.scenario.implementation}\n"
            f"## DESCRIPTION: <DESCRIPTION>{self.scenario.description}</DESCRIPTION>\n"
            f"## REQUIREMENTS:\n"
            f"<DEPENDENCIES>{json.dumps(self.scenario.dependencies)}</DEPENDENCIES>\n"
        )
        if self.scenario.options:
            task += f"<BUILD OPTIONS>{json.dumps(self.scenario.options)}</BUILD OPTIONS>\n"
        if self.scenario.implementation in Cs.aliases and self.scenario.packages:
            package_refs = [f"{p['name']}={p['version']}" for p in self.scenario.packages]
            task += f"<PACKAGES>{json.dumps(package_refs)}</PACKAGES>\n"
        elif self.scenario.implementation in GraalVm.aliases + OpenJdk.aliases:
            if self.scenario.class_paths:
                task += f"<CLASS PATHS>{json.dumps(self.scenario.class_paths)}</CLASS PATHS>\n"
            if self.scenario.roptions:
                task += f"<RUNTIME OPTIONS>{json.dumps(self.scenario.roptions)}</RUNTIME OPTIONS>\n"
        task += f"<HARDWARE>{self.scenario.hardware}</HARDWARE>\n"
        return task


class SignalInstructions(Instructions):
    instructions = [
        "Your solution MUST use the signal structure shown below.",
        "Place solution code between the 'start signal' and 'stop signal' calls.",
        "The signal functions are provided for you, so you can use them directly.",
        "Program state MUST be reset between iterations to ensure consistency.",
        "Each iteration MUST do the same amount of work everytime.",
    ]


class EnergyOptimizationInstructions(Instructions):
    instructions = [
        "CRITICAL! Your solution MUST prioritize energy efficiency for the hardware platform provided."
    ]


class RuntimeOptimizationInstructions(Instructions):
    instructions = [
        "CRITICAL! Your solution MUST be as efficient as possible for the hardware platform provided."
    ]


class CInstructions(Instructions):
    instructions = ["Define your main function correctly."]


class CppInstructions(Instructions):
    instructions = ["Define your main function correctly."]


class CsInstructions(Instructions):
    instructions = ["Define your main function in a public class called 'Program'."]


class JavaInstructions(Instructions):
    instructions = ["Define your main function in a public class called 'Program'."]


class PythonInstructions(Instructions):
    instructions = ["Define your main entry point correctly."]


class RubyInstructions(Instructions):
    instructions = ["Define your main entry point correctly."]


class RustInstructions(Instructions):
    instructions = ["Define your main function correctly."]


class ExampleTask(Task):
    def get_task(self) -> str:
        task = super().get_task()
        if self.scenario.code:
            task += f"## SOLUTION CODE: <code>{self.scenario.code}</code>\n"
        return task


class ScenarioTask(Task):
    def get_task(self) -> str:
        task = super().get_task()
        example_runs = []
        for test in itertools.islice(self.scenario.get_tests(), 2):
            example = (
                "### SUCCESSFUL RUN EXAMPLE:\n"
                f"<CMD ARGS>{json.dumps(test.args)}</CMD ARGS>\n"
                f"<INPUT>{self._truncate_bytes(test.stdin)}</INPUT>\n"
                f"<EXPECTED OUTPUT>{self._truncate_bytes(test.expected_stdout)}</EXPECTED OUTPUT>\n"
            )
            example_runs.append(example)
        return task + "".join(example_runs)

    def _truncate_bytes(self, data: bytes, max_bytes=256):
        decoded = data[:max_bytes].decode(errors="ignore").strip()
        if len(data) > max_bytes:
            decoded += "…"
        return decoded


class Prompt(ABC):
    def __init__(
        self, task: Task, examples: list[Task] = [], instructions: list[Instructions] = []
    ) -> None:
        self.task = task
        self.examples = examples
        self.instructions = instructions

    def build_prompt(self) -> str:
        prompt = self._get_instructions()

        prompt += (
            "# OUTPUT FORMAT EXAMPLE:\n"
            "For a hello world program in C, your response should look exactly like this:\n"
            '<code>#include <stdio.h>\nint main() {\n    printf("Hello World\\n");\n    return 0;\n}</code>\n\n'
        )

        if self.examples:
            prompt += f"# EXAMPLES:\n{' '.join([ex.get_task() for ex in self.examples])}\n"

        prompt += (
            f"# TASK:\n{self.task.get_task()}\n"
            "GENERATING SOLUTIONS THAT DON'T ADHERE TO THESE STRICT RULES WILL LEAD TO TERMINATION"
        )
        return prompt

    def _get_instructions(self) -> str:
        return (
            "# INSTRUCTIONS:\n"
            f"- You are an expert at solving programming problems.\n"
            f"- Generate solutions that exactly match requirements.\n"
            f"- Solutions must be production-ready.\n"
            f"{self._format_custom_instructions()}"
            f"- CRITICAL: Use ONLY <code> and </code> tags to wrap your solution.\n"
            f"- DO NOT use triple backticks (```) or any markdown formatting.\n"
            f"- DO NOT add any comments or debug statements.\n"
            f"- Ensure code is clearly formatted and idiomatic for {self.task.scenario.implementation}.\n"
        )

    def _format_custom_instructions(self) -> str:
        if not self.instructions:
            return ""

        formatted = ""
        for instruction_set in self.instructions:
            formatted += instruction_set.get_instructions()
        return formatted
