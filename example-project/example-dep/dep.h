#pragma once
#include <string>

// Shared libary export stuff is different per compiler
#if defined(_MSC_VER)
    // Microsoft
    #define EXPORT __declspec(dllexport)
    #define IMPORT __declspec(dllimport)
#else
    // GCC
    #define EXPORT __attribute__((visibility("default")))
    #define IMPORT
#endif

// Only export if we building the library, otherwise import the functions
#ifdef COMPILING
    #define MY_LIB_EXPORT EXPORT
#else
    #define MY_LIB_EXPORT IMPORT
#endif

MY_LIB_EXPORT void cpp_print(std::string message);