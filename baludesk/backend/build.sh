#!/usr/bin/env bash
# ============================================================================
# BaluDesk Backend Build Script (Linux/macOS)
# ============================================================================

set -euo pipefail

# Configuration
BUILD_TYPE="${1:-Release}"
BUILD_DIR="build"
CORES=$(nproc 2>/dev/null || sysctl -n hw.ncpu 2>/dev/null || echo 4)

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Print with color
print_header() {
    echo -e "${GREEN}============================================================================${NC}"
    echo -e "${GREEN}$1${NC}"
    echo -e "${GREEN}============================================================================${NC}"
}

print_error() {
    echo -e "${RED}ERROR: $1${NC}" >&2
}

print_warning() {
    echo -e "${YELLOW}WARNING: $1${NC}"
}

# Handle clean
if [[ "${1:-}" == "clean" ]]; then
    echo "Cleaning build directory..."
    rm -rf "$BUILD_DIR"
    echo "Clean complete."
    exit 0
fi

print_header "BaluDesk C++ Backend - Build Script"
echo "Build Type: $BUILD_TYPE"
echo "Build Directory: $BUILD_DIR"
echo "CPU Cores: $CORES"
echo

# Check dependencies
print_header "[0/4] Checking dependencies"
echo "Checking for required tools..."

command -v cmake >/dev/null 2>&1 || {
    print_error "cmake not found. Please install CMake 3.20+"
    exit 1
}

command -v g++ >/dev/null 2>&1 || command -v clang++ >/dev/null 2>&1 || {
    print_error "No C++ compiler found (g++ or clang++)"
    exit 1
}

echo "✓ CMake found: $(cmake --version | head -n1)"
echo "✓ Compiler found"

# Check for libcurl
if ! pkg-config --exists libcurl 2>/dev/null; then
    print_warning "libcurl not found via pkg-config. Install: sudo apt-get install libcurl4-openssl-dev"
fi

# Check for sqlite3
if ! pkg-config --exists sqlite3 2>/dev/null; then
    print_warning "sqlite3 not found via pkg-config. Install: sudo apt-get install libsqlite3-dev"
fi

echo

# Create build directory
mkdir -p "$BUILD_DIR"
cd "$BUILD_DIR"

# Configure
print_header "[1/4] Configuring CMake"
cmake .. \
    -DCMAKE_BUILD_TYPE="$BUILD_TYPE" \
    -DCMAKE_EXPORT_COMPILE_COMMANDS=ON \
    -G "Unix Makefiles"

# Build
print_header "[2/4] Building project (using $CORES cores)"
cmake --build . --config "$BUILD_TYPE" --parallel "$CORES"

# Optional: Run tests
if [[ "${2:-}" == "test" ]]; then
    print_header "[3/4] Running tests"
    ctest --output-on-failure --parallel "$CORES"
else
    echo -e "${YELLOW}Skipping tests (use './build.sh Release test' to run)${NC}"
fi

# Success
cd ..
print_header "[4/4] Build complete!"
echo "Executable: ./$BUILD_DIR/baludesk-backend"
echo
echo "To run: ./$BUILD_DIR/baludesk-backend"
echo "To clean: ./build.sh clean"
echo
