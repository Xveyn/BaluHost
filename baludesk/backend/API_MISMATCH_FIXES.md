# BaluDesk C++ Backend - API Mismatch Analysis & Fixes

## Overview
This document lists API mismatches between:
- **Python Backend** (FastAPI reference): `backend/app/api/routes/files.py`
- **C++ Backend** (BaluDesk Sync Engine): `baludesk/backend/src/`

---

## ✅ Analysis Results

### 1. Logger API
**Status:** ✅ **CORRECT**
- Implementation: `src/utils/logger.cpp/h`
- All methods are static (no getInstance() needed)
- Format string support with variadic templates
- Log levels match spdlog: trace, debug, info, warn, error, critical
- **No fixes needed**

### 2. Database API

#### 2a. File Metadata Operations
**Status:** ✅ **CORRECT**

| Operation | C++ Signature | Status | Notes |
|-----------|--------------|--------|-------|
| `upsertFileMetadata(FileMetadata)` | ✅ Exists (line 297) | OK | Takes full FileMetadata struct |
| `upsertFileMetadata(path, folderId, size, checksum, modifiedAt)` | ✅ Exists (line 347) | OK | 5 params overload |
| `getFileMetadata(path)` | ✅ Exists (line 313) | OK | Returns `std::optional<FileMetadata>` |

**Note:** Line 347 in database.cpp implements the 5-parameter overload that's used by change_detector.cpp

#### 2b. All Methods Implemented ✅
**Status:** ✅ **COMPLETE**

All methods are fully implemented in database.cpp:

| Method | Lines | Status |
|--------|-------|--------|
| `getFilesInFolder(folderId)` | 364-398 | ✅ Implemented |
| `getChangedFilesSince(timestamp)` | 399-447 | ✅ Implemented |
| `updateSyncFolderTimestamp(folderId)` | 448-463 | ✅ Implemented |

All three methods have proper SQLite queries and error handling.

### 3. HTTP Client API
**Status:** ✅ **CORRECT**

| Method | Status | Maps To |
|--------|--------|---------|
| `login(username, password)` | ✅ | `POST /api/auth/login` |
| `listFiles(path)` | ✅ | `GET /api/files/list?path=...` |
| `uploadFile(local, remote)` | ✅ | `POST /api/files/upload` |
| `downloadFile(remote, local)` | ✅ | `GET /api/files/download/{path}` |
| `getChangesSince(timestamp)` | ✅ | `GET /api/sync/changes?since={timestamp}` |

**Data Structure Mapping:**

```cpp
// C++ RemoteFile struct maps to Python FileItem
struct RemoteFile {
    std::string name;              // ← FileItem.name
    std::string path;              // ← FileItem.path
    uint64_t size;                 // ← FileItem.size
    bool isDirectory;              // ← FileItem.type (convert to "file"/"directory")
    std::string modifiedAt;        // ← FileItem.modified_at
    std::string hash;              // ← FileItem.mime_type (or new field)
};
```

### 4. Sync Engine API
**Status:** ✅ **CORRECT**

Core interface is well-designed:
- `addSyncFolder(SyncFolder&)` - modifies folder.id
- `removeSyncFolder(folderId)`
- `pauseSync(folderId)`
- `resumeSync(folderId)`
- `updateSyncFolderSettings(folderId, conflictResolution)`
- `getSyncFolders()`

---

## 🔴 Issues Found & Fixes

### Issue 1: Change Detection API (change_detector.cpp)
**Severity:** HIGH
**File:** `src/sync/change_detector.cpp`
**Line:** 47, 60, 213, 228, 242

**Problem:**
```cpp
// Line 47 - httpClient_ API call incomplete
// TODO: httpClient_->get() needs to be implemented

// Line 60 - Hardcoded timestamp instead of parsing
change.timestamp = std::chrono::system_clock::now(); // TODO: parse from API
```

**Fix Required:** Implement actual API calls instead of TODO stubs

### Issue 2: Conflict Resolver (conflict_resolver.cpp)
**Severity:** MEDIUM
**File:** `src/sync/conflict_resolver.cpp`
**Lines:** 95-97

**Problem:**
```cpp
conflict.folderId = "";           // TODO: Get from context
conflict.localModified = "";      // TODO: Add timestamp
conflict.remoteModified = "";     // TODO: Add timestamp
```

**Fix Required:** Pass context to methods to populate these fields

### Issue 3: Sync Engine - Missing Implementation (sync_engine.cpp)
**Severity:** HIGH
**File:** `src/sync/sync_engine.cpp`
**Lines:** 346, 352, 388, 394

**Problem:**
```cpp
void SyncEngine::scanLocalChanges(const SyncFolder& folder) {
    // TODO: Implement local change scanning
}

void SyncEngine::fetchRemoteChanges(const SyncFolder& folder) {
    // TODO: Implement remote change fetching
}

void SyncEngine::downloadFile(const std::string& remotePath, const std::string& localPath) {
    // TODO: Implement download
}

void SyncEngine::handleConflict(const std::string& path) {
    // TODO: Implement conflict handling
}
```

**Fix Required:** Implement these critical functions

### Issue 4: Database - Query Implementation (database.cpp)
**Severity:** MEDIUM
**File:** `src/db/database.cpp`
**Functions:**

Need to verify if these are implemented:
```cpp
std::vector<FileMetadata> getFilesInFolder(const std::string& folderId);
std::vector<FileMetadata> getChangedFilesSince(const std::string& timestamp);
bool updateSyncFolderTimestamp(const std::string& folderId);
```

---

## 📋 Implementation Roadmap

### Phase 1: Quick Fixes (enables build)
1. ✅ Logger - Already correct
2. ✅ Database::getFileMetadata() - Already returns optional
3. ✅ HTTP Client - Already correct

### Phase 2: Core Implementation (enables sync)
1. Implement `scanLocalChanges()` using filesystem iteration + change_detector
2. Implement `fetchRemoteChanges()` using httpClient_->getChangesSince()
3. Implement `downloadFile()` using httpClient_->downloadFile()
4. Implement `handleConflict()` using conflictResolver_

### Phase 3: Database Completeness
1. Implement `getFilesInFolder(folderId)`
2. Implement `getChangedFilesSince(timestamp)`
3. Implement `updateSyncFolderTimestamp(folderId)`

---

## 📊 API Comparison Table

### FileItem (Python) → RemoteFile (C++)

| Python Schema | C++ Struct | Type | Required |
|---------------|-----------|------|----------|
| `name` | `name` | str/string | ✅ |
| `path` | `path` | str/string | ✅ |
| `size` | `size` | int/uint64_t | ✅ |
| `type` (file/dir) | `isDirectory` | Literal/bool | ✅ |
| `modified_at` | `modifiedAt` | datetime/string | ✅ |
| `owner_id` | ❌ **MISSING** | str/string | ⚠️ |
| `mime_type` | `hash` (reused) | str/string | ⚠️ |
| `file_id` | ❌ **MISSING** | int | ⚠️ |

**Missing Fields in C++ to add if needed:**
```cpp
struct RemoteFile {
    // ... existing ...
    std::string ownerId;     // Add: for permission management
    uint64_t fileId;         // Add: for database references
    std::string mimeType;    // Add: file type detection
};
```

---

## ✨ Summary

### What's Already Working:
- ✅ Logger
- ✅ HTTP Client (structure)
- ✅ Database schema & basic operations
- ✅ File Watchers (all platforms)
- ✅ Sync Engine (skeleton)

### What Needs Implementation:
- ❌ Local change scanning
- ❌ Remote change fetching  
- ❌ Conflict handling
- ❌ Download operations
- ⚠️ Hash calculations (SHA256 stub)
- ⚠️ Timestamp parsing from API responses

### Estimated Effort:
- **Quick Fixes:** 30 minutes (verify Database methods)
- **Core Implementation:** 3-4 hours (scanLocalChanges, fetchRemoteChanges, download)
- **Polish:** 2 hours (error handling, testing)

---

**Last Updated:** January 5, 2026
**Status:** Analysis Complete - Ready for Implementation
