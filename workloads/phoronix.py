from subprocess import SubprocessError
import subprocess
import os

from utils import ProgramError, print_info
from .base import Workload


class PhoronixWorkload(Workload):
    DEPENDENCIES = ["phoronix-test-suite"]
    TEST_CHOICE = -1
    TEST = ""

    def _install_test(self) -> None:
        cmd = f"phoronix-test-suite install {self.TEST}"
        cmd = self.nix_wrapped(cmd)
        print_info(f"installing Phoronix workload '{self.TEST}'")
        subprocess.run(cmd, check=True, capture_output=True)

    def __enter__(self):
        try:
            self._install_test()
        except SubprocessError as ex:
            raise ProgramError(f"failed while installing workload '{self.TEST}' – {ex}") from ex

        cmd = f"phoronix-test-suite stress-run {self.TEST}"
        cmd = self.nix_wrapped(cmd)

        env = os.environ.copy()
        env.update({"TOTAL_LOOP_TIME": "9999"})  # effectively “infinite”
        try:
            self.process = subprocess.Popen(
                cmd,
                env=env,
                stdin=subprocess.PIPE,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                preexec_fn=os.setsid,
            )
            if self.TEST_CHOICE >= 0 and self.process.stdin:
                self.process.stdin.write(f"{self.TEST_CHOICE}\n".encode())
                self.process.stdin.close()

        except OSError as ex:
            raise ProgramError(f"failed while running workload – {ex}")

        return self


class GimpResize(PhoronixWorkload):
    TEST = "system/gimp"
    TEST_CHOICE = 2  # Test choise for resize
