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
find_package(CURL REQUIRED)
find_package(SQLite3 REQUIRED)
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
    src/sync/sync_engine.cpp
    src/sync/file_watcher.cpp
    src/sync/conflict_resolver.cpp
    src/sync/change_detector.cpp
    src/api/http_client.cpp
    src/api/auth_manager.cpp
    src/db/database.cpp
    src/db/migrations.cpp
    src/fs/file_utils.cpp
    src/ipc/ipc_server.cpp
    src/utils/logger.cpp
    src/utils/config.cpp
    src/utils/crypto.cpp
)

# Platform-specific file watcher
if(WIN32)
    list(APPEND SOURCES src/fs/file_watcher_win.cpp)
elseif(APPLE)
    list(APPEND SOURCES src/fs/file_watcher_mac.cpp)
else()
    list(APPEND SOURCES src/fs/file_watcher_linux.cpp)
endif()

# Main executable
add_executable(baludesk-backend ${SOURCES})

# Link libraries
target_link_libraries(baludesk-backend
    PRIVATE
        CURL::libcurl
        SQLite::SQLite3
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

# Enable testing
enable_testing()

# Test executable
add_executable(baludesk-tests
    tests/sync_engine_test.cpp
    tests/http_client_test.cpp
    tests/conflict_resolver_test.cpp
    tests/database_test.cpp
    # Add source files needed for tests (exclude main.cpp)
    src/sync/sync_engine.cpp
    src/sync/file_watcher.cpp
    src/sync/conflict_resolver.cpp
    src/sync/change_detector.cpp
    src/api/http_client.cpp
    src/api/auth_manager.cpp
    src/db/database.cpp
    src/db/migrations.cpp
    src/fs/file_utils.cpp
    src/utils/logger.cpp
    src/utils/config.cpp
    src/utils/crypto.cpp
)

target_link_libraries(baludesk-tests
    PRIVATE
        CURL::libcurl
        SQLite::SQLite3
        nlohmann_json::nlohmann_json
        spdlog::spdlog
        Threads::Threads
        GTest::gtest
        GTest::gtest_main
)

# Discover tests
include(GoogleTest)
gtest_discover_tests(baludesk-tests)

# Print configuration
message(STATUS "Build type: ${CMAKE_BUILD_TYPE}")
message(STATUS "C++ compiler: ${CMAKE_CXX_COMPILER}")
message(STATUS "C++ standard: ${CMAKE_CXX_STANDARD}")
