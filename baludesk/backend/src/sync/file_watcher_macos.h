#pragma once

#include "file_watcher_v2.h"
#include <CoreServices/CoreServices.h>
#include <memory>
#include <map>
#include <string>
#include <atomic>
#include <mutex>

namespace baludesk {

/**
 * @brief macOS FileWatcher implementation using FSEvents API
 * 
 * Uses Core Foundation's FSEvents to monitor directory changes.
 * Runs event stream on a dispatch queue for non-blocking operation.
 * 
 * @note FSEvents is recursive by default - no need to manually recurse
 * @note Events are coalesced to reduce event volume
 * @note Requires macOS 10.7+
 */
class MacOSFileWatcher : public IFileWatcherImpl {
public:
    MacOSFileWatcher();
    ~MacOSFileWatcher() override;

    // Delete copy/move operations
    MacOSFileWatcher(const MacOSFileWatcher&) = delete;
    MacOSFileWatcher& operator=(const MacOSFileWatcher&) = delete;
    MacOSFileWatcher(MacOSFileWatcher&&) = delete;
    MacOSFileWatcher& operator=(MacOSFileWatcher&&) = delete;

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
        FSEventStreamRef stream = nullptr;
        dispatch_queue_t queue = nullptr;
    };

    // Callback invoked by FSEvents
    static void fsEventsCallback(
        ConstFSEventStreamRef streamRef,
        void* clientCallbackInfo,
        size_t numEvents,
        void* eventPaths,
        const FSEventStreamEventFlags eventFlags[],
        const FSEventStreamEventId eventIds[]
    );

    // Process FSEvents and convert to FileEvent
    void processFSEvents(
        const std::vector<std::string>& paths,
        const std::vector<FSEventStreamEventFlags>& flags
    );

    // Determine FileAction from FSEvent flags
    FileAction determineFSEventAction(FSEventStreamEventFlags flags);

    mutable std::mutex mutex_;
    std::map<std::string, std::unique_ptr<WatchContext>> watches_;
    std::function<void(const FileEvent&)> callback_;
    dispatch_queue_t mainQueue_;
};

} // namespace baludesk
