from pybind11.setup_helpers import Pybind11Extension, build_ext
from setuptools import setup

setup(
    ext_modules=[Pybind11Extension("geofolio._core", ["cpp/core.cpp"], cxx_std=17)],
    cmdclass={"build_ext": build_ext},
)
