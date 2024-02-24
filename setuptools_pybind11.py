import logging
from typing import List, Optional
import os
import shutil
import pathlib
import sys
import subprocess

import setuptools
from setuptools.command.build_ext import build_ext
from setuptools.command.install_lib import install_lib

SOURCE_DIR, _ = os.path.split(__file__)
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
        cmake_build_options: List[str] = list()
    ):
        """
        Params:
          module_name - The name of the output wheel
          source_dir - The cmake source directory
          bin_prefix - path prefix to binary files in the cmake build directory
          dep_bin_prefix - list of any additional folders to search for dependent shared libs
          cmake_config_options - Any extra cmd line arguments to be set during cmake config
          cmake_build_options - Any extra cmd line arguments to be set during cmake build
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

    def log(self, msg: str):
        # log with the module name at the start
        logging.info(f'{self.name}: {msg}')


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

        extension.log("Configuring cmake project")

        try:
            # Use env var, if available
            pyRoot = os.environ['PY_ROOT']
        except KeyError:
            # else use the current exec
            pyRoot, _ = os.path.split(sys.executable)

        extension.log(f"Using Python Root: {pyRoot}")

        env = os.environ.copy()

        env["CMAKE_BUILD_PARALLEL_LEVEL"] = "8"
        env["Python3_ROOT_DIR"] = pyRoot

        args = ["cmake", "-S", extension.sourcedir, "-B", self.build_temp]
        if not IS_WINDOWS:
            args.append("-DCMAKE_BUILD_TYPE=Release")
        # Add user supplied args
        args.extend(extension.extraConfigOptions)

        ret = subprocess.call(args, env=env)

        if ret != 0:
            raise RuntimeError(
                f"Error building pybind extension '{extension.name}': Could not configure cmake"
            )

        args = [
            "cmake",
            "--build",
            self.build_temp,  # TODO
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

        bin_dir = build_dir
        if extension.binPrefix is not None:
            bin_dir /= extension.binPrefix

        if IS_WINDOWS:
            bin_dir /= "Release"

        bin_dir = bin_dir.resolve()

        extension.log(f"Using bin directory {bin_dir}")

        def isLibFile(filename: str) -> bool:
            fullPath = os.path.join(bin_dir, filename)
            if not os.path.isfile(fullPath):
                return False
            name, ext = os.path.splitext(filename)
            if ext not in [".pyd", ".so"]:
                return False
            return name.startswith(extension.name)

        potentials = [
            bin_dir / pyd for pyd in os.listdir(bin_dir) if isLibFile(pyd)
        ]

        if len(potentials) == 0:
            raise RuntimeError(
                f"Error building pybind extension '{extension.name}': Could not find built library"
            )

        pyd_path = potentials[0]

        # store this in the distribution for use later
        self.distribution.bin_dir = bin_dir  # type: ignore
        self.distribution.lib_name = pyd_path  # type: ignore
        self.distribution.extra_bin = extension.extraBinDirs  # type: ignore

        extension.log(
            f"Moving build python module '{pyd_path}' -> '{ext_path}'"
        )
        # copy lib to the name setuptools wants it to be
        shutil.copy(pyd_path, ext_path)

        # copy any dependencies
        # TODO use additional bin dirs

        # TODO stubs


class _InstallLibs(install_lib):
    """
    Copies any additional dependency libs
    """

    def run(self) -> None:

        bin_dir: pathlib.Path = self.distribution.bin_dir  # type: ignore
        lib_name: pathlib.Path = self.distribution.lib_name  # type: ignore
        extra_bin: Optional[List[str]
                            ] = self.distribution.extra_bin  # type: ignore

        libDirs = [bin_dir]
        # Copy additional dependencies
        # no need to do this on linux, since you should be using auditwheel anyway
        if IS_WINDOWS:
            # Just a list because it's a small number of items
            fileTypes = [".dll", ".pyd"]
            if extra_bin is not None:
                libDirs.extend((bin_dir / pathlib.Path(x)) for x in extra_bin)
            libs = []
            for libdir in libDirs:
                for file in os.listdir(libdir):
                    if file == lib_name.name:
                        # skip the primary lib we already copied
                        continue
                    _, ext = os.path.splitext(file)
                    if ext in fileTypes:
                        # Copy the file
                        src = libdir / file
                        dest = os.path.join(self.build_dir, file)
                        libs.append(file)
                        self.distribution.announce(
                            f'Copying lib: {src} -> {dest}'
                        )
                        shutil.copy(src, dest)

        # We already build the libs in _Build
        self.skip_build = True
        # Call the normal install_lib
        super().run()


def setup(modules: List[PyBindModule], *args, **kwargs):
    setuptools.setup(
        ext_modules=modules,
        *args,
        cmdclass={
            'build_ext': _Build,
            'install_lib': _InstallLibs,
        },
        **kwargs
    )
