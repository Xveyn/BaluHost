#include "file_watcher_v2.h"
#include "utils/logger.h"
#include <filesystem>

#ifdef _WIN32
#include "file_watcher_windows.h"
#elif __APPLE__
#include "file_watcher_macos.h"
#elif __linux__
#include "file_watcher_linux.h"
#endif

namespace fs = std::filesystem;

namespace baludesk {

// ============================================================================
// Factory Function
// ============================================================================

std::unique_ptr<IFileWatcherImpl> createPlatformFileWatcher() {
#ifdef _WIN32
    return std::make_unique<WindowsFileWatcher>();
#elif __APPLE__
    return std::make_unique<MacOSFileWatcher>();
#elif __linux__
    return std::make_unique<LinuxFileWatcher>();
#else
    Logger::error("Platform-specific FileWatcher not implemented");
    return nullptr;
#endif
}

// ============================================================================
// FileWatcher Implementation (Facade with Debouncing)
// ============================================================================

FileWatcher::FileWatcher()
    : impl_(createPlatformFileWatcher()) {
    
    if (!impl_) {
        throw std::runtime_error("Failed to create platform file watcher");
    }

    // Set internal callback that handles debouncing
    impl_->setCallback([this](const FileEvent& event) {
        onFileEvent(event);
    });

    Logger::info("FileWatcher facade initialized");
}

FileWatcher::~FileWatcher() {
    stop();
    Logger::info("FileWatcher facade destroyed");
}

bool FileWatcher::watch(const std::string& path) {
    // Validate path
    std::error_code ec;
    fs::path fsPath(path);
    
    if (!fs::exists(fsPath, ec)) {
        Logger::error("Path does not exist: {}", path);
        return false;
    }

    if (!fs::is_directory(fsPath, ec)) {
        Logger::error("Path is not a directory: {}", path);
        return false;
    }

    // Normalize path (absolute, no trailing slash)
    std::string normalizedPath = fs::canonical(fsPath, ec).string();
    if (ec) {
        Logger::error("Failed to normalize path: {}", path);
        return false;
    }

    Logger::info("Watching: {}", normalizedPath);
    return impl_->startWatch(normalizedPath);
}

void FileWatcher::unwatch(const std::string& path) {
    std::error_code ec;
    std::string normalizedPath = fs::canonical(path, ec).string();
    
    if (ec) {
        // Path might not exist anymore, try with original path
        impl_->stopWatch(path);
    } else {
        impl_->stopWatch(normalizedPath);
    }
}

void FileWatcher::stop() {
    if (impl_) {
        impl_->stopAll();
    }
}

void FileWatcher::setCallback(std::function<void(const FileEvent&)> callback) {
    std::lock_guard<std::mutex> lock(mutex_);
    userCallback_ = std::move(callback);
}

void FileWatcher::setDebounceDelay(int delayMs) {
    std::lock_guard<std::mutex> lock(mutex_);
    debounceDelay_ = std::chrono::milliseconds(delayMs);
    Logger::debug("Debounce delay set to {}ms", delayMs);
}

bool FileWatcher::isWatching(const std::string& path) const {
    if (!impl_) return false;
    return impl_->isWatching(path);
}

// ============================================================================
// Private Implementation (Debouncing Logic)
// ============================================================================

void FileWatcher::onFileEvent(const FileEvent& event) {
    // Check if should debounce
    if (shouldDebounce(event.path, event.action)) {
        Logger::trace("Debounced event: {} {}", 
            event.action == FileAction::CREATED ? "CREATE" :
            event.action == FileAction::MODIFIED ? "MODIFY" : "DELETE",
            event.path);
        return;
    }

    // Update debounce map
    updateDebounceEntry(event.path, event.action);

    // Forward to user callback
    std::lock_guard<std::mutex> lock(mutex_);
    if (userCallback_) {
        userCallback_(event);
    }

    Logger::debug("File event: {} {}",
        event.action == FileAction::CREATED ? "CREATE" :
        event.action == FileAction::MODIFIED ? "MODIFY" : "DELETE",
        event.path);
}

bool FileWatcher::shouldDebounce(const std::string& path, FileAction action) {
    std::lock_guard<std::mutex> lock(mutex_);

    auto it = debounceMap_.find(path);
    if (it == debounceMap_.end()) {
        return false;  // First event for this path
    }

    const auto& entry = it->second;
    auto now = std::chrono::steady_clock::now();
    auto elapsed = std::chrono::duration_cast<std::chrono::milliseconds>(
        now - entry.lastEvent
    );

    // Debounce if:
    // 1. Same action within debounce window
    // 2. MODIFY events within window (often duplicate)
    if (elapsed < debounceDelay_) {
        if (entry.lastAction == action) {
            return true;  // Same action, debounce
        }
        
        if (action == FileAction::MODIFIED) {
            return true;  // Always debounce MODIFY events
        }
    }

    return false;
}

void FileWatcher::updateDebounceEntry(const std::string& path, FileAction action) {
    std::lock_guard<std::mutex> lock(mutex_);

    DebounceEntry entry;
    entry.lastEvent = std::chrono::steady_clock::now();
    entry.lastAction = action;

    debounceMap_[path] = entry;

    // Cleanup old entries (older than 10 seconds)
    auto now = std::chrono::steady_clock::now();
    auto threshold = now - std::chrono::seconds(10);

    for (auto it = debounceMap_.begin(); it != debounceMap_.end();) {
        if (it->second.lastEvent < threshold) {
            it = debounceMap_.erase(it);
        } else {
            ++it;
        }
    }
}

} // namespace baludesk
