import signal
import os


class Workload:
    DEPENDENCIES = []

    def __init__(self) -> None:
        self.process = None

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        try:
            if self.process:
                os.killpg(os.getpgid(self.process.pid), signal.SIGTERM)
        except ProcessLookupError:
            pass
        return False

    def __str__(self) -> str:
        return self.__class__.__name__.lower()

    def nix_wrapped(self, command: str) -> list[str]:
        return (
            ["nix-shell", "--no-build-output", "--quiet", "--packages"]
            + self.DEPENDENCIES
            + ["--run", command]
        )
