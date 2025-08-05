from typing import Any
import anthropic
import os

from scenario import Scenario
from .base import LLM
from utils import *


class AnthropicLLM(LLM):
    chat_models = ["claude-3-5-sonnet-20241022", "claude-3-5-haiku-20241022"]
    reasoning_models = ["claude-3-7-sonnet-20250219"]

    REASONING_BUDGET_TOKENS = 20_000

    def __init__(self, base_dir: str) -> None:
        super().__init__(base_dir)
        try:
            self.client = anthropic.Anthropic()
        except anthropic.AnthropicError as ex:
            raise ProgramError(f"failed to initialize llm model - {ex}")

    def _get_model_config(self, model: str) -> dict[str, Any]:
        if model in self.reasoning_models:
            return {
                "thinking": {"type": "enabled", "budget_tokens": self.REASONING_BUDGET_TOKENS},
                "max_tokens": self.REASONING_MAX_TOKENS,
                "temperature": anthropic.NOT_GIVEN,
            }
        else:
            return {
                "thinking": anthropic.NOT_GIVEN,
                "max_tokens": self.DEFAULT_MAX_TOKENS,
                "temperature": self.DEFAULT_TEMPERATURE,
            }

    def single(self, model: str, message: str) -> str | None:
        try:
            config = self._get_model_config(model)

            response = self.client.messages.create(
                model=model,
                thinking=config["thinking"],
                max_tokens=config["max_tokens"],
                temperature=config["temperature"],
                messages=[{"role": "user", "content": message}],
            )

            for content in response.content:
                if content.type == "text":
                    return content.text
            return None

        except anthropic.AnthropicError as ex:
            raise ProgramError(f"failed while generating response - {ex}")
        except Exception as ex:
            raise ProgramError(f"unexpected error while generating response - {ex}")

    def _create_batch_request(self, model: str, message: str) -> dict[str, Any]:
        config = self._get_model_config(model)

        params = {
            "model": model,
            "max_tokens": config["max_tokens"],
            "messages": [{"role": "user", "content": message}],
        }

        if model in self.reasoning_models:
            params["thinking"] = config["thinking"]
        else:
            params["temperature"] = config["temperature"]

        return {"custom_id": self.hash_from_message(message), "params": params}

    def batch(self, model: str, messages: list[str]) -> list[dict]:
        if not messages:
            print_warning("No messages provided for batch processing")
            return []

        batch_id = self.latest_batch(model)
        if batch_id:
            batch_status = self._get_batch_status(batch_id)
            if batch_status in {"in_progress", "cancelling", "ended"}:
                print_warning(f"{model} batch {batch_status}")
                return []

        try:
            requests = [self._create_batch_request(model, msg) for msg in messages]

            response = self.client.messages.batches.create(requests=requests)
            self.save_batch(model, requests, response.id)

            print_info(f"{model} batch {response.id} started with {len(requests)} requests")
            return requests

        except anthropic.AnthropicError as ex:
            raise ProgramError(f"failed while creating batch - {ex}")
        except Exception as ex:
            raise ProgramError(f"unexpected error while creating batch - {ex}")

    def _get_batch_status(self, batch_id: str) -> str:
        try:
            info = self.client.messages.batches.retrieve(batch_id)
            return info.processing_status
        except anthropic.AnthropicError as ex:
            return "failed"

    def _find_scenario_by_id(self, model: str, custom_id: str) -> Scenario | None:
        scenarios_dir = os.path.join(self.base_dir, "scenarios", model)

        if not os.path.exists(scenarios_dir):
            return None

        for dirpath, _, filenames in os.walk(scenarios_dir):
            for filename in filenames:
                if custom_id in filename:
                    scenario_path = os.path.join(dirpath, filename)
                    try:
                        return Scenario.from_yaml(scenario_path)
                    except Exception as ex:
                        print(f"Error loading scenario from {scenario_path}: {ex}")
                        continue
        return None

    def _process_batch_response(self, response, model: str) -> str | None:
        custom_id = response.custom_id
        result = response.result

        scenario = self._find_scenario_by_id(model, custom_id)
        if not scenario:
            print_warning(f"No scenario found for custom_id: {custom_id}")
            return None

        if result.type != "succeeded":
            print_warning(
                f"{model} batch for {scenario.implementation} {scenario.name} {result.type}"
            )
            return None

        text_parts = [
            block.text
            for block in result.message.content
            if block.type == "text" and hasattr(block, "text") and block.text
        ]

        if not text_parts:
            print_warning(f"{model} no text content for {scenario.implementation} {scenario.name}")
            return None

        code_blob = "".join(text_parts)
        code = self.get_code(code_blob)

        if not code:
            print_warning(
                f"{model} no code extracted for {scenario.implementation} {scenario.name}"
            )
            return None

        scenario_path = self.save_code(model, scenario, custom_id, code)
        return scenario_path

    def fetch(self, model: str) -> int:
        batch_id = self.latest_batch(model)
        if not batch_id:
            return -1

        try:
            batch_info = self.client.messages.batches.retrieve(batch_id)
            status = batch_info.processing_status

            if status != "ended":
                print_warning(f"{model} batch {status}")
                return 0

            responses = self.client.messages.batches.results(batch_id)
            fetched = 0

            for response in responses:
                scenario_path = self._process_batch_response(response, model)
                if scenario_path:
                    print_success(f"saved {scenario_path}")
                    fetched += 1

            self.remove_batch(model, batch_id)

            try:
                self.client.messages.batches.delete(batch_id)
            except anthropic.AnthropicError as ex:
                print(f"Warning: Could not delete batch {batch_id}: {ex}")

            print_info(f"Fetched {fetched} results for {model}")
            return fetched

        except anthropic.AnthropicError as ex:
            raise ProgramError(f"failed while fetching batch - {ex}")
        except Exception as ex:
            raise ProgramError(f"unexpected error while fetching batch - {ex}")

    def available(self) -> set[str]:
        try:
            available = set()
            response = self.client.models.list(limit=20)

            while True:
                for model in response.data:
                    available.add(model.id)

                if not response.has_more or not response.last_id:
                    break

                response = self.client.models.list(limit=20, after_id=response.last_id)

            return available

        except anthropic.AnthropicError as ex:
            raise ProgramError(f"failed while checking model availability - {ex}")
        except Exception as ex:
            raise ProgramError(f"unexpected error while checking model availability - {ex}")
