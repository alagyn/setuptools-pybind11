# setuptools-pybind11
Setuptools extension for building pybind11 libraries with CMake

## Usage
Add setuptools-pybind11 to your `pyproject.toml`
```toml
[build-system]
requires = ["setuptools", "wheel", "setuptools-pybind11[cmake]"]
```

Use `setuptools-pybind11` if you don't want to automatically install cmake

Create a `setup.py` file
```py
from setuptools_pybind11 import PyBindModule, setup

SRC_DIR = os.path.dirname(__file__)

setup([
    PyBindModule(
        module_name="example",
        source_dir=SRC_DIR,
        dep_bin_prefixes=["example-dep"]
    )]
)
```

Build your module
`python -m build --wheel`