import logging
from typing import List, Optional, Tuple
import os
import shutil
import pathlib
import sys
import subprocess

if sys.version_info.major == 3 and sys.version_info.minor < 11:
    import tomli  # type: ignore
else:
    import tomllib as tomli  # type: ignore

import setuptools
from setuptools.command.build_ext import build_ext

from setuptools import build_meta

IS_WINDOWS = sys.platform == "win32"


class PyBindModule(setuptools.Extension):
    """
    Defines a single pybind11 module
    """

    def __init__(
        self,
        module_name: str,
        source_dir: str,
        bin_prefix: Optional[str] = None,
        # TODO change this to be a list of files?
        dep_bin_prefixes: Optional[List[str]] = None,
        cmake_config_options: List[str] = list(),
        cmake_build_options: List[str] = list(),
        inc_dirs: List[Tuple[str, str]] = list()
    ):
        """
        Params:
          module_name - The name of the output wheel
          source_dir - The cmake source directory
          bin_prefix - path prefix to binary files in the cmake build directory
          dep_bin_prefix - list of any additional folders to search for dependent shared libs
          cmake_config_options - Any extra cmd line arguments to be set during cmake config
          cmake_build_options - Any extra cmd line arguments to be set during cmake build
          inc_dirs - List of any additional data dirs (E.G. include dirs) and output paths
        """
        # TODO docstring
        # call super with no sources, since we are controlling the build
        super().__init__(name=module_name, sources=[])
        self.name = module_name
        self.sourcedir = source_dir
        self.extraBinDirs = dep_bin_prefixes
        self.extraConfigOptions = cmake_config_options
        self.extraBuildOptions = cmake_build_options
        self.binPrefix = bin_prefix
        self.incDirs = inc_dirs

    def log(self, msg: str):
        # log with the module name at the start
        logging.info(f'\033[1;33m{self.name}: {msg}\033[0m')


class _Build(build_ext):

    def run(self) -> None:
        for extension in self.extensions:
            if isinstance(extension, PyBindModule):
                self.build(extension)

        # run the normal func for "normal" extensions
        super().run()

    def build(self, extension: PyBindModule):
        extension.log("Preparing the build environment")
        ext_path = pathlib.Path(self.get_ext_fullpath(extension.name))
        build_dir = pathlib.Path(self.build_temp)

        os.makedirs(build_dir, exist_ok=True)
        os.makedirs(ext_path.parent.absolute(), exist_ok=True)

        try:
            # Use env var, if available
            pyRoot = os.environ['PY_ROOT']
        except KeyError:
            # else use the current exec
            pyRoot, _ = os.path.split(sys.executable)

        extension.log(f"Using Python Root: {pyRoot}")
        extension.log(f"Using build directory: {build_dir}")
        env = os.environ.copy()

        env["CMAKE_BUILD_PARALLEL_LEVEL"] = "8"
        env["Python3_ROOT_DIR"] = pyRoot

        args = ["cmake", "-S", extension.sourcedir, "-B", str(build_dir)]
        if not IS_WINDOWS:
            args.append("-DCMAKE_BUILD_TYPE=Release")
        # Add user supplied args
        args.extend(extension.extraConfigOptions)

        extension.log("Configuring cmake project")
        ret = subprocess.call(args, env=env)

        if ret != 0:
            raise RuntimeError(
                f"Error building pybind extension '{extension.name}': Could not configure cmake"
            )

        args = [
            "cmake",
            "--build",
            str(build_dir),  # TODO
            # "--target", extension.name
        ]

        if IS_WINDOWS:
            args.append("--config=Release")

        extension.log("Building cmake project")

        ret = subprocess.call(args, env=env)

        if ret != 0:
            raise RuntimeError(
                f"Error building pybind extension '{extension.name}': Could not build cmake project"
            )

        primary_bin_dir = build_dir
        if extension.binPrefix is not None:
            primary_bin_dir /= extension.binPrefix

        if IS_WINDOWS:
            primary_bin_dir /= "Release"

        extension.log(f"Using bin directory {primary_bin_dir}")

        def isLibFile(filename: str) -> bool:
            fullPath = os.path.join(primary_bin_dir, filename)
            if not os.path.isfile(fullPath):
                return False
            name, ext = os.path.splitext(filename)
            if ext not in [".pyd", ".so"]:
                return False
            return name.startswith(extension.name)

        potentials = [
            primary_bin_dir / pyd for pyd in os.listdir(primary_bin_dir)
            if isLibFile(pyd)
        ]

        if len(potentials) == 0:
            raise RuntimeError(
                f"Error building pybind extension '{extension.name}': Could not find built library"
            )

        pyd_path = potentials[0]

        extension.log(
            f"Moving build python module '{pyd_path}' -> '{ext_path}'"
        )
        # copy lib to the name setuptools wants it to be
        shutil.copy(pyd_path, ext_path)

        # copy any dependencies
        # TODO use additional bin dirs

        # Copy additional dependencies
        # only do this on windows, since auditwheel will take care of it
        # on linux
        if IS_WINDOWS:
            libDirs = [primary_bin_dir]
            # Just a list because it's a small number of items
            fileTypes = [".dll", ".pyd", ".so", ".lib"]
            if extension.extraBinDirs is not None:
                libDirs.extend(
                    (build_dir / pathlib.Path(x) / "Release")
                    for x in extension.extraBinDirs
                )
            libs = {pyd_path.name, f'{pyd_path.stem}.lib'}
            for libdir in libDirs:
                for file in os.listdir(libdir):
                    _, ext = os.path.splitext(file)
                    if ext in fileTypes:
                        # Copy the file
                        src = libdir / file
                        dest = ext_path.parent / file
                        if file in libs:
                            # skip the primary lib we already copied
                            continue
                        libs.add(file)
                        extension.log(f'Copying lib: {src} -> {dest}')
                        shutil.move(src, dest)

        extension.log("Generating stubs")

        try:
            oldPath = env['PYTHONPATH']
        except KeyError:
            oldPath = ""

        if IS_WINDOWS:
            newPath = f"{primary_bin_dir};" + oldPath
        else:
            newPath = f"{primary_bin_dir}:" + oldPath

        env["PYTHONPATH"] = newPath

        ret = subprocess.call(
            [
                sys.executable,
                "-m",
                "pybind11_stubgen",
                extension.name,
                "-o",
                "."
            ],
            cwd=ext_path.parent
        )

        if ret != 0:
            raise RuntimeError("Could not generate stubs")

        datadir = ext_path.parent / f'{self.distribution.get_fullname()}.inc'
        extension.log(f"Copying data files to {datadir}")

        for folder, outpath in extension.incDirs:
            fullout = datadir / outpath
            if os.path.exists(fullout):
                shutil.rmtree(fullout)
            shutil.copytree(folder, fullout)


def setup(modules: List[PyBindModule], *args, **kwargs):
    setuptools.setup(
        ext_modules=modules,
        *args,
        cmdclass={
            'build_ext': _Build
        },
        **kwargs,
    )


__all__ = [
    'get_requires_for_build_sdist',
    'get_requires_for_build_wheel',
    'prepare_metadata_for_build_wheel',
    'build_wheel',
    'build_sdist'
]


# subclass the normal setuptools backend
class _BuildBackend(build_meta._BuildMetaBackend):
    SOURCE_DIR = "source_dir"
    BIN_PREFIX = "bin_prefix"
    DEP_BIN_PREFIXES = "dep_bin_prefixes"
    INC_DIRS = "inc_dirs"
    CMAKE_CONFIG = "cmake_config_options"
    CMAKE_BUILD = "cmake_build_options"

    VALID_KEYS = {
        SOURCE_DIR,
        BIN_PREFIX,
        DEP_BIN_PREFIXES,
        INC_DIRS,
        CMAKE_CONFIG,
        CMAKE_BUILD
    }

    def run_setup(self, setup_script: str = "setup.py") -> None:
        # ignore the passed arg, and just directly call
        # setup here after loading the pyproject args
        with open("pyproject.toml", mode='rb') as f:
            project = tomli.load(f)

        try:
            moduleConfigs = project["tool"]["setuptools-pybind11"]["modules"]
        except KeyError:
            logging.warn("No pybind11 modules defined, exitting")
            return

        modules = []

        for moduleName, configs in moduleConfigs.items():
            badKey = False
            for key in configs.keys():
                if key not in self.VALID_KEYS:
                    logging.error(
                        f"Unknown config key tools.setuptools-pybind11.modules.{moduleName}.{key}"
                    )
                    badKey = True

            if badKey:
                raise RuntimeError("Invalid config keys")

            try:
                sourceDir = configs["source_dir"]
            except KeyError:
                sourceDir = "."

            # make source dir relative to pyproject.toml
            if not os.path.isabs(sourceDir):
                sourceDir = os.path.abspath(sourceDir)

            try:
                binPrefix = configs["bin_prefix"]
            except KeyError:
                binPrefix = ""

            try:
                depBinPrefixes = configs['dep_bin_prefixes']
            except KeyError:
                depBinPrefixes = []

            try:
                incDirs = configs["inc_dirs"]
            except KeyError:
                incDirs = []

            try:
                cmakeConfigOptions = configs["cmake_config_options"]
            except KeyError:
                cmakeConfigOptions = []

            try:
                cmakeBuildOptions = configs["cmake_build_options"]
            except KeyError:
                cmakeBuildOptions = []

            modules.append(
                PyBindModule(
                    module_name=moduleName,
                    source_dir=sourceDir,
                    bin_prefix=binPrefix,
                    dep_bin_prefixes=depBinPrefixes,
                    inc_dirs=incDirs,
                    cmake_config_options=cmakeConfigOptions,
                    cmake_build_options=cmakeBuildOptions
                )
            )

        setup(modules=modules)


build_meta._BACKEND = _BuildBackend()
get_requires_for_build_wheel = build_meta._BACKEND.get_requires_for_build_wheel
get_requires_for_build_sdist = build_meta._BACKEND.get_requires_for_build_sdist
prepare_metadata_for_build_wheel = build_meta._BACKEND.prepare_metadata_for_build_wheel
build_wheel = build_meta._BACKEND.build_wheel
build_sdist = build_meta._BACKEND.build_sdist
