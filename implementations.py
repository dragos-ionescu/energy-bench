from dataclasses import dataclass
from typing import ClassVar
import os

from scenario import Implementation
from utils import *


def get_implementation_class(implementation: str) -> type[Implementation]:
    impl = implementation.lower().strip()
    for cls in all_subclasses(Implementation):
        if hasattr(cls, "aliases") and impl in cls.aliases:
            return cls
    raise ProgramError(f"{implementation} not a known implementation")


@dataclass
class C(Implementation):
    aliases: ClassVar[list[str]] = ["c"]
    target: str = "main"
    source: str = "main.c"

    @property
    def build_command(self) -> list[str]:
        return [
            "$(which gcc)",
            self.source_path,
            "-o",
            self.target_path,
            *self.scenario.options,
            "-w",
            "-lenergy_signal",
        ]

    @property
    def measure_command(self) -> list[str]:
        return [self.target_path]

    @property
    def clean_command(self) -> list[str]:
        return ["rm", "-f", self.target_path]


@dataclass
class Cpp(C):
    aliases: ClassVar[list[str]] = ["c++", "cpp", "cplus", "cplusplus"]
    source: str = "main.cpp"

    @property
    def build_command(self) -> list[str]:
        return [
            "$(which g++)",
            self.source_path,
            "-o",
            self.target_path,
            *self.scenario.options,
            "-w",
            "-lenergy_signal",
        ]


@dataclass
class Cs(Implementation):
    aliases: ClassVar[list[str]] = ["c#", "cs", "csharp"]
    target: str = os.path.join("bin", "Release", "net*", "program")
    source: str = "Program.cs"

    @property
    def build_command(self) -> list[str]:
        return [
            "$(which dotnet)",
            "build",
            self.scenario_path,
            "--nologo",
            "-v q",
            "-p:WarningLevel=0",
            "-p:UseSharedCompilation=false",
            *self.scenario.options,
        ]

    @property
    def measure_command(self) -> list[str]:
        return ["env DOTNET_ROOT=$(dirname $(readlink -f $(which dotnet)))", self.target_path]

    @property
    def clean_command(self) -> list[str]:
        bin_path = os.path.join(self.scenario_path, "bin")
        obj_path = os.path.join(self.scenario_path, "obj")
        csproj_path = os.path.join(self.scenario_path, "program.csproj")
        return ["rm", "-rf", bin_path, obj_path, csproj_path]

    def build(self) -> None:
        csproj_path = os.path.join(self.scenario_path, "program.csproj")
        with open(csproj_path, "w") as file:
            pkg_refs = "".join(
                [
                    f'<PackageReference Include="{pkg.get("name")}" Version="{pkg.get("version")}" />'
                    for pkg in self.scenario.packages
                ]
            )
            file.write(
                f'<Project Sdk="Microsoft.NET.Sdk"><PropertyGroup><TargetFramework>{self.scenario.target_framework}</TargetFramework></PropertyGroup><ItemGroup>{pkg_refs}</ItemGroup></Project>'
            )
        super().build()


@dataclass
class Java(Implementation):
    aliases: ClassVar[list[str]] = ["java"]
    target: str = "Program"
    source: str = "Program.java"

    @property
    def _cp_flag(self) -> str:
        return f"-cp {self.base_dir}:{self.scenario_path}:{':'.join(self.scenario.class_paths)}"

    @property
    def build_command(self) -> list[str]:
        return [
            "$(which javac)",
            "-nowarn",
            f"-d {self.scenario_path}",
            self._cp_flag,
            self.source_path,
            *self.scenario.options,
        ]

    @property
    def measure_command(self) -> list[str]:
        return ["$(which java)", "--enable-native-access=ALL-UNNAMED", self._cp_flag, self.target]

    @property
    def clean_command(self) -> list[str]:
        classes_path = f"{self.scenario_path}/*.class"
        return ["rm", "-f", classes_path]


@dataclass
class GraalVm(Java):
    aliases: ClassVar[list[str]] = ["graalvm"]


@dataclass
class OpenJdk(Java):
    aliases: ClassVar[list[str]] = ["openjdk"]


@dataclass
class Semeru(Java):
    aliases: ClassVar[list[str]] = ["semeru"]


@dataclass
class JavaScript(Implementation):
    aliases: ClassVar[list[str]] = ["javascript", "js"]


@dataclass
class Python(Implementation):
    aliases: ClassVar[list[str]] = ["python", "py"]
    target: str = "main.py"
    source: str = "main.py"

    @property
    def measure_command(self) -> list[str]:
        return ["$(which python)", *self.scenario.roptions, "--", self.target_path]


@dataclass
class Ruby(Implementation):
    aliases: ClassVar[list[str]] = ["ruby", "rb"]
    target: str = "main.rb"
    source: str = "main.rb"

    @property
    def measure_command(self) -> list[str]:
        return ["$(which ruby)", *self.scenario.roptions, "--", self.target_path]


@dataclass
class Rust(Implementation):
    aliases: ClassVar[list[str]] = ["rust", "rs"]
    target: str = os.path.join("target", "release", "program")
    source: str = "main.rs"

    @property
    def build_command(self) -> list[str]:
        toml_path = os.path.join(self.scenario_path, "Cargo.toml")
        return ["$(which cargo)", "build", "--manifest-path", toml_path, *self.scenario.options]

    @property
    def measure_command(self) -> list[str]:
        return [self.target_path]

    @property
    def clean_command(self) -> list[str]:
        toml_path = os.path.join(self.scenario_path, "Cargo.toml")
        return ["$(which cargo)", "clean", "--manifest-path", toml_path]

    def build(self) -> None:
        toml_path = os.path.join(self.scenario_path, "Cargo.toml")
        with open(toml_path, "w") as file:
            file.write(
                (
                    "[package]\n"
                    "name = 'program'\n"
                    "version = '0.1.0'\n"
                    "edition = '2024'\n"
                    "[[bin]]\n"
                    "name = 'program'\n"
                    "path = 'main.rs'\n"
                    "[dependencies]\n"
                )
            )
            for pkg in self.scenario.packages:
                name = pkg.get("name")
                version = pkg.get("version")
                file.write(f'{name} = "{version}"\n')
        super().build()
