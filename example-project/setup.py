from setuptools_pybind11 import PyBindModule, setup

import os.path

SRC_DIR = os.path.dirname(__file__)

setup([PyBindModule("example", SRC_DIR)])