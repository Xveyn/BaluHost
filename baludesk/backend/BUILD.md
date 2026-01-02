# BaluDesk Backend - Build Instructions

## Prerequisites

### Windows
```powershell
# Install vcpkg
git clone https://github.com/Microsoft/vcpkg.git
cd vcpkg
.\\bootstrap-vcpkg.bat

# Install dependencies
.\\vcpkg install curl:x64-windows sqlite3:x64-windows

# Install CMake (via chocolatey)
choco install cmake
```

### macOS
```bash
# Install Homebrew
/bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"

# Install dependencies
brew install cmake curl sqlite3
```

### Linux (Ubuntu/Debian)
```bash
# Install build tools
sudo apt update
sudo apt install build-essential cmake git

# Install dependencies
sudo apt install libcurl4-openssl-dev libsqlite3-dev
```

## Building

### 1. Clone Repository
```bash
cd baludesk/backend
```

### 2. Create Build Directory
```bash
mkdir build
cd build
```

### 3. Configure with CMake
```bash
# Windows (with vcpkg)
cmake .. -DCMAKE_TOOLCHAIN_FILE=path/to/vcpkg/scripts/buildsystems/vcpkg.cmake

# macOS/Linux
cmake ..
```

### 4. Build
```bash
# Build release version
cmake --build . --config Release

# Build with verbose output
cmake --build . --config Release --verbose

# Parallel build (faster)
cmake --build . --config Release -j8
```

### 5. Run
```bash
# Run the backend
./baludesk-backend

# Run with verbose logging
./baludesk-backend --verbose

# Run tests
ctest --output-on-failure
```

## Development

### Build in Debug Mode
```bash
mkdir build-debug
cd build-debug
cmake .. -DCMAKE_BUILD_TYPE=Debug
cmake --build .

# Run with debugger
gdb ./baludesk-backend
# or on macOS
lldb ./baludesk-backend
```

### Run Tests
```bash
# Run all tests
ctest

# Run specific test
./baludesk-tests --gtest_filter=SyncEngineTest.*

# Run with verbose output
ctest --verbose
```

### Code Coverage (Linux/macOS)
```bash
cmake .. -DCMAKE_BUILD_TYPE=Debug -DENABLE_COVERAGE=ON
cmake --build .
ctest
lcov --capture --directory . --output-file coverage.info
genhtml coverage.info --output-directory coverage_html
```

## Troubleshooting

### Missing Dependencies
**Windows**: Ensure vcpkg is properly configured
```powershell
.\\vcpkg integrate install
```

**Linux**: Install missing packages
```bash
sudo apt install pkg-config
```

### CMake Can't Find CURL
```bash
# Set CURL_ROOT environment variable
export CURL_ROOT=/path/to/curl
cmake ..
```

### Build Errors
1. Clean build directory: `rm -rf build && mkdir build`
2. Update CMake: Ensure version >= 3.20
3. Check compiler: GCC 9+, Clang 10+, MSVC 2019+

## IDE Integration

### Visual Studio Code
```json
{
  "cmake.configureArgs": [
    "-DCMAKE_EXPORT_COMPILE_COMMANDS=ON"
  ],
  "C_Cpp.default.compileCommands": "${workspaceFolder}/build/compile_commands.json"
}
```

### CLion
Open `CMakeLists.txt` as project. CMake will auto-configure.

### Visual Studio
```bash
cmake .. -G "Visual Studio 17 2022" -A x64
# Open generated .sln file
```

## Performance

### Optimization Flags
```bash
# Maximum optimization
cmake .. -DCMAKE_BUILD_TYPE=Release -DCMAKE_CXX_FLAGS="-O3 -march=native"
```

### Profile Build
```bash
cmake .. -DCMAKE_BUILD_TYPE=RelWithDebInfo
cmake --build .
# Use profiling tools: gprof, perf, Instruments.app
```

## Cross-Compilation

### Windows → Linux
Use WSL or MinGW

### macOS → Universal Binary
```bash
cmake .. -DCMAKE_OSX_ARCHITECTURES="x86_64;arm64"
cmake --build .
```
