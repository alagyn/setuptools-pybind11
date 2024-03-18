import logging
from typing import List, Optional, Tuple
import os
import shutil
import pathlib
import sys
import subprocess

import setuptools
from setuptools.command.build_ext import build_ext

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
        cmake_build_options: List[str] = list(),
        data_dirs: List[Tuple[str, str]] = list()
    ):
        """
        Params:
          module_name - The name of the output wheel
          source_dir - The cmake source directory
          bin_prefix - path prefix to binary files in the cmake build directory
          dep_bin_prefix - list of any additional folders to search for dependent shared libs
          cmake_config_options - Any extra cmd line arguments to be set during cmake config
          cmake_build_options - Any extra cmd line arguments to be set during cmake build
          data_dirs - List of any additional data dirs (E.G. include dirs) and output paths
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
        self.data_dirs = data_dirs

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

        args = ["cmake", "-S", extension.sourcedir, "-B", build_dir]
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
            build_dir,  # TODO
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
            fileTypes = [".dll", ".pyd", ".so"]
            if extension.extraBinDirs is not None:
                libDirs.extend(
                    (build_dir / pathlib.Path(x))
                    for x in extension.extraBinDirs
                )
            libs = {pyd_path}
            for libdir in libDirs:
                for file in os.listdir(libdir):
                    _, ext = os.path.splitext(file)
                    if ext in fileTypes:
                        # Copy the file
                        src = libdir / file
                        dest = build_dir / file
                        if dest in libs:
                            # skip the primary lib we already copied
                            continue
                        libs.add(dest)
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

        extension.log("Copying data files")

        for folder, outpath in extension.data_dirs:
            shutil.copytree(
                folder, ext_path.parent / f'{extension.name}' / outpath
            )


def setup(modules: List[PyBindModule], *args, **kwargs):
    setuptools.setup(
        ext_modules=modules,
        *args,
        cmdclass={
            'build_ext': _Build
        },
        **kwargs,
    )
