# CMakeLists.txt for RCompare FFI examples

# Simple parse example
add_executable(simple_parse simple_parse.c)
target_link_libraries(simple_parse PRIVATE rcompare)

# Patch application example
add_executable(patch_apply patch_apply.c)
target_link_libraries(patch_apply PRIVATE rcompare)

# Set C standard
set_property(TARGET simple_parse patch_apply PROPERTY C_STANDARD 99)

# Installation
install(TARGETS simple_parse patch_apply
    RUNTIME DESTINATION bin
    OPTIONAL
)

# Print configuration
message(STATUS "RCompare FFI Examples:")
message(STATUS "  - simple_parse: Basic parsing and inspection")
message(STATUS "  - patch_apply: Advanced blending and application")
