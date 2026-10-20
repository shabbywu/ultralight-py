cmake_minimum_required(VERSION 3.22)
project(ultralight_py VERSION 0.6.0 LANGUAGES CXX)

set(CMAKE_CXX_STANDARD 20)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
set(CMAKE_CXX_EXTENSIONS OFF)
set(CMAKE_POSITION_INDEPENDENT_CODE ON)
set(BUILD_TESTING OFF CACHE BOOL "Build dependency tests")
set(ULTRALIGHT_SDK_VERSION "2.0.0-beta.2" CACHE STRING "Ultralight SDK version")

set(PYBIND11_FINDPYTHON ON)
find_package(Python COMPONENTS Interpreter Development.Module REQUIRED)
add_subdirectory(externals/pybind11)
set(ULBIND17_ENABLE_APPCORE ON CACHE BOOL "Enable AppCore for Python" FORCE)
add_subdirectory(externals/ulbind17 EXCLUDE_FROM_ALL)

pybind11_add_module(_native MODULE bindings/module.cpp)
target_link_libraries(_native PRIVATE ulbind17::ulbind17 ulbind17::appcore)
ulbind17_copy_runtime_files(_native INCLUDE_APPCORE ON)
install(TARGETS _native LIBRARY DESTINATION ultralight_py RUNTIME DESTINATION ultralight_py)
foreach(library IN ITEMS UltralightCore WebCore Ultralight AppCore)
  install(FILES "$<TARGET_FILE:Ultralight::${library}>" DESTINATION ultralight_py)
endforeach()

if(APPLE)
  # SDK dylibs refer to their peers via @rpath without a usable package-local
  # LC_RPATH. Make the installed copies self-contained, including for delocate's
  # per-library dependency analysis, then restore their ad-hoc signatures.
  install(CODE [[
    set(_package "$ENV{DESTDIR}${CMAKE_INSTALL_PREFIX}/ultralight_py")
    foreach(_library IN ITEMS UltralightCore WebCore Ultralight AppCore)
      set(_file "${_package}/lib${_library}.dylib")
      foreach(_dependency IN ITEMS UltralightCore WebCore Ultralight AppCore)
        execute_process(
          COMMAND /usr/bin/install_name_tool
            -change "@rpath/lib${_dependency}.dylib"
            "@loader_path/lib${_dependency}.dylib" "${_file}"
          COMMAND_ERROR_IS_FATAL ANY)
      endforeach()
      execute_process(COMMAND /usr/bin/codesign --force --sign - "${_file}"
        COMMAND_ERROR_IS_FATAL ANY)
    endforeach()
  ]])
endif()
