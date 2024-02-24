cmake_minimum_required(VERSION 3.25.2)

project(example)

set(CMAKE_DEBUG_POSTFIX, "-d")

set(Python3_FIND_REGISTRY NEVER)

if(${MSVC})
    set(PY_COMPONENTS Interpreter Development)
else()
    set(PY_COMPONENTS Interpreter Development.Module)
endif()

find_package(Python3
    COMPONENTS
    REQUIRED
    ${PY_COMPONENTS}
)

add_subdirectory(pybind11)
add_subdirectory(example-dep)

Python3_add_library(
    example # Library Name
    # src files
    src/myModule.cpp
)

set_target_properties(example PROPERTIES
    INTERPROCEDURAL_OPTIMIZATION ON
    VISIBILITY_INLINES_HIDDEN ON
    CXX_STANDARD 17
)

target_link_libraries(example
    PRIVATE
    pybind11::headers
    myLibDep
)

target_compile_definitions(example
    PRIVATE
    PYBIND11_DETAILED_ERROR_MESSAGES
)

if(${MSVC})
else()
    target_compile_options(${PROJECT_NAME}
        PRIVATE
        -Wno-format-security
        -fvisibility=hidden
    )
endif()
