from typing import Any
import openai
import json
import os

from scenario import Scenario
from .base import LLM
from utils import *


class OpenAILLM(LLM):
    chat_models = ["gpt-4.1", "gpt-4.1-mini", "gpt-4.1-nano", "gpt-4o", "gpt-4o-mini"]
    reasoning_models = ["o1", "o1-mini", "o3", "o3-mini", "o4-mini"]

    REASONING_EFFORT = "medium"

    def __init__(self, base_dir: str) -> None:
        super().__init__(base_dir)
        try:
            self.client = openai.OpenAI()
        except openai.OpenAIError as ex:
            raise ProgramError(f"failed to initialize llm model - {ex}")

    def _get_model_config(self, model: str) -> dict[str, Any]:
        if model in self.reasoning_models:
            return {
                "reasoning": {"effort": self.REASONING_EFFORT},
                "max_output_tokens": self.REASONING_MAX_TOKENS,
            }
        else:
            return {
                "temperature": self.DEFAULT_TEMPERATURE,
                "max_completion_tokens": self.DEFAULT_MAX_TOKENS,
            }

    def single(self, model: str, message: str) -> str | None:
        try:
            config = self._get_model_config(model)

            if model in self.reasoning_models:
                response = self.client.responses.create(
                    model=model,
                    reasoning=config["reasoning"],
                    max_output_tokens=config["max_output_tokens"],
                    input=[{"role": "user", "content": message}],
                )
                return response.output_text
            else:
                response = self.client.chat.completions.create(
                    model=model,
                    messages=[{"role": "user", "content": message}],
                    temperature=config["temperature"],
                    max_completion_tokens=config["max_completion_tokens"],
                )
                return response.choices[0].message.content

        except openai.OpenAIError as ex:
            raise ProgramError(f"failed while generating response - {ex}")
        except Exception as ex:
            raise ProgramError(f"unexpected error while generating response - {ex}")

    def _create_batch_request(self, model: str, message: str) -> dict[str, Any]:
        if model in self.reasoning_models:
            body = {
                "model": model,
                "input": [{"role": "user", "content": message}],
                "max_output_tokens": self.REASONING_MAX_TOKENS,
                "reasoning": {"effort": self.REASONING_EFFORT},
            }
        else:
            body = {
                "model": model,
                "messages": [{"role": "user", "content": message}],
                "temperature": self.DEFAULT_TEMPERATURE,
                "max_completion_tokens": self.DEFAULT_MAX_TOKENS,
            }

        endpoint = "/v1/responses" if model in self.reasoning_models else "/v1/chat/completions"

        return {
            "custom_id": self.hash_from_message(message),
            "method": "POST",
            "url": endpoint,
            "body": body,
        }

    def batch(self, model: str, messages: list[str]) -> list[dict]:
        if not messages:
            print_warning("no messages provided for batch processing")
            return []

        batch_id = self.latest_batch(model)
        if batch_id:
            batch_status = self._get_batch_status(batch_id)
            if batch_status in {"in_progress", "validating", "finalizing"}:
                print_warning(f"{model} batch {batch_status}")
                return []

        try:
            requests = [self._create_batch_request(model, msg) for msg in messages]

            batch_path = self.save_batch(model, requests, "batch")

            with open(batch_path, "rb") as batch_file:
                batch_file_obj = self.client.files.create(file=batch_file, purpose="batch")

            endpoint = "/v1/responses" if model in self.reasoning_models else "/v1/chat/completions"
            batch = self.client.batches.create(
                input_file_id=batch_file_obj.id, endpoint=endpoint, completion_window="24h"
            )

            new_batch_path = batch_path.replace("batch.jsonl", f"{batch.id}.jsonl")
            os.rename(batch_path, new_batch_path)

            print_info(f"{model} batch {batch.id} started with {len(requests)} requests")
            return requests

        except openai.OpenAIError as ex:
            raise ProgramError(f"failed while creating batch - {ex}")
        except Exception as ex:
            raise ProgramError(f"unexpected error while creating batch - {ex}")

    def _get_batch_status(self, batch_id: str) -> str:
        try:
            info = self.client.batches.retrieve(batch_id)
            return info.status
        except openai.OpenAIError as ex:
            return "failed"

    def _process_batch_response_line(self, line: str, model: str) -> str | None:
        if not line.strip():
            return None

        try:
            response = json.loads(line)
        except json.JSONDecodeError as ex:
            return None

        custom_id = response.get("custom_id")
        if not custom_id:
            print_warning("batch response missing custom_id")
            return None

        scenario = self._find_scenario_by_id(model, custom_id)
        if not scenario:
            print_warning(f"no scenario found for custom_id: {custom_id}")
            return None

        response_body = response.get("response", {}).get("body", {})

        if model in self.reasoning_models:
            outputs = response_body.get("output", [])
            if not outputs:
                print_warning(f"{model} no output for {scenario.implementation} {scenario.name}")
                return None

            output_text = ""
            for output in outputs:
                if output.get("type") == "message":
                    content = output.get("content", [])
                    if content and len(content) > 0:
                        output_text = content[0].get("text", "")
                        break
        else:
            choices = response_body.get("choices", [])
            if not choices:
                print_warning(f"{model} no choices for {scenario.implementation} {scenario.name}")
                return None
            output_text = choices[0].get("message", {}).get("content", "")

        if not output_text:
            print_warning(f"{model} empty response for {scenario.implementation} {scenario.name}")
            return None

        code = self.get_code(output_text)
        if not code:
            print_warning(
                f"{model} no code extracted for {scenario.implementation} {scenario.name}"
            )
            return None

        scenario_path = self.save_code(model, scenario, custom_id, code)
        return scenario_path

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
                        print(f"failed while loading scenario from {scenario_path}: {ex}")
                        continue
        return None

    def _handle_batch_error(self, batch_info) -> None:
        if not batch_info.error_file_id:
            raise ProgramError("batch failed with no error file available")

        try:
            error_response = self.client.files.content(batch_info.error_file_id)
            error_data = json.loads(error_response.content)
            error_message = (
                error_data.get("response", {})
                .get("body", {})
                .get("error", {})
                .get("message", "Unknown error")
            )
            raise ProgramError(f"batch processing failed - {error_message}")
        except json.JSONDecodeError:
            raise ProgramError("batch failed with unparseable error response")

    def fetch(self, model: str) -> int:
        batch_id = self.latest_batch(model)
        if not batch_id:
            return -1

        try:
            batch_info = self.client.batches.retrieve(batch_id)
            status = batch_info.status

            if status != "completed":
                print_warning(f"{model} batch {status}")
                return 0

            if not batch_info.output_file_id:
                self._handle_batch_error(batch_info)
                return 0

            responses = self.client.files.content(batch_info.output_file_id)
            fetched = 0

            for line in responses.content.splitlines():
                scenario_path = self._process_batch_response_line(line.decode("utf-8"), model)
                if scenario_path:
                    print_success(f"saved {scenario_path}")
                    fetched += 1

            self.remove_batch(model, batch_id)
            self.client.files.delete(batch_info.output_file_id)

            print_info(f"Fetched {fetched} results for {model}")
            return fetched

        except openai.OpenAIError as ex:
            raise ProgramError(f"failed while fetching batch - {ex}")
        except Exception as ex:
            raise ProgramError(f"unexpected error while fetching batch - {ex}")

    def available(self) -> set[str]:
        try:
            available = set()
            response = self.client.models.list()

            while True:
                for model in response.data:
                    available.add(model.id)

                if not response.has_next_page():
                    break
                response = response.get_next_page()

            return available

        except openai.OpenAIError as ex:
            raise ProgramError(f"failed while checking model availability - {ex}")
        except Exception as ex:
            raise ProgramError(f"unexpected error while checking model availability - {ex}")
