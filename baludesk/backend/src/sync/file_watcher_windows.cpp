#include "file_watcher_windows.h"
#include "utils/logger.h"
#include <filesystem>

namespace fs = std::filesystem;

namespace baludesk {

// ============================================================================
// Constructor & Destructor
// ============================================================================

WindowsFileWatcher::WindowsFileWatcher() {
    Logger::info("Windows FileWatcher initialized");
}

WindowsFileWatcher::~WindowsFileWatcher() {
    stopAll();
    Logger::info("Windows FileWatcher destroyed");
}

// ============================================================================
// Public Interface
// ============================================================================

bool WindowsFileWatcher::startWatch(const std::string& path) {
    std::lock_guard<std::mutex> lock(mutex_);

    // Check if already watching
    if (watches_.find(path) != watches_.end()) {
        Logger::warn("Already watching: {}", path);
        return false;
    }

    // Verify path exists
    if (!fs::exists(path) || !fs::is_directory(path)) {
        Logger::error("Invalid directory path: {}", path);
        return false;
    }

    // Create watch context
    auto ctx = std::make_unique<WatchContext>();
    ctx->path = path;

    // Open directory handle - convert UTF-8 to wide string
    int wideLen = MultiByteToWideChar(CP_UTF8, 0, path.c_str(), -1, NULL, 0);
    std::wstring widePath(wideLen, 0);
    MultiByteToWideChar(CP_UTF8, 0, path.c_str(), -1, &widePath[0], wideLen);
    
    ctx->dirHandle = CreateFileW(
        widePath.c_str(),
        FILE_LIST_DIRECTORY,
        FILE_SHARE_READ | FILE_SHARE_WRITE | FILE_SHARE_DELETE,
        NULL,
        OPEN_EXISTING,
        FILE_FLAG_BACKUP_SEMANTICS | FILE_FLAG_OVERLAPPED,
        NULL
    );

    if (ctx->dirHandle == INVALID_HANDLE_VALUE) {
        Logger::error("Failed to open directory: {} (Error: {})", path, GetLastError());
        return false;
    }

    // Create stop event
    ctx->stopEvent = CreateEvent(NULL, TRUE, FALSE, NULL);
    if (ctx->stopEvent == INVALID_HANDLE_VALUE) {
        Logger::error("Failed to create stop event");
        CloseHandle(ctx->dirHandle);
        return false;
    }

    // Create OVERLAPPED event
    ctx->overlapped.hEvent = CreateEvent(NULL, TRUE, FALSE, NULL);
    if (ctx->overlapped.hEvent == INVALID_HANDLE_VALUE) {
        Logger::error("Failed to create overlapped event");
        CloseHandle(ctx->dirHandle);
        CloseHandle(ctx->stopEvent);
        return false;
    }

    // Start watch thread
    ctx->running = true;
    WatchContext* ctxPtr = ctx.get();
    ctx->watchThread = std::thread(&WindowsFileWatcher::watchThreadFunc, this, ctxPtr);

    watches_[path] = std::move(ctx);
    Logger::info("Started watching: {}", path);
    return true;
}

void WindowsFileWatcher::stopWatch(const std::string& path) {
    std::lock_guard<std::mutex> lock(mutex_);

    auto it = watches_.find(path);
    if (it == watches_.end()) {
        return;
    }

    auto& ctx = it->second;
    
    // Signal stop
    ctx->running = false;
    SetEvent(ctx->stopEvent);

    // Wait for thread
    if (ctx->watchThread.joinable()) {
        ctx->watchThread.join();
    }

    // Cleanup handles
    if (ctx->overlapped.hEvent != INVALID_HANDLE_VALUE) {
        CloseHandle(ctx->overlapped.hEvent);
    }
    if (ctx->stopEvent != INVALID_HANDLE_VALUE) {
        CloseHandle(ctx->stopEvent);
    }
    if (ctx->dirHandle != INVALID_HANDLE_VALUE) {
        CloseHandle(ctx->dirHandle);
    }

    watches_.erase(it);
    Logger::info("Stopped watching: {}", path);
}

void WindowsFileWatcher::stopAll() {
    std::lock_guard<std::mutex> lock(mutex_);

    for (auto& [path, ctx] : watches_) {
        ctx->running = false;
        SetEvent(ctx->stopEvent);
    }

    for (auto& [path, ctx] : watches_) {
        if (ctx->watchThread.joinable()) {
            ctx->watchThread.join();
        }
        
        if (ctx->overlapped.hEvent != INVALID_HANDLE_VALUE) {
            CloseHandle(ctx->overlapped.hEvent);
        }
        if (ctx->stopEvent != INVALID_HANDLE_VALUE) {
            CloseHandle(ctx->stopEvent);
        }
        if (ctx->dirHandle != INVALID_HANDLE_VALUE) {
            CloseHandle(ctx->dirHandle);
        }
    }

    watches_.clear();
    Logger::info("Stopped all watches");
}

bool WindowsFileWatcher::isWatching(const std::string& path) const {
    std::lock_guard<std::mutex> lock(mutex_);
    return watches_.find(path) != watches_.end();
}

void WindowsFileWatcher::setCallback(std::function<void(const FileEvent&)> callback) {
    std::lock_guard<std::mutex> lock(mutex_);
    callback_ = std::move(callback);
}

// ============================================================================
// Private Implementation
// ============================================================================

void WindowsFileWatcher::watchThreadFunc(WatchContext* ctx) {
    Logger::debug("Watch thread started for: {}", ctx->path);

    while (ctx->running) {
        // Start async read
        DWORD bytesReturned = 0;
        BOOL success = ReadDirectoryChangesW(
            ctx->dirHandle,
            ctx->buffer.data(),
            static_cast<DWORD>(ctx->buffer.size()),
            TRUE,  // Watch subtree
            FILE_NOTIFY_CHANGE_FILE_NAME |
            FILE_NOTIFY_CHANGE_DIR_NAME |
            FILE_NOTIFY_CHANGE_SIZE |
            FILE_NOTIFY_CHANGE_LAST_WRITE,
            &bytesReturned,
            &ctx->overlapped,
            NULL
        );

        if (!success && GetLastError() != ERROR_IO_PENDING) {
            Logger::error("ReadDirectoryChangesW failed: {}", GetLastError());
            break;
        }

        // Wait for events
        HANDLE events[] = { ctx->overlapped.hEvent, ctx->stopEvent };
        DWORD result = WaitForMultipleObjects(2, events, FALSE, INFINITE);

        if (result == WAIT_OBJECT_0) {
            // Directory change event
            if (GetOverlappedResult(ctx->dirHandle, &ctx->overlapped, &bytesReturned, FALSE)) {
                processNotifications(ctx, bytesReturned);
            }
            ResetEvent(ctx->overlapped.hEvent);
        }
        else if (result == WAIT_OBJECT_0 + 1) {
            // Stop event
            Logger::debug("Stop event received");
            break;
        }
        else {
            Logger::error("WaitForMultipleObjects failed: {}", GetLastError());
            break;
        }
    }

    Logger::debug("Watch thread stopped for: {}", ctx->path);
}

void WindowsFileWatcher::processNotifications(WatchContext* ctx, DWORD bytesReturned) {
    if (bytesReturned == 0) {
        return;
    }

    FILE_NOTIFY_INFORMATION* info = reinterpret_cast<FILE_NOTIFY_INFORMATION*>(ctx->buffer.data());

    while (true) {
        // Convert filename to UTF-8
        std::wstring wideFilename(info->FileName, info->FileNameLength / sizeof(WCHAR));
        std::string filename = wideToUtf8(wideFilename);

        // Build full path
        std::string fullPath = (fs::path(ctx->path) / filename).string();

        // Convert action
        FileAction action = convertAction(info->Action);

        // Create event
        FileEvent event;
        event.path = fullPath;
        event.action = action;
        event.size = fs::exists(fullPath) ? fs::file_size(fullPath) : 0;
        
        // Convert time_point to ISO8601 string
        auto now = std::chrono::system_clock::now();
        auto now_time_t = std::chrono::system_clock::to_time_t(now);
        std::tm tm;
        localtime_s(&tm, &now_time_t);  // Windows-safe
        char buffer[32];
        std::strftime(buffer, sizeof(buffer), "%Y-%m-%dT%H:%M:%S", &tm);
        event.timestamp = std::string(buffer);

        // Notify callback
        if (callback_) {
            callback_(event);
        }

        // Next entry
        if (info->NextEntryOffset == 0) {
            break;
        }
        info = reinterpret_cast<FILE_NOTIFY_INFORMATION*>(
            reinterpret_cast<BYTE*>(info) + info->NextEntryOffset
        );
    }
}

FileAction WindowsFileWatcher::convertAction(DWORD action) {
    switch (action) {
        case FILE_ACTION_ADDED:
            return FileAction::CREATED;
        case FILE_ACTION_REMOVED:
            return FileAction::DELETED;
        case FILE_ACTION_MODIFIED:
            return FileAction::MODIFIED;
        case FILE_ACTION_RENAMED_OLD_NAME:
            return FileAction::DELETED;
        case FILE_ACTION_RENAMED_NEW_NAME:
            return FileAction::CREATED;
        default:
            return FileAction::MODIFIED;
    }
}

std::string WindowsFileWatcher::wideToUtf8(const std::wstring& wide) {
    if (wide.empty()) return "";
    
    int size = WideCharToMultiByte(CP_UTF8, 0, wide.c_str(), -1, NULL, 0, NULL, NULL);
    std::string result(size - 1, '\0');
    WideCharToMultiByte(CP_UTF8, 0, wide.c_str(), -1, &result[0], size, NULL, NULL);
    
    return result;
}

} // namespace baludesk
