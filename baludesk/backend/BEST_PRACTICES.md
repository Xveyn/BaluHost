# C++ Best Practices - BaluDesk Backend

## 📚 Table of Contents
1. [Code Organization](#code-organization)
2. [Modern C++17 Features](#modern-c17-features)
3. [Error Handling](#error-handling)
4. [Memory Management](#memory-management)
5. [Threading & Concurrency](#threading--concurrency)
6. [Logging Best Practices](#logging-best-practices)
7. [Database Patterns](#database-patterns)
8. [Testing Guidelines](#testing-guidelines)
9. [Performance Tips](#performance-tips)
10. [Security Considerations](#security-considerations)

---

## 🗂️ Code Organization

### Header Guards
✅ **Good:** Pragma once (modern, faster)
```cpp
#pragma once

namespace baludesk {
    class MyClass { };
}
```

❌ **Avoid:** Traditional include guards (verbose)
```cpp
#ifndef MYCLASS_H
#define MYCLASS_H
// ...
#endif
```

### Forward Declarations
✅ **Good:** Reduce compile times
```cpp
// In header file
class Database;  // Forward declaration

class SyncEngine {
    std::unique_ptr<Database> db_;  // Only pointer, no definition needed
};
```

✅ **Implementation file includes full header**
```cpp
// In .cpp file
#include "db/database.h"  // Full definition
```

### Namespace Usage
✅ **Good:** Consistent namespace hierarchy
```cpp
namespace baludesk {
namespace sync {
    class SyncEngine { };
}
}

// Or C++17 nested namespace
namespace baludesk::sync {
    class SyncEngine { };
}
```

---

## 🚀 Modern C++17 Features

### std::optional (Replace nullable returns)
✅ **Good:**
```cpp
std::optional<FileMetadata> getFileMetadata(const std::string& path) {
    // ... query database
    if (found) {
        return metadata;
    }
    return std::nullopt;  // No value
}

// Usage
auto metadata = db.getFileMetadata("/path/to/file");
if (metadata) {
    std::cout << "Size: " << metadata->size << std::endl;
}
```

❌ **Avoid:** Raw pointers or exceptions for "not found"
```cpp
FileMetadata* getFileMetadata(const std::string& path); // Bad: manual memory management
```

### std::filesystem (Path manipulation)
✅ **Good:**
```cpp
#include <filesystem>
namespace fs = std::filesystem;

bool isValidPath(const std::string& path) {
    fs::path p(path);
    return fs::exists(p) && fs::is_regular_file(p);
}
```

### Structured Bindings
✅ **Good:**
```cpp
std::map<std::string, int> stats = getStats();
for (const auto& [key, value] : stats) {
    std::cout << key << ": " << value << std::endl;
}
```

### std::string_view (Read-only string refs)
✅ **Good:** Avoid unnecessary string copies
```cpp
void processPath(std::string_view path) {
    // No copy, just a view
}
```

---

## ⚠️ Error Handling

### RAII Pattern (Resource Acquisition Is Initialization)
✅ **Good:** Automatic cleanup
```cpp
class Database {
public:
    Database(const std::string& path) {
        sqlite3_open(path.c_str(), &db_);
    }
    
    ~Database() {
        if (db_) sqlite3_close(db_);  // Automatic cleanup
    }
    
private:
    sqlite3* db_;
};
```

### Exception Safety
✅ **Good:** Use RAII + std::unique_ptr
```cpp
void processFile(const std::string& path) {
    auto file = std::make_unique<std::ifstream>(path);
    // Even if exception thrown, file is automatically closed
}
```

### Error Result Pattern
✅ **Good:** Explicit error handling
```cpp
struct Result {
    bool success;
    std::string errorMessage;
};

Result uploadFile(const std::string& path) {
    if (!fileExists(path)) {
        return { false, "File not found" };
    }
    // ... upload logic
    return { true, "" };
}

// Usage
auto result = uploadFile("/path/to/file");
if (!result.success) {
    Logger::error("Upload failed: {}", result.errorMessage);
}
```

---

## 💾 Memory Management

### Smart Pointers (Always prefer)
✅ **Good:**
```cpp
// Unique ownership
std::unique_ptr<Database> db_ = std::make_unique<Database>(path);

// Shared ownership (only if truly needed)
std::shared_ptr<HttpClient> httpClient_ = std::make_shared<HttpClient>(url);
```

❌ **Avoid:** Raw pointers for ownership
```cpp
Database* db_ = new Database(path);  // BAD: Manual delete needed
```

### Rule of Five (if managing resources)
```cpp
class MyClass {
public:
    // 1. Destructor
    ~MyClass() { cleanup(); }
    
    // 2. Copy constructor
    MyClass(const MyClass& other) { /* deep copy */ }
    
    // 3. Copy assignment
    MyClass& operator=(const MyClass& other) { /* copy-and-swap */ }
    
    // 4. Move constructor
    MyClass(MyClass&& other) noexcept { /* steal resources */ }
    
    // 5. Move assignment
    MyClass& operator=(MyClass&& other) noexcept { /* steal resources */ }
};
```

**OR** use Rule of Zero (prefer):
```cpp
class MyClass {
    // Use std::unique_ptr, std::vector, etc.
    // Compiler generates all special members correctly
    std::unique_ptr<Data> data_;
};
```

---

## 🧵 Threading & Concurrency

### Mutex Protection
✅ **Good:** RAII lock guard
```cpp
std::mutex queueMutex_;
std::queue<FileEvent> eventQueue_;

void addEvent(const FileEvent& event) {
    std::lock_guard<std::mutex> lock(queueMutex_);
    eventQueue_.push(event);
}  // Mutex automatically released
```

### Atomic Operations
✅ **Good:** Lock-free for simple flags
```cpp
std::atomic<bool> running_{false};

void stop() {
    running_.store(false);  // Thread-safe
}
```

### Thread Pool Pattern
✅ **Good:** Reuse threads
```cpp
class ThreadPool {
public:
    explicit ThreadPool(size_t numThreads) {
        for (size_t i = 0; i < numThreads; ++i) {
            workers_.emplace_back([this] { workerThread(); });
        }
    }
    
    ~ThreadPool() {
        stop();
    }
    
    template<typename Func>
    void enqueue(Func&& task) {
        std::lock_guard<std::mutex> lock(queueMutex_);
        tasks_.push(std::forward<Func>(task));
        condition_.notify_one();
    }
    
private:
    std::vector<std::thread> workers_;
    std::queue<std::function<void()>> tasks_;
    std::mutex queueMutex_;
    std::condition_variable condition_;
};
```

---

## 📝 Logging Best Practices

### Use Structured Logging
✅ **Good:** Format strings with spdlog
```cpp
Logger::info("User {} logged in from IP {}", username, ipAddress);
Logger::error("Failed to upload file {}: {}", filePath, errorMessage);
```

❌ **Avoid:** String concatenation
```cpp
Logger::info("User " + username + " logged in");  // BAD: inefficient
```

### Log Levels
```cpp
Logger::trace("Entering function processFile");       // Debug only
Logger::debug("Processing file: {}", path);           // Development
Logger::info("Sync completed successfully");          // Normal operation
Logger::warn("Retrying upload attempt {}", attempt);  // Recoverable issues
Logger::error("Failed to connect to server: {}", e);  // Errors
Logger::critical("Database corrupted!");              // Fatal errors
```

### Performance-Critical Logging
✅ **Good:** Check log level before expensive operations
```cpp
if (spdlog::should_log(spdlog::level::debug)) {
    std::string expensiveDebugInfo = generateDetailedReport();
    Logger::debug("Report: {}", expensiveDebugInfo);
}
```

---

## 🗄️ Database Patterns

### Prepared Statements (Always)
✅ **Good:** Prevents SQL injection + performance
```cpp
sqlite3_stmt* prepareStatement(const std::string& query) {
    sqlite3_stmt* stmt;
    sqlite3_prepare_v2(db_, query.c_str(), -1, &stmt, nullptr);
    return stmt;
}

// Usage
auto stmt = prepareStatement("SELECT * FROM files WHERE path = ?");
sqlite3_bind_text(stmt, 1, path.c_str(), -1, SQLITE_TRANSIENT);
sqlite3_step(stmt);
sqlite3_finalize(stmt);
```

### Transaction Batching
✅ **Good:** Batch inserts for performance
```cpp
bool insertMultipleFiles(const std::vector<FileMetadata>& files) {
    executeQuery("BEGIN TRANSACTION;");
    
    for (const auto& file : files) {
        if (!upsertFileMetadata(file)) {
            executeQuery("ROLLBACK;");
            return false;
        }
    }
    
    executeQuery("COMMIT;");
    return true;
}
```

---

## 🧪 Testing Guidelines

### Test Fixtures (Setup/Teardown)
```cpp
class DatabaseTest : public ::testing::Test {
protected:
    void SetUp() override {
        tempDb_ = createTempDatabase();
        db_ = std::make_unique<Database>(tempDb_);
    }
    
    void TearDown() override {
        db_.reset();
        std::filesystem::remove(tempDb_);
    }
    
    std::string tempDb_;
    std::unique_ptr<Database> db_;
};
```

### Parameterized Tests
```cpp
class SyncTest : public ::testing::TestWithParam<std::string> { };

TEST_P(SyncTest, HandlesDifferentPaths) {
    std::string path = GetParam();
    EXPECT_TRUE(syncEngine.validatePath(path));
}

INSTANTIATE_TEST_SUITE_P(
    PathVariations,
    SyncTest,
    ::testing::Values("/home/user", "/tmp", "/var/log")
);
```

---

## ⚡ Performance Tips

### Avoid Unnecessary Copies
✅ **Good:** Pass by const reference
```cpp
void processFile(const std::string& path) { }  // No copy
```

### Reserve Vector Capacity
✅ **Good:** Preallocate memory
```cpp
std::vector<FileMetadata> files;
files.reserve(1000);  // Avoid reallocation
```

### Move Semantics
✅ **Good:** Transfer ownership
```cpp
std::vector<FileMetadata> getFiles() {
    std::vector<FileMetadata> files = queryDatabase();
    return files;  // Automatic move (RVO)
}
```

---

## 🔒 Security Considerations

### Input Validation
✅ **Good:** Sanitize all inputs
```cpp
bool isValidPath(const std::string& path) {
    if (path.find("..") != std::string::npos) {
        return false;  // Path traversal attack
    }
    return fs::exists(path) && fs::is_regular_file(path);
}
```

### Secure String Handling
✅ **Good:** Use std::string, not C-strings
```cpp
std::string password = getUserPassword();
// std::string automatically manages memory
```

### Token Storage
✅ **Good:** Never log sensitive data
```cpp
void authenticate(const std::string& token) {
    Logger::info("User authenticated");  // Good
    // Logger::debug("Token: {}", token);  // BAD: Security risk!
}
```

---

## 📚 References

- [C++ Core Guidelines](https://isocpp.github.io/CppCoreGuidelines/)
- [Google C++ Style Guide](https://google.github.io/styleguide/cppguide.html)
- [Modern C++ Best Practices](https://www.modernescpp.com/)

---

**Last Updated:** January 4, 2026  
**Maintainer:** BaluHost Development Team
