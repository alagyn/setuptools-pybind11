#include <pybind11/pybind11.h>

#include <dep.h>

namespace py = pybind11;
using namespace pybind11::literals;

bool myFunction(int a, int b)
{
    cpp_print("This is my message");
    return a < b;
}

// module name should be the same as your library name defined in CMakeLists.txt
PYBIND11_MODULE(example, m)
{
    m.def("myFunction", myFunction, "a"_a, "b"_a);
}