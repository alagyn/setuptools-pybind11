# setuptools-pybind11
Setuptools extension for building pybind11 libraries with CMake

## Usage
Add setuptools-pybind11 to your `pyproject.toml`
```toml
[build-system]
requires = [
    "setuptools", 
    "wheel", 
    # Use setuptools-pybind11 if you don't want to automatically install cmake
    "setuptools-pybind11[cmake]"
    ]
# set this package as the backend
build-backend="setuptools_pybind11"

[project]
name = "example"
version = "0.1.0"
... # other project stuff

# you can define multiple modules
[tool.setuptools-pybind11.modules.example]
# defaults to this
source_dir = "."
# prefix in build directory to main binary
bin_prefix = ""
# binary dir prefixes for dependencies
dep_bin_prefixes = ["example-dep"]
# include/data directories and their name (placed under [package-name]-[version].inc/path)
inc_dirs = [["example-dep", "example-path"]]
# any additional cmake configs you need
cmake_config_options = ["-DMYCMAKE_OPTION=ON"]
cmake_build_options = ["--MyBuildOption"]
```

Build your module
`python -m build`