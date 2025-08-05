import openai
import os
from .openai import OpenAILLM
from utils import *


class DeepSeekLLM(OpenAILLM):
    chat_models = ["deepseek-chat"]
    reasoning_models = ["deepseek-reasoner"]

    def __init__(self, base_dir: str) -> None:
        super().__init__(base_dir)
        try:
            self.client = openai.OpenAI(
                api_key=os.environ["DEEPSEEK_API_KEY"], base_url="https://api.deepseek.com"
            )
        except openai.OpenAIError as ex:
            raise ProgramError(f"failed to initialize llm model - {ex}")

    def single(self, model: str, message: str) -> str | None:
        try:
            response = self.client.chat.completions.create(
                model=model, messages=[{"role": "user", "content": message}]
            )
            return response.choices[0].message.content
        except openai.OpenAIError as ex:
            raise ProgramError(f"failed while generating response - {ex}")
        except Exception as ex:
            raise ProgramError(f"unexpected error while generating response - {ex}")

    def batch(self, model: str, messages: list[str]) -> list[dict]:
        raise ProgramError(
            "DeepSeek doesn't support batching. Run --single at 16:30-00:30 UTC for half the price!"
        )

    def fetch(self, model: str) -> int:
        print_warning("DeepSeek doesn't support batch operations")
        return 0
