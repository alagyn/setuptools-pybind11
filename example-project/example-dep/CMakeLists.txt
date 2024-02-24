project(myLibDep)

add_library(myLibDep SHARED dep.cpp)
target_include_directories(myLibDep PUBLIC ${CMAKE_CURRENT_SOURCE_DIR})
# Add a flag for when we are compiling this lib to setup the exports
target_compile_definitions(myLibDep PRIVATE COMPILING)