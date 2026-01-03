cmake_minimum_required(VERSION 3.20)
project(BaluDeskBackend VERSION 1.0.0 LANGUAGES CXX)

# C++17 Standard
set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
set(CMAKE_CXX_EXTENSIONS OFF)

# Export compile commands for IDEs
set(CMAKE_EXPORT_COMPILE_COMMANDS ON)

# Build type
if(NOT CMAKE_BUILD_TYPE)
    set(CMAKE_BUILD_TYPE Release)
endif()

# Compiler flags
if(MSVC)
    add_compile_options(/W4 /WX)
else()
    add_compile_options(-Wall -Wextra -Wpedantic -Werror)
endif()

# Dependencies
# Try vcpkg first, fall back to system packages
find_package(CURL CONFIG QUIET)
if(NOT CURL_FOUND)
    find_package(CURL REQUIRED)
endif()

find_package(unofficial-sqlite3 CONFIG QUIET)
if(NOT unofficial-sqlite3_FOUND)
    find_package(SQLite3 REQUIRED)
endif()

find_package(Threads REQUIRED)

# Include FetchContent for header-only libraries
include(FetchContent)

# nlohmann/json
FetchContent_Declare(
    json
    GIT_REPOSITORY https://github.com/nlohmann/json.git
    GIT_TAG v3.11.3
)
FetchContent_MakeAvailable(json)

# spdlog
FetchContent_Declare(
    spdlog
    GIT_REPOSITORY https://github.com/gabime/spdlog.git
    GIT_TAG v1.12.0
)
FetchContent_MakeAvailable(spdlog)

# Google Test (for unit tests)
FetchContent_Declare(
    googletest
    GIT_REPOSITORY https://github.com/google/googletest.git
    GIT_TAG v1.14.0
)
FetchContent_MakeAvailable(googletest)

# Include directories
include_directories(
    ${CMAKE_CURRENT_SOURCE_DIR}/src
    ${CURL_INCLUDE_DIRS}
    ${SQLite3_INCLUDE_DIRS}
)

# Source files
set(SOURCES
    src/main.cpp
    src/stubs.cpp
    src/sync/sync_engine.cpp
    src/sync/file_watcher.cpp
    src/sync/change_detector.cpp
    src/sync/conflict_resolver.cpp
    src/api/http_client.cpp
    src/db/database.cpp
    src/ipc/ipc_server_fixed.cpp
    src/utils/logger.cpp
    src/utils/config.cpp
    src/baluhost_client.cpp
)

# Platform-specific file watcher is now unified in file_watcher.cpp

# Main executable
add_executable(baludesk-backend ${SOURCES})

# Link libraries
target_link_libraries(baludesk-backend
    PRIVATE
        CURL::libcurl
        unofficial::sqlite3::sqlite3
        nlohmann_json::nlohmann_json
        spdlog::spdlog
        Threads::Threads
)

# Platform-specific libraries
if(APPLE)
    target_link_libraries(baludesk-backend PRIVATE "-framework CoreServices")
endif()

# Installation
install(TARGETS baludesk-backend
    RUNTIME DESTINATION bin
)

# TODO: Enable testing later
# enable_testing()
# include(GoogleTest)
# gtest_discover_tests(baludesk-tests)

# Print configuration
message(STATUS "Build type: ${CMAKE_BUILD_TYPE}")
message(STATUS "C++ compiler: ${CMAKE_CXX_COMPILER}")
message(STATUS "C++ standard: ${CMAKE_CXX_STANDARD}")
