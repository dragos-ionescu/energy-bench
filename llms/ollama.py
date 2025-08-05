from .base import LLM


class OllamaLLM(LLM):
    def single(self, model: str, message: str) -> str | None:
        return None

    def batch(self, model: str, messages: list[str]) -> list[dict]:
        return []

    def fetch(self, model: str) -> int:
        return 0

    def available(self) -> set[str]:
        return set()

    # def generate_ollama(self, model: str, context: str, task: str) -> str | None:
    #     import ollama

    #     llm_available = False

    #     for _, ms in ollama.list():
    #         for m in ms:
    #             if model == m.model:
    #                 llm_available = True

    #     if not llm_available:
    #         raise ProgramError(f"{model} not available")

    #     try:
    #         response = ollama.generate(model=model, prompt=context + task)
    #         return response.response
    #     except (ollama.ResponseError, ConnectionError) as ex:
    #         raise ProgramError(f"failed while generating ollama reponse using model {model} - {ex}")
