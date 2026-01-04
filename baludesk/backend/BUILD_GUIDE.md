# BaluDesk Backend - Build Guide

## 📋 Overview

The BaluDesk Backend is a **cross-platform C++ sync engine** built with modern C++17 standards. This guide covers:
- Dependency installation
- Build process (Windows, macOS, Linux)
- Running tests
- Troubleshooting

---

## 🔧 Prerequisites

### Required Tools

| Tool | Minimum Version | Purpose |
|------|----------------|---------|
| **CMake** | 3.20+ | Build system generator |
| **C++ Compiler** | C++17 support | Compilation |
| **vcpkg** (Windows) | Latest | Dependency management |
| **pkg-config** (Linux/macOS) | Any | Library detection |

### Required Libraries

| Library | Version | Purpose |
|---------|---------|---------|
| **libcurl** | 8.5+ | HTTP client |
| **SQLite3** | 3.40+ | Local database |
| **nlohmann/json** | 3.11+ | JSON parsing (auto-fetched) |
| **spdlog** | 1.12+ | Logging (auto-fetched) |
| **GoogleTest** | 1.14+ | Unit testing (auto-fetched) |

---

## 🪟 Windows Setup

### 1. Install Visual Studio 2022
- Download: [Visual Studio 2022 Community](https://visualstudio.microsoft.com/)
- Required Components:
  - Desktop development with C++
  - CMake tools for Windows
  - Windows 10/11 SDK

### 2. Install vcpkg
```powershell
cd "F:\Programme (x86)\Baluhost"
git clone https://github.com/Microsoft/vcpkg.git
cd vcpkg
.\bootstrap-vcpkg.bat
```

### 3. Install Dependencies via vcpkg
```powershell
.\vcpkg install curl:x64-windows
.\vcpkg install sqlite3:x64-windows
.\vcpkg integrate install
```

### 4. Build the Backend
```powershell
cd "F:\Programme (x86)\Baluhost\baludesk\backend"
.\build.bat release
```

### 5. Run Tests
```powershell
cd build\Release
.\baludesk-tests.exe
```

### Common Issues (Windows)

**Problem:** `CURL not found`
```powershell
# Solution: Re-install with triplet
.\vcpkg install curl:x64-windows
```

**Problem:** `SQLite3 not found`
```powershell
# Solution: Check vcpkg integration
.\vcpkg integrate install
```

**Problem:** Build fails with `/WX` error
```cmake
# Solution: Temporarily disable warnings-as-errors in CMakeLists.txt
# Change: add_compile_options(/W4 /WX)
# To:     add_compile_options(/W4)
```

---

## 🐧 Linux Setup

### 1. Install Build Tools
```bash
# Ubuntu/Debian
sudo apt-get update
sudo apt-get install -y \
    build-essential \
    cmake \
    git \
    pkg-config

# Fedora/RHEL
sudo dnf install -y \
    gcc-c++ \
    cmake \
    git \
    pkgconfig
```

### 2. Install Dependencies
```bash
# Ubuntu/Debian
sudo apt-get install -y \
    libcurl4-openssl-dev \
    libsqlite3-dev

# Fedora/RHEL
sudo dnf install -y \
    libcurl-devel \
    sqlite-devel
```

### 3. Build the Backend
```bash
cd baludesk/backend
chmod +x build.sh
./build.sh Release
```

### 4. Run Tests
```bash
./build/baludesk-tests
```

### Common Issues (Linux)

**Problem:** `libcurl not found`
```bash
# Solution: Install dev package
sudo apt-get install libcurl4-openssl-dev
```

**Problem:** `sqlite3.h not found`
```bash
# Solution: Install sqlite3 dev package
sudo apt-get install libsqlite3-dev
```

**Problem:** Permission denied on build.sh
```bash
# Solution: Make executable
chmod +x build.sh
```

---

## 🍎 macOS Setup

### 1. Install Xcode Command Line Tools
```bash
xcode-select --install
```

### 2. Install Homebrew
```bash
/bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
```

### 3. Install Dependencies
```bash
brew install cmake curl sqlite3
```

### 4. Build the Backend
```bash
cd baludesk/backend
chmod +x build.sh
./build.sh Release
```

### 5. Run Tests
```bash
./build/baludesk-tests
```

### Common Issues (macOS)

**Problem:** `curl not found`
```bash
# Solution: System curl might not have dev headers
brew install curl
```

**Problem:** Apple Silicon (M1/M2) build issues
```bash
# Solution: Use native arch
cmake .. -DCMAKE_OSX_ARCHITECTURES=arm64
```

---

## 🏗️ Build Options

### Build Types
```bash
# Debug build (with symbols, no optimization)
./build.sh Debug

# Release build (optimized, no symbols)
./build.sh Release

# Clean build directory
./build.sh clean
```

### CMake Options
```bash
# Disable tests
cmake .. -DBUILD_TESTS=OFF

# Specify compiler
cmake .. -DCMAKE_CXX_COMPILER=g++-12

# Custom install prefix
cmake .. -DCMAKE_INSTALL_PREFIX=/usr/local

# Verbose build
cmake --build . --verbose
```

---

## 🧪 Testing

### Run All Tests
```bash
# Linux/macOS
./build/baludesk-tests

# Windows
.\build\Release\baludesk-tests.exe
```

### Run Specific Tests
```bash
# Run only Database tests
./build/baludesk-tests --gtest_filter=DatabaseTest.*

# Run only Logger tests
./build/baludesk-tests --gtest_filter=LoggerTest.*
```

### Test with Verbose Output
```bash
./build/baludesk-tests --gtest_print_time=1
```

### CTest Integration
```bash
cd build
ctest --output-on-failure
```

---

## 🐛 Debugging

### Debug Build with GDB (Linux/macOS)
```bash
./build.sh Debug
gdb ./build/baludesk-backend
```

### Debug Build with LLDB (macOS)
```bash
./build.sh Debug
lldb ./build/baludesk-backend
```

### Debug Build with Visual Studio (Windows)
1. Open `baludesk/backend/build/BaluDeskBackend.sln` in Visual Studio
2. Set `baludesk-backend` as startup project
3. Press F5 to debug

### Memory Leak Detection (Linux)
```bash
valgrind --leak-check=full ./build/baludesk-backend
```

### Address Sanitizer
```bash
# Add to CMake
cmake .. -DCMAKE_CXX_FLAGS="-fsanitize=address -g"
cmake --build .
./build/baludesk-backend
```

---

## 📊 Performance Profiling

### Linux (perf)
```bash
perf record ./build/baludesk-backend
perf report
```

### macOS (Instruments)
```bash
instruments -t "Time Profiler" ./build/baludesk-backend
```

### Windows (Visual Studio Profiler)
- Debug → Performance Profiler → CPU Usage

---

## 🔍 Static Analysis

### Clang-Tidy (All Platforms)
```bash
# Generate compile_commands.json
cmake .. -DCMAKE_EXPORT_COMPILE_COMMANDS=ON

# Run clang-tidy
clang-tidy src/**/*.cpp -- -std=c++17
```

### Cppcheck
```bash
cppcheck --enable=all --inconclusive src/
```

---

## 📦 Installation

### System-Wide Install (Linux/macOS)
```bash
cd build
sudo cmake --install .
```

### Custom Install Location
```bash
cmake .. -DCMAKE_INSTALL_PREFIX=$HOME/.local
cmake --build . --target install
```

---

## 🚀 CI/CD Integration

### GitHub Actions Example
```yaml
name: Build & Test
on: [push, pull_request]
jobs:
  build:
    runs-on: ${{ matrix.os }}
    strategy:
      matrix:
        os: [ubuntu-latest, macos-latest, windows-latest]
    steps:
      - uses: actions/checkout@v3
      - name: Install dependencies (Ubuntu)
        if: matrix.os == 'ubuntu-latest'
        run: sudo apt-get install libcurl4-openssl-dev libsqlite3-dev
      - name: Build
        run: |
          cd baludesk/backend
          ./build.sh Release
      - name: Test
        run: ./baludesk/backend/build/baludesk-tests
```

---

## 📝 VS Code Integration

### Recommended Extensions
- C/C++ (Microsoft)
- CMake Tools
- GoogleTest Adapter

### Build Tasks
Press `Ctrl+Shift+B` to access:
- Build BaluDesk Backend (Debug)
- Build BaluDesk Backend (Release)
- Clean BaluDesk Backend Build

### Launch Configuration (.vscode/launch.json)
```json
{
  "version": "0.2.0",
  "configurations": [
    {
      "name": "Debug BaluDesk Backend",
      "type": "cppdbg",
      "request": "launch",
      "program": "${workspaceFolder}/baludesk/backend/build/Debug/baludesk-backend",
      "cwd": "${workspaceFolder}/baludesk/backend",
      "MIMode": "gdb"
    }
  ]
}
```

---

## 🔗 Useful Links

- [CMake Documentation](https://cmake.org/documentation/)
- [vcpkg Documentation](https://vcpkg.io/en/getting-started.html)
- [GoogleTest Documentation](https://google.github.io/googletest/)
- [spdlog Documentation](https://github.com/gabime/spdlog)

---

**Last Updated:** January 4, 2026  
**Maintainer:** BaluHost Development Team
