from subprocess import CalledProcessError
from abc import abstractmethod
import subprocess
import shutil
import os

from .base import Workload
from utils import ProgramError


class BrowserWorkload(Workload):
    PROFILE_DIR = "/tmp/"
    DEPENDENCIES = ["xorg.xvfb"]

    def __enter__(self):
        shutil.rmtree(self.PROFILE_DIR, ignore_errors=True)
        os.makedirs(self.PROFILE_DIR, exist_ok=True)
        command = f"Xvfb :99 & sleep 1 ; {self.open_sites()}"
        command = self.nix_wrapped(command)
        try:
            self.process = subprocess.Popen(
                args=command, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, process_group=0
            )
        except CalledProcessError as ex:
            raise ProgramError(f"failed while starting workload - {ex}")
        return self

    @abstractmethod
    def open_sites(self, display: int = 99) -> str:
        ...


class Brave(BrowserWorkload):
    PROFILE_DIR = "/tmp/brave-profile"
    DEPENDENCIES = ["brave", "xorg.xvfb"]

    def open_sites(self, display: int = 99) -> str:
        urls = [
            "https://www.youtube.com/watch?v=xm3YgoEiEDc&autoplay=1",
            "https://www.google.com/",
            "https://open.spotify.com/",
            "https://www.amazon.com/",
        ]
        urls_arg = " ".join(f"'{u}'" for u in urls)
        return (
            f"brave --display=:{display} --new-window "
            f"--no-first-run --disable-session-crashed-bubble "
            f"--enable-unsafe-swiftshader "
            f"--user-data-dir={self.PROFILE_DIR} "
            f"{urls_arg}"
        )


# Librewolf Workload Doesn't Work As Expected
# class Librewolf(BrowserWorkload):
#     PROFILE_DIR = "/tmp/lw-profile"
#     USER_JS = """// Disable session restore and browser prompts
# user_pref("browser.startup.page", 0);
# user_pref("browser.sessionstore.resume_session_once", false);
# user_pref("browser.sessionstore.resume_from_crash", false);
# user_pref("browser.sessionstore.enabled", false);
# user_pref("browser.startup.homepage_override.mstone", "ignore");
# user_pref("browser.startup.homepage_override.buildID", "");
# user_pref("startup.homepage_welcome_url", "");
# user_pref("startup.homepage_welcome_url.additional", "");
# user_pref("browser.shell.checkDefaultBrowser", false);
# user_pref("browser.warnOnQuit", false);
# user_pref("gfx.webrender.all", true);
# user_pref("gfx.webrender.enabled", true);
# user_pref("layers.acceleration.force-enabled", true);
# user_pref("webgl.force-enabled", true);
# user_pref("privacy.resistFingerprinting", false);
# user_pref("privacy.firstparty.isolate", false);
# user_pref("network.cookie.cookieBehavior", 2);
# user_pref("privacy.userContext.enabled", false);
# user_pref("permissions.default.geo", 1);
# user_pref("permissions.default.camera", 1);
# user_pref("permissions.default.microphone", 1);
# """
#     DEPENDENCIES = ["librewolf", "xorg.xvfb"]

#     def prepare_clean_profile(self):
#         if os.path.exists(self.PROFILE_DIR):
#             shutil.rmtree(self.PROFILE_DIR)
#         os.makedirs(self.PROFILE_DIR, exist_ok=True)
#         user_js_path = os.path.join(self.PROFILE_DIR, "user.js")
#         with open(user_js_path, "w") as f:
#             f.write(self.USER_JS)

#     def open_sites(self, display: int = 99) -> str:
#         urls = [
#             "https://www.youtube.com/watch?v=xm3YgoEiEDc&autoplay=1",
#             "https://www.google.com/",
#             "https://open.spotify.com/",
#             "https://www.amazon.com/",
#         ]
#         urls_arg = " ".join(f"'{u}'" for u in urls)
#         return (
#             f"librewolf --no-remote --profile {self.PROFILE_DIR} "
#             f"--display=:{display} --new-window {urls_arg}"
#         )
