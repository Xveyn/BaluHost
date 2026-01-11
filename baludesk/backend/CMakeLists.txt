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
    add_compile_options(/W4 /WX /D_CRT_SECURE_NO_WARNINGS)
else()
    add_compile_options(-Wall -Wextra -Wpedantic -Werror)
endif()

# Dependencies
# Try vcpkg first, fall back to system packages
find_package(CURL CONFIG QUIET)
if(NOT CURL_FOUND)
    find_package(CURL QUIET)
endif()

find_package(unofficial-sqlite3 CONFIG QUIET)
if(NOT unofficial-sqlite3_FOUND)
    find_package(SQLite3 QUIET)
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

# spdlog (use vcpkg instead of FetchContent to avoid locking issues)
find_package(spdlog CONFIG REQUIRED)

# Google Test (for unit tests)
FetchContent_Declare(
    googletest
    GIT_REPOSITORY https://github.com/google/googletest.git
    GIT_TAG v1.14.0
)
set(gtest_force_shared_crt ON CACHE BOOL "" FORCE)
FetchContent_MakeAvailable(googletest)

# Source files
set(SOURCES
    src/main.cpp
    src/stubs.cpp
    src/sync/sync_engine.cpp
    src/sync/file_watcher_v2.cpp
    src/sync/change_detector.cpp
    src/utils/sha256.cpp
    src/sync/conflict_resolver.cpp
    src/api/http_client.cpp
    src/db/database.cpp
    src/ipc/ipc_server_fixed.cpp
    src/services/ssh_service.cpp
    src/services/vpn_service.cpp
    src/utils/logger.cpp
    src/utils/config.cpp
    src/utils/system_info.cpp
    src/utils/raid_info.cpp
    src/utils/settings_manager.cpp
    src/baluhost_client.cpp
)

# Platform-specific file watcher implementations
if(WIN32)
    list(APPEND SOURCES src/sync/file_watcher_windows.cpp)
    message(STATUS "Windows FileWatcher enabled")
elseif(APPLE)
    list(APPEND SOURCES src/sync/file_watcher_macos.cpp)
    message(STATUS "macOS FileWatcher enabled (FSEvents)")
elseif(UNIX AND NOT APPLE)
    list(APPEND SOURCES src/sync/file_watcher_linux.cpp)
    message(STATUS "Linux FileWatcher enabled (inotify)")
else()
    message(WARNING "No platform-specific FileWatcher available")
endif()

# Main executable
add_executable(baludesk-backend ${SOURCES})

# Include directories (modern target-based approach)
target_include_directories(baludesk-backend
    PRIVATE
        ${CMAKE_CURRENT_SOURCE_DIR}/src
)

# Link libraries with proper interface propagation
set(LINK_LIBS nlohmann_json::nlohmann_json spdlog::spdlog Threads::Threads)

if(CURL_FOUND)
    list(APPEND LINK_LIBS CURL::libcurl)
else()
    message(WARNING "CURL not found - some features may be unavailable")
endif()

if(unofficial-sqlite3_FOUND)
    list(APPEND LINK_LIBS unofficial::sqlite3::sqlite3)
elseif(SQLite3_FOUND)
    list(APPEND LINK_LIBS SQLite3::SQLite3)
else()
    message(WARNING "SQLite3 not found - database features unavailable")
endif()

target_link_libraries(baludesk-backend
    PRIVATE
        ${LINK_LIBS}
)

# Platform-specific libraries
if(APPLE)
    target_link_libraries(baludesk-backend PRIVATE "-framework CoreServices")
endif()

# Installation
install(TARGETS baludesk-backend
    RUNTIME DESTINATION bin
)

# Configure compile features for better IDE support
target_compile_features(baludesk-backend PRIVATE cxx_std_17)

# Add compile definitions for debug/release
target_compile_definitions(baludesk-backend
    PRIVATE
        $<$<CONFIG:Debug>:DEBUG_BUILD>
        $<$<CONFIG:Release>:NDEBUG>
)

# ============================================================================
# Unit Tests
# ============================================================================

option(BUILD_TESTS "Build unit tests" ON)

if(BUILD_TESTS)
    enable_testing()
    include(GoogleTest)
    
    # Test source files
    set(TEST_SOURCES
        tests/file_watcher_test.cpp
        tests/change_detector_hash_test.cpp
        tests/sync_engine_retry_test.cpp
        tests/sync_engine_performance_test.cpp
        # Note: sync_engine_integration_test.cpp requires full build context with
        # mocked HttpClient and Database - see comments in sync_engine_integration_test.cpp
        # tests/sync_engine_integration_test.cpp
    )
    
    # Common sources needed by tests (exclude main.cpp, DB, HTTP)
    set(TEST_COMMON_SOURCES
        src/utils/logger.cpp
        src/sync/file_watcher_v2.cpp
        src/sync/change_detector.cpp
        src/utils/sha256.cpp
    )
    
    # Platform-specific test sources
    if(WIN32)
        list(APPEND TEST_COMMON_SOURCES src/sync/file_watcher_windows.cpp)
    elseif(APPLE)
        list(APPEND TEST_COMMON_SOURCES src/sync/file_watcher_macos.cpp)
    elseif(UNIX AND NOT APPLE)
        list(APPEND TEST_COMMON_SOURCES src/sync/file_watcher_linux.cpp)
    endif()
    
    # Create test executable
    add_executable(baludesk-tests ${TEST_SOURCES} ${TEST_COMMON_SOURCES})
    
    # Include directories for tests
    target_include_directories(baludesk-tests
        PRIVATE
            ${CMAKE_CURRENT_SOURCE_DIR}/src
    )
    
    # Link test libraries
    set(TEST_LINK_LIBS nlohmann_json::nlohmann_json spdlog::spdlog Threads::Threads GTest::gtest GTest::gtest_main)
    
    if(CURL_FOUND)
        list(APPEND TEST_LINK_LIBS CURL::libcurl)
    endif()
    
    if(official-sqlite3_FOUND)
        list(APPEND TEST_LINK_LIBS unofficial::sqlite3::sqlite3)
    elseif(SQLite3_FOUND)
        list(APPEND TEST_LINK_LIBS SQLite3::SQLite3)
    endif()
    
    target_link_libraries(baludesk-tests
        PRIVATE
            ${TEST_LINK_LIBS}
    )
    
    # Platform-specific libraries for tests
    if(APPLE)
        target_link_libraries(baludesk-tests PRIVATE "-framework CoreServices")
    endif()
    
    # Discover tests
    gtest_discover_tests(baludesk-tests
        WORKING_DIRECTORY ${CMAKE_CURRENT_BINARY_DIR}
        PROPERTIES
            LABELS "unit"
    )
    
    message(STATUS "Unit tests enabled")
else()
    message(STATUS "Unit tests disabled (use -DBUILD_TESTS=ON to enable)")
endif()

# ============================================================================
# Documentation
# ============================================================================

# Print configuration
message(STATUS "Build type: ${CMAKE_BUILD_TYPE}")
message(STATUS "C++ compiler: ${CMAKE_CXX_COMPILER}")
message(STATUS "C++ standard: ${CMAKE_CXX_STANDARD}")
