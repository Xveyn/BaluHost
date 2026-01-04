#pragma once

#include "sync_engine.h"
#include <string>
#include <functional>
#include <memory>
#include <chrono>
#include <map>

namespace baludesk {

/**
 * @brief Abstract base class for platform-specific file watchers
 * 
 * This interface follows the Strategy Pattern for platform-specific implementations:
 * - Windows: ReadDirectoryChangesW
 * - macOS: FSEvents API
 * - Linux: inotify
 */
class IFileWatcherImpl {
public:
    virtual ~IFileWatcherImpl() = default;

    /**
     * @brief Start watching a directory
     * @param path Absolute path to directory
     * @return true if watch started successfully
     */
    virtual bool startWatch(const std::string& path) = 0;

    /**
     * @brief Stop watching a directory
     * @param path Absolute path to directory
     */
    virtual void stopWatch(const std::string& path) = 0;

    /**
     * @brief Stop all watches
     */
    virtual void stopAll() = 0;

    /**
     * @brief Check if path is being watched
     */
    virtual bool isWatching(const std::string& path) const = 0;

    /**
     * @brief Set event callback
     */
    virtual void setCallback(std::function<void(const FileEvent&)> callback) = 0;
};

/**
 * @brief Main FileWatcher facade with debouncing
 * 
 * This class provides:
 * - Platform-independent API
 * - Event debouncing (prevents duplicate events)
 * - Thread-safe operation
 * - RAII resource management
 */
class FileWatcher {
public:
    FileWatcher();
    ~FileWatcher();

    // Delete copy/move (follows Rule of Five)
    FileWatcher(const FileWatcher&) = delete;
    FileWatcher& operator=(const FileWatcher&) = delete;
    FileWatcher(FileWatcher&&) = delete;
    FileWatcher& operator=(FileWatcher&&) = delete;

    /**
     * @brief Watch a directory for changes
     * @param path Absolute path to directory
     * @return true if watch started successfully
     */
    bool watch(const std::string& path);

    /**
     * @brief Stop watching a directory
     * @param path Absolute path to directory
     */
    void unwatch(const std::string& path);

    /**
     * @brief Stop all watchers
     */
    void stop();

    /**
     * @brief Set callback for file events
     * @param callback Function to call on file changes
     */
    void setCallback(std::function<void(const FileEvent&)> callback);

    /**
     * @brief Set debounce delay (default: 500ms)
     * @param delayMs Delay in milliseconds
     */
    void setDebounceDelay(int delayMs);

    /**
     * @brief Check if path is being watched
     */
    bool isWatching(const std::string& path) const;

private:
    struct DebounceEntry {
        std::chrono::steady_clock::time_point lastEvent;
        FileAction lastAction;
    };

    /**
     * @brief Internal callback with debouncing
     */
    void onFileEvent(const FileEvent& event);

    /**
     * @brief Check if event should be debounced
     */
    bool shouldDebounce(const std::string& path, FileAction action);

    /**
     * @brief Update debounce map
     */
    void updateDebounceEntry(const std::string& path, FileAction action);

    // Platform-specific implementation (Pimpl pattern)
    std::unique_ptr<IFileWatcherImpl> impl_;

    // Debouncing state
    std::map<std::string, DebounceEntry> debounceMap_;
    std::chrono::milliseconds debounceDelay_{500};
    mutable std::mutex mutex_;

    // User callback
    std::function<void(const FileEvent&)> userCallback_;
};

/**
 * @brief Factory function to create platform-specific watcher
 */
std::unique_ptr<IFileWatcherImpl> createPlatformFileWatcher();

} // namespace baludesk
