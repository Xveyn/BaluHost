#include "file_watcher_linux.h"
#include "utils/logger.h"
#include <filesystem>
#include <sys/inotify.h>
#include <unistd.h>
#include <ftw.h>
#include <cstring>
#include <chrono>

namespace fs = std::filesystem;

namespace baludesk {

LinuxFileWatcher::LinuxFileWatcher() {
    // Initialize inotify
    inotifyFd_ = inotify_init1(IN_NONBLOCK | IN_CLOEXEC);
    if (inotifyFd_ == -1) {
        Logger::error("Failed to initialize inotify: {}", strerror(errno));
        return;
    }

    // Start watch thread
    running_ = true;
    watchThread_ = std::thread(&LinuxFileWatcher::watchThreadFunc, this);
    Logger::info("Linux FileWatcher initialized");
}

LinuxFileWatcher::~LinuxFileWatcher() {
    stopAll();
    Logger::info("Linux FileWatcher destroyed");
}

bool LinuxFileWatcher::startWatch(const std::string& path) {
    std::lock_guard<std::mutex> lock(mutex_);

    if (inotifyFd_ == -1) {
        Logger::error("inotify not initialized");
        return false;
    }

    // Validate path
    std::error_code ec;
    if (!fs::exists(path, ec) || !fs::is_directory(path, ec)) {
        Logger::error("Path does not exist or is not a directory: {}", path);
        return false;
    }

    // Check if already watching
    if (watches_.find(path) != watches_.end()) {
        Logger::debug("Already watching: {}", path);
        return true;
    }

    // Create watch context
    auto ctx = std::make_unique<WatchContext>();
    ctx->path = path;

    // Add watch with flags for file-level events
    uint32_t mask = IN_CREATE | IN_DELETE | IN_MODIFY | 
                    IN_MOVED_FROM | IN_MOVED_TO | IN_EXCL_UNLINK;
    
    ctx->watchDescriptor = inotify_add_watch(inotifyFd_, path.c_str(), mask);
    if (ctx->watchDescriptor == -1) {
        Logger::error("Failed to add inotify watch for {}: {}", path, strerror(errno));
        return false;
    }

    // Map watch descriptor to path
    watchDescriptorMap_[ctx->watchDescriptor] = path;

    // Optionally add watches for subdirectories
    // For now, we use IN_ONLYDIR implicitly by watching with IN_EXCL_UNLINK
    // Recursive watching can be added if needed

    watches_[path] = std::move(ctx);
    Logger::info("Started watching: {}", path);
    return true;
}

void LinuxFileWatcher::stopWatch(const std::string& path) {
    std::lock_guard<std::mutex> lock(mutex_);

    auto it = watches_.find(path);
    if (it == watches_.end()) {
        return;
    }

    auto& ctx = it->second;

    // Remove inotify watch
    if (ctx->watchDescriptor != -1) {
        inotify_rm_watch(inotifyFd_, ctx->watchDescriptor);
        watchDescriptorMap_.erase(ctx->watchDescriptor);
    }

    watches_.erase(it);
    Logger::info("Stopped watching: {}", path);
}

void LinuxFileWatcher::stopAll() {
    {
        std::lock_guard<std::mutex> lock(mutex_);

        // Remove all inotify watches
        for (auto& [path, ctx] : watches_) {
            if (ctx->watchDescriptor != -1) {
                inotify_rm_watch(inotifyFd_, ctx->watchDescriptor);
            }
        }

        watches_.clear();
        watchDescriptorMap_.clear();
    }

    // Stop watch thread
    running_ = false;
    if (watchThread_.joinable()) {
        watchThread_.join();
    }

    // Close inotify fd
    if (inotifyFd_ != -1) {
        close(inotifyFd_);
        inotifyFd_ = -1;
    }

    Logger::info("Stopped all watches");
}

bool LinuxFileWatcher::isWatching(const std::string& path) const {
    std::lock_guard<std::mutex> lock(mutex_);
    return watches_.find(path) != watches_.end();
}

void LinuxFileWatcher::setCallback(std::function<void(const FileEvent&)> callback) {
    std::lock_guard<std::mutex> lock(mutex_);
    callback_ = std::move(callback);
}

// ============================================================================
// Private Implementation
// ============================================================================

void LinuxFileWatcher::watchThreadFunc() {
    Logger::debug("Watch thread started");

    const size_t BUF_LEN = (10 * (sizeof(struct inotify_event) + 256));
    char buf[BUF_LEN] __attribute__((aligned(__alignof__(struct inotify_event))));

    while (running_) {
        // Read events from inotify fd
        ssize_t len = read(inotifyFd_, buf, BUF_LEN);

        if (len == -1) {
            if (errno != EAGAIN && errno != EWOULDBLOCK) {
                Logger::error("Failed to read inotify events: {}", strerror(errno));
            }
            // Sleep briefly to avoid busy-waiting
            std::this_thread::sleep_for(std::chrono::milliseconds(100));
            continue;
        }

        // Process events
        for (char* p = buf; p < buf + len;) {
            struct inotify_event* event = (struct inotify_event*)p;

            // Get the path from watch descriptor map
            std::lock_guard<std::mutex> lock(mutex_);
            auto it = watchDescriptorMap_.find(event->wd);
            if (it != watchDescriptorMap_.end()) {
                std::string basePath = it->second;
                std::string fullPath = basePath;
                
                // Append filename if present (subdirectory event)
                if (event->len > 0) {
                    fullPath = fs::path(basePath) / event->name;
                }

                // Skip directory events if flag set
                if (!(event->mask & IN_ISDIR)) {
                    FileAction action = determineInotifyAction(event->mask);

                    // Create file event
                    FileEvent fileEvent;
                    fileEvent.path = fullPath;
                    fileEvent.action = action;
                    fileEvent.size = fs::exists(fullPath) ? fs::file_size(fullPath) : 0;
                    
                    // Convert time_point to ISO8601 string
                    auto now = std::chrono::system_clock::now();
                    auto now_time_t = std::chrono::system_clock::to_time_t(now);
                    std::tm tm = *std::localtime(&now_time_t);
                    char timebuf[32];
                    std::strftime(timebuf, sizeof(timebuf), "%Y-%m-%dT%H:%M:%S", &tm);
                    fileEvent.timestamp = std::string(timebuf);

                    Logger::debug("File event: {} {}", 
                        action == FileAction::CREATED ? "CREATE" :
                        action == FileAction::MODIFIED ? "MODIFY" : "DELETE",
                        fullPath);

                    // Invoke callback
                    if (callback_) {
                        callback_(fileEvent);
                    }
                }
            }

            // Move to next event
            p += sizeof(struct inotify_event) + event->len;
        }
    }

    Logger::debug("Watch thread stopped");
}

void LinuxFileWatcher::processInotifyEvents() {
    // Events are processed in watchThreadFunc
}

FileAction LinuxFileWatcher::determineInotifyAction(uint32_t mask) {
    // Map inotify masks to FileAction
    if (mask & IN_CREATE) {
        return FileAction::CREATED;
    } else if (mask & IN_DELETE || mask & IN_DELETE_SELF) {
        return FileAction::DELETED;
    } else if (mask & (IN_MODIFY | IN_ATTRIB | IN_MOVED_FROM | IN_MOVED_TO)) {
        return FileAction::MODIFIED;
    } else {
        return FileAction::MODIFIED;  // Default
    }
}

} // namespace baludesk
