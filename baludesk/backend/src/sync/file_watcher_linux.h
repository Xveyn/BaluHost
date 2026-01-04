#pragma once

#include "file_watcher_v2.h"
#include <memory>
#include <map>
#include <string>
#include <atomic>
#include <mutex>
#include <thread>

namespace baludesk {

/**
 * @brief Linux FileWatcher implementation using inotify API
 * 
 * Uses Linux inotify subsystem for directory monitoring.
 * Runs watch thread for async event collection.
 * 
 * @note Watches are non-recursive - need manual recursive setup
 * @note Watch descriptor limit: /proc/sys/fs/inotify/max_user_watches
 * @note Event masks: IN_CREATE | IN_DELETE | IN_MODIFY | IN_MOVED_FROM | IN_MOVED_TO
 * @note Requires Linux 2.6.13+
 */
class LinuxFileWatcher : public IFileWatcherImpl {
public:
    LinuxFileWatcher();
    ~LinuxFileWatcher() override;

    // Delete copy/move operations
    LinuxFileWatcher(const LinuxFileWatcher&) = delete;
    LinuxFileWatcher& operator=(const LinuxFileWatcher&) = delete;
    LinuxFileWatcher(LinuxFileWatcher&&) = delete;
    LinuxFileWatcher& operator=(LinuxFileWatcher&&) = delete;

    /**
     * @brief Start watching a directory for changes
     * @param path Absolute path to directory
     * @return true if watch started successfully
     */
    bool startWatch(const std::string& path) override;

    /**
     * @brief Stop watching a specific directory
     * @param path Directory path to stop watching
     */
    void stopWatch(const std::string& path) override;

    /**
     * @brief Stop all watches and clean up resources
     */
    void stopAll() override;

    /**
     * @brief Check if a path is being watched
     * @param path Directory path
     * @return true if path is currently watched
     */
    bool isWatching(const std::string& path) const override;

    /**
     * @brief Set callback for file events
     * @param callback Function to invoke on file changes
     */
    void setCallback(std::function<void(const FileEvent&)> callback) override;

private:
    struct WatchContext {
        std::string path;
        int watchDescriptor = -1;  // inotify watch descriptor
    };

    // Watch thread function
    void watchThreadFunc();

    // Process inotify events
    void processInotifyEvents();

    // Add directory recursively to inotify
    bool addWatchRecursive(const std::string& path);

    // Remove all watches for a path (and its subdirs)
    void removeWatchRecursive(const std::string& path);

    // Determine FileAction from inotify mask
    FileAction determineInotifyAction(uint32_t mask);

    int inotifyFd_ = -1;  // inotify file descriptor
    std::atomic<bool> running_ = false;
    std::thread watchThread_;
    
    mutable std::mutex mutex_;
    std::map<std::string, std::unique_ptr<WatchContext>> watches_;
    std::map<int, std::string> watchDescriptorMap_;  // wd -> path mapping
    std::function<void(const FileEvent&)> callback_;
};

} // namespace baludesk
