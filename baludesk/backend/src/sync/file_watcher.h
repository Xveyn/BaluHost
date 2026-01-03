#pragma once

#include "sync_engine.h"
#include <string>
#include <functional>
#include <map>
#include <thread>
#include <atomic>
#include <mutex>
#include <chrono>

#ifdef _WIN32
#include <windows.h>
#elif __APPLE__
#include <CoreServices/CoreServices.h>
#else
#include <sys/inotify.h>
#endif

namespace baludesk {

// Debounce entry for file events
struct DebounceEntry {
    std::chrono::steady_clock::time_point lastEvent;
    FileAction lastAction;
};

// Platform-specific watch handle
struct WatchHandle {
#ifdef _WIN32
    HANDLE dirHandle;
    HANDLE stopEvent;
    std::thread watchThread;
    std::atomic<bool> running;
#elif __APPLE__
    FSEventStreamRef stream;
    CFRunLoopRef runLoop;
#else
    int watchDescriptor;
#endif
};

class FileWatcher {
public:
    FileWatcher();
    ~FileWatcher();

    // Watch a directory for changes
    void watch(const std::string& path);
    
    // Stop watching a directory
    void unwatch(const std::string& path);
    
    // Stop all watchers
    void stop();
    
    // Set callback for file events
    void setCallback(std::function<void(const FileEvent&)> callback);

private:
    // Platform-specific implementations
#ifdef _WIN32
    void watchDirectoryWindows(const std::string& path, WatchHandle* handle);
    void processWindowsEvents(const std::string& basePath, DWORD bytesReturned, FILE_NOTIFY_INFORMATION* info);
#elif __APPLE__
    static void fsEventsCallback(
        ConstFSEventStreamRef streamRef,
        void* clientCallBackInfo,
        size_t numEvents,
        void* eventPaths,
        const FSEventStreamEventFlags eventFlags[],
        const FSEventStreamEventId eventIds[]
    );
#else
    void watchDirectoryLinux();
    void processInotifyEvents();
    std::thread inotifyThread_;
    int inotifyFd_;
    std::atomic<bool> running_;
#endif

    // Event processing
    void notifyEvent(const FileEvent& event);
    bool shouldDebounce(const std::string& path, FileAction action);
    void updateDebounceEntry(const std::string& path, FileAction action);

    // State
    std::map<std::string, WatchHandle*> watchHandles_;
    std::map<std::string, DebounceEntry> debounceMap_;
    std::function<void(const FileEvent&)> callback_;
    std::mutex mutex_;
    std::chrono::milliseconds debounceDelay_{500}; // 500ms debounce
};

} // namespace baludesk
