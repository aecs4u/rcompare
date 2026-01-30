# CMakeLists.txt for RCompare FFI
# This allows C/C++ projects to easily integrate the RCompare library

cmake_minimum_required(VERSION 3.15)
project(rcompare_ffi C CXX)

# Option to build examples
option(BUILD_EXAMPLES "Build example programs" ON)

# Find the Rust library
# Assumes the library is built with `cargo build --release`
set(RCOMPARE_LIB_DIR "${CMAKE_CURRENT_SOURCE_DIR}/../target/release")

# Create imported target for the static library
add_library(rcompare STATIC IMPORTED)
set_target_properties(rcompare PROPERTIES
    IMPORTED_LOCATION "${RCOMPARE_LIB_DIR}/librcompare_ffi.a"
    INTERFACE_INCLUDE_DIRECTORIES "${CMAKE_CURRENT_SOURCE_DIR}/include"
)

# Link requirements (Rust std library dependencies)
if(UNIX AND NOT APPLE)
    # Linux
    target_link_libraries(rcompare INTERFACE
        pthread
        dl
        m
    )
elseif(APPLE)
    # macOS
    target_link_libraries(rcompare INTERFACE
        "-framework Security"
        "-framework CoreFoundation"
        pthread
        dl
        m
    )
elseif(WIN32)
    # Windows
    target_link_libraries(rcompare INTERFACE
        ws2_32
        userenv
        bcrypt
        ntdll
    )
endif()

# Build examples if requested
if(BUILD_EXAMPLES)
    add_subdirectory(examples)
endif()

# Install rules
install(FILES include/rcompare.h
    DESTINATION include
)

install(FILES "${RCOMPARE_LIB_DIR}/librcompare_ffi.a"
    DESTINATION lib
    OPTIONAL
)

# Print configuration
message(STATUS "RCompare FFI Configuration:")
message(STATUS "  Library directory: ${RCOMPARE_LIB_DIR}")
message(STATUS "  Include directory: ${CMAKE_CURRENT_SOURCE_DIR}/include")
message(STATUS "  Build examples: ${BUILD_EXAMPLES}")
