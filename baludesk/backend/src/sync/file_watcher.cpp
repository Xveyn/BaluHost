#include "sync/file_watcher.h"
#include "utils/logger.h"
#include <filesystem>
#include <algorithm>

#ifdef _WIN32
#include <windows.h>
#elif __APPLE__
#include <CoreServices/CoreServices.h>
#else
#include <sys/inotify.h>
#include <unistd.h>
#include <poll.h>
#endif

namespace fs = std::filesystem;

namespace baludesk {

// ============================================================================
// Constructor & Destructor
// ============================================================================

FileWatcher::FileWatcher() 
#ifndef _WIN32
#ifndef __APPLE__
    : inotifyFd_(-1), running_(false)
#endif
#endif
{
#if !defined(_WIN32) && !defined(__APPLE__)
    inotifyFd_ = inotify_init();
    if (inotifyFd_ < 0) {
        Logger::error("Failed to initialize inotify");
    }
#endif
    Logger::info("FileWatcher initialized");
}

FileWatcher::~FileWatcher() {
    stop();
    Logger::info("FileWatcher destroyed");
}

// ============================================================================
// Public Interface
// ============================================================================

void FileWatcher::watch(const std::string& path) {
    std::lock_guard<std::mutex> lock(mutex_);
    
    // Check if already watching
    if (watchHandles_.find(path) != watchHandles_.end()) {
        Logger::warn("Already watching: {}", path);
        return;
    }
    
    // Verify path exists
    if (!fs::exists(path)) {
        Logger::error("Path does not exist: {}", path);
        return;
    }
    
    if (!fs::is_directory(path)) {
        Logger::error("Path is not a directory: {}", path);
        return;
    }
    
    Logger::info("Starting watch on: {}", path);
    
    WatchHandle* handle = new WatchHandle();
    
#ifdef _WIN32
    handle->running = true;
    handle->watchThread = std::thread(&FileWatcher::watchDirectoryWindows, this, path, handle);
    watchHandles_[path] = handle;
#elif __APPLE__
    // Setup FSEvents stream
    CFStringRef pathRef = CFStringCreateWithCString(
        NULL, path.c_str(), kCFStringEncodingUTF8
    );
    CFArrayRef pathsToWatch = CFArrayCreate(
        NULL, (const void**)&pathRef, 1, NULL
    );
    
    FSEventStreamContext context = {0, this, NULL, NULL, NULL};
    
    handle->stream = FSEventStreamCreate(
        NULL,
        &FileWatcher::fsEventsCallback,
        &context,
        pathsToWatch,
        kFSEventStreamEventIdSinceNow,
        0.3, // Latency in seconds
        kFSEventStreamCreateFlagFileEvents | kFSEventStreamCreateFlagNoDefer
    );
    
    if (handle->stream) {
        handle->runLoop = CFRunLoopGetCurrent();
        FSEventStreamScheduleWithRunLoop(
            handle->stream, handle->runLoop, kCFRunLoopDefaultMode
        );
        FSEventStreamStart(handle->stream);
        watchHandles_[path] = handle;
        
        Logger::info("macOS FSEvents stream started for: {}", path);
    } else {
        Logger::error("Failed to create FSEvents stream");
        delete handle;
    }
    
    CFRelease(pathsToWatch);
    CFRelease(pathRef);
#else
    // Linux inotify
    if (inotifyFd_ < 0) {
        Logger::error("inotify not initialized");
        delete handle;
        return;
    }
    
    int wd = inotify_add_watch(
        inotifyFd_,
        path.c_str(),
        IN_CREATE | IN_DELETE | IN_MODIFY | IN_MOVED_FROM | IN_MOVED_TO
    );
    
    if (wd < 0) {
        Logger::error("Failed to add inotify watch: {}", path);
        delete handle;
        return;
    }
    
    handle->watchDescriptor = wd;
    watchHandles_[path] = handle;
    
    // Start inotify thread if not running
    if (!running_) {
        running_ = true;
        inotifyThread_ = std::thread(&FileWatcher::watchDirectoryLinux, this);
    }
    
    Logger::info("Linux inotify watch started for: {}", path);
#endif
}

void FileWatcher::unwatch(const std::string& path) {
    std::lock_guard<std::mutex> lock(mutex_);
    
    auto it = watchHandles_.find(path);
    if (it == watchHandles_.end()) {
        Logger::warn("Not watching: {}", path);
        return;
    }
    
    Logger::info("Stopping watch on: {}", path);
    
    WatchHandle* handle = it->second;
    
#ifdef _WIN32
    handle->running = false;
    if (handle->stopEvent) {
        SetEvent(handle->stopEvent);
    }
    if (handle->watchThread.joinable()) {
        handle->watchThread.join();
    }
    if (handle->dirHandle) {
        CloseHandle(handle->dirHandle);
    }
    if (handle->stopEvent) {
        CloseHandle(handle->stopEvent);
    }
#elif __APPLE__
    if (handle->stream) {
        FSEventStreamStop(handle->stream);
        FSEventStreamInvalidate(handle->stream);
        FSEventStreamRelease(handle->stream);
    }
#else
    if (handle->watchDescriptor >= 0) {
        inotify_rm_watch(inotifyFd_, handle->watchDescriptor);
    }
#endif
    
    delete handle;
    watchHandles_.erase(it);
}

void FileWatcher::stop() {
    Logger::info("Stopping all file watchers");
    
    std::lock_guard<std::mutex> lock(mutex_);
    
    // Stop all watchers
    for (auto& pair : watchHandles_) {
        WatchHandle* handle = pair.second;
        
#ifdef _WIN32
        handle->running = false;
        if (handle->stopEvent) {
            SetEvent(handle->stopEvent);
        }
        if (handle->watchThread.joinable()) {
            handle->watchThread.join();
        }
        if (handle->dirHandle) {
            CloseHandle(handle->dirHandle);
        }
        if (handle->stopEvent) {
            CloseHandle(handle->stopEvent);
        }
#elif __APPLE__
        if (handle->stream) {
            FSEventStreamStop(handle->stream);
            FSEventStreamInvalidate(handle->stream);
            FSEventStreamRelease(handle->stream);
        }
#else
        if (handle->watchDescriptor >= 0) {
            inotify_rm_watch(inotifyFd_, handle->watchDescriptor);
        }
#endif
        
        delete handle;
    }
    
    watchHandles_.clear();
    
#if !defined(_WIN32) && !defined(__APPLE__)
    running_ = false;
    if (inotifyThread_.joinable()) {
        inotifyThread_.join();
    }
    if (inotifyFd_ >= 0) {
        close(inotifyFd_);
        inotifyFd_ = -1;
    }
#endif
}

void FileWatcher::setCallback(std::function<void(const FileEvent&)> callback) {
    callback_ = callback;
    Logger::debug("FileWatcher callback set");
}

// ============================================================================
// Windows Implementation
// ============================================================================

#ifdef _WIN32

void FileWatcher::watchDirectoryWindows(const std::string& path, WatchHandle* handle) {
    Logger::info("Starting Windows watch thread for: {}", path);
    
    // Open directory handle
    handle->dirHandle = CreateFileA(
        path.c_str(),
        FILE_LIST_DIRECTORY,
        FILE_SHARE_READ | FILE_SHARE_WRITE | FILE_SHARE_DELETE,
        NULL,
        OPEN_EXISTING,
        FILE_FLAG_BACKUP_SEMANTICS | FILE_FLAG_OVERLAPPED,
        NULL
    );
    
    if (handle->dirHandle == INVALID_HANDLE_VALUE) {
        Logger::error("Failed to open directory: {}, Error: {}", path, GetLastError());
        return;
    }
    
    // Create stop event
    handle->stopEvent = CreateEvent(NULL, TRUE, FALSE, NULL);
    
    // Buffer for change notifications
    const DWORD bufferSize = 64 * 1024; // 64KB buffer
    BYTE buffer[bufferSize];
    OVERLAPPED overlapped = {0};
    overlapped.hEvent = CreateEvent(NULL, TRUE, FALSE, NULL);
    
    DWORD notifyFilter = FILE_NOTIFY_CHANGE_FILE_NAME |
                         FILE_NOTIFY_CHANGE_DIR_NAME |
                         FILE_NOTIFY_CHANGE_LAST_WRITE |
                         FILE_NOTIFY_CHANGE_CREATION;
    
    while (handle->running) {
        DWORD bytesReturned = 0;
        
        // Start async read
        BOOL success = ReadDirectoryChangesW(
            handle->dirHandle,
            buffer,
            bufferSize,
            TRUE, // Watch subdirectories
            notifyFilter,
            &bytesReturned,
            &overlapped,
            NULL
        );
        
        if (!success) {
            Logger::error("ReadDirectoryChangesW failed: {}", GetLastError());
            break;
        }
        
        // Wait for either change notification or stop event
        HANDLE events[2] = {overlapped.hEvent, handle->stopEvent};
        DWORD waitResult = WaitForMultipleObjects(2, events, FALSE, INFINITE);
        
        if (waitResult == WAIT_OBJECT_0) {
            // Change notification received
            if (GetOverlappedResult(handle->dirHandle, &overlapped, &bytesReturned, FALSE)) {
                if (bytesReturned > 0) {
                    processWindowsEvents(path, bytesReturned, (FILE_NOTIFY_INFORMATION*)buffer);
                }
            }
            ResetEvent(overlapped.hEvent);
        } else if (waitResult == WAIT_OBJECT_0 + 1) {
            // Stop event signaled
            Logger::info("Stop event received for: {}", path);
            break;
        } else {
            Logger::error("WaitForMultipleObjects failed: {}", GetLastError());
            break;
        }
    }
    
    CloseHandle(overlapped.hEvent);
    Logger::info("Windows watch thread stopped for: {}", path);
}

void FileWatcher::processWindowsEvents(const std::string& basePath, DWORD bytesReturned, FILE_NOTIFY_INFORMATION* info) {
    (void)bytesReturned;  // Intentionally unused
    while (info) {
        // Convert filename from WCHAR to string using proper Windows API
        std::wstring wfilename(info->FileName, info->FileNameLength / sizeof(WCHAR));
        int sizeNeeded = WideCharToMultiByte(CP_UTF8, 0, wfilename.c_str(), (int)wfilename.length(), nullptr, 0, nullptr, nullptr);
        std::string filename(sizeNeeded, 0);
        WideCharToMultiByte(CP_UTF8, 0, wfilename.c_str(), (int)wfilename.length(), &filename[0], sizeNeeded, nullptr, nullptr);
        
        // Build full path
        std::string fullPath = basePath;
        if (fullPath.back() != '\\' && fullPath.back() != '/') {
            fullPath += '\\';
        }
        fullPath += filename;
        
        // Normalize path separators
        std::replace(fullPath.begin(), fullPath.end(), '\\', '/');
        
        // Determine action
        FileAction action;
        switch (info->Action) {
            case FILE_ACTION_ADDED:
                action = FileAction::CREATED;
                Logger::debug("File created: {}", fullPath);
                break;
            case FILE_ACTION_REMOVED:
                action = FileAction::DELETED;
                Logger::debug("File deleted: {}", fullPath);
                break;
            case FILE_ACTION_MODIFIED:
                action = FileAction::MODIFIED;
                Logger::debug("File modified: {}", fullPath);
                break;
            case FILE_ACTION_RENAMED_OLD_NAME:
                // Treat as deletion
                action = FileAction::DELETED;
                Logger::debug("File renamed (old): {}", fullPath);
                break;
            case FILE_ACTION_RENAMED_NEW_NAME:
                // Treat as creation
                action = FileAction::CREATED;
                Logger::debug("File renamed (new): {}", fullPath);
                break;
            default:
                action = FileAction::MODIFIED;
                break;
        }
        
        // Check debouncing
        if (!shouldDebounce(fullPath, action)) {
            // Create and notify event
            FileEvent event;
            event.path = fullPath;
            event.action = action;
            
            // Get file size if it exists
            try {
                if (fs::exists(fullPath) && fs::is_regular_file(fullPath)) {
                    event.size = fs::file_size(fullPath);
                } else {
                    event.size = 0;
                }
            } catch (const std::exception& e) {
                (void)e;  // Intentionally unused
                event.size = 0;
            }
            
            // Get timestamp
            auto now = std::chrono::system_clock::now();
            auto timestamp = std::chrono::system_clock::to_time_t(now);
            event.timestamp = std::to_string(timestamp);
            
            notifyEvent(event);
            updateDebounceEntry(fullPath, action);
        }
        
        // Move to next notification
        if (info->NextEntryOffset == 0) {
            break;
        }
        info = (FILE_NOTIFY_INFORMATION*)((BYTE*)info + info->NextEntryOffset);
    }
}

#endif // _WIN32

// ============================================================================
// macOS Implementation
// ============================================================================

#ifdef __APPLE__

void FileWatcher::fsEventsCallback(
    ConstFSEventStreamRef streamRef,
    void* clientCallBackInfo,
    size_t numEvents,
    void* eventPaths,
    const FSEventStreamEventFlags eventFlags[],
    const FSEventStreamEventId eventIds[]
) {
    FileWatcher* watcher = static_cast<FileWatcher*>(clientCallBackInfo);
    char** paths = (char**)eventPaths;
    
    for (size_t i = 0; i < numEvents; i++) {
        std::string path = paths[i];
        FSEventStreamEventFlags flags = eventFlags[i];
        
        FileAction action;
        
        if (flags & kFSEventStreamEventFlagItemCreated) {
            action = FileAction::CREATED;
            Logger::debug("File created (macOS): {}", path);
        } else if (flags & kFSEventStreamEventFlagItemRemoved) {
            action = FileAction::DELETED;
            Logger::debug("File deleted (macOS): {}", path);
        } else if (flags & kFSEventStreamEventFlagItemModified) {
            action = FileAction::MODIFIED;
            Logger::debug("File modified (macOS): {}", path);
        } else if (flags & kFSEventStreamEventFlagItemRenamed) {
            // Treat rename as create for new name
            action = FileAction::CREATED;
            Logger::debug("File renamed (macOS): {}", path);
        } else {
            continue; // Skip unknown events
        }
        
        if (!watcher->shouldDebounce(path, action)) {
            FileEvent event;
            event.path = path;
            event.action = action;
            
            try {
                if (fs::exists(path) && fs::is_regular_file(path)) {
                    event.size = fs::file_size(path);
                } else {
                    event.size = 0;
                }
            } catch (const std::exception& e) {
                event.size = 0;
            }
            
            auto now = std::chrono::system_clock::now();
            auto timestamp = std::chrono::system_clock::to_time_t(now);
            event.timestamp = std::to_string(timestamp);
            
            watcher->notifyEvent(event);
            watcher->updateDebounceEntry(path, action);
        }
    }
}

#endif // __APPLE__

// ============================================================================
// Linux Implementation
// ============================================================================

#if !defined(_WIN32) && !defined(__APPLE__)

void FileWatcher::watchDirectoryLinux() {
    Logger::info("Starting Linux inotify watch thread");
    
    const size_t bufferSize = 4096;
    char buffer[bufferSize];
    
    struct pollfd pfd;
    pfd.fd = inotifyFd_;
    pfd.events = POLLIN;
    
    while (running_) {
        int ret = poll(&pfd, 1, 1000); // 1 second timeout
        
        if (ret < 0) {
            Logger::error("poll() failed: {}", strerror(errno));
            break;
        }
        
        if (ret == 0) {
            // Timeout, continue
            continue;
        }
        
        if (pfd.revents & POLLIN) {
            ssize_t length = read(inotifyFd_, buffer, bufferSize);
            
            if (length < 0) {
                Logger::error("read() failed: {}", strerror(errno));
                break;
            }
            
            size_t offset = 0;
            while (offset < length) {
                struct inotify_event* event = (struct inotify_event*)(buffer + offset);
                
                if (event->len > 0) {
                    // Find the path for this watch descriptor
                    std::string basePath;
                    {
                        std::lock_guard<std::mutex> lock(mutex_);
                        for (const auto& pair : watchHandles_) {
                            if (pair.second->watchDescriptor == event->wd) {
                                basePath = pair.first;
                                break;
                            }
                        }
                    }
                    
                    if (!basePath.empty()) {
                        std::string fullPath = basePath;
                        if (fullPath.back() != '/') {
                            fullPath += '/';
                        }
                        fullPath += event->name;
                        
                        FileAction action;
                        
                        if (event->mask & IN_CREATE) {
                            action = FileAction::CREATED;
                            Logger::debug("File created (Linux): {}", fullPath);
                        } else if (event->mask & IN_DELETE) {
                            action = FileAction::DELETED;
                            Logger::debug("File deleted (Linux): {}", fullPath);
                        } else if (event->mask & IN_MODIFY) {
                            action = FileAction::MODIFIED;
                            Logger::debug("File modified (Linux): {}", fullPath);
                        } else if (event->mask & IN_MOVED_FROM) {
                            action = FileAction::DELETED;
                            Logger::debug("File moved from (Linux): {}", fullPath);
                        } else if (event->mask & IN_MOVED_TO) {
                            action = FileAction::CREATED;
                            Logger::debug("File moved to (Linux): {}", fullPath);
                        } else {
                            offset += sizeof(struct inotify_event) + event->len;
                            continue;
                        }
                        
                        if (!shouldDebounce(fullPath, action)) {
                            FileEvent fileEvent;
                            fileEvent.path = fullPath;
                            fileEvent.action = action;
                            
                            try {
                                if (fs::exists(fullPath) && fs::is_regular_file(fullPath)) {
                                    fileEvent.size = fs::file_size(fullPath);
                                } else {
                                    fileEvent.size = 0;
                                }
                            } catch (const std::exception& e) {
                                fileEvent.size = 0;
                            }
                            
                            auto now = std::chrono::system_clock::now();
                            auto timestamp = std::chrono::system_clock::to_time_t(now);
                            fileEvent.timestamp = std::to_string(timestamp);
                            
                            notifyEvent(fileEvent);
                            updateDebounceEntry(fullPath, action);
                        }
                    }
                }
                
                offset += sizeof(struct inotify_event) + event->len;
            }
        }
    }
    
    Logger::info("Linux inotify watch thread stopped");
}

#endif // Linux

// ============================================================================
// Event Processing
// ============================================================================

void FileWatcher::notifyEvent(const FileEvent& event) {
    if (callback_) {
        try {
            callback_(event);
        } catch (const std::exception& e) {
            Logger::error("Error in file event callback: {}", e.what());
        }
    }
}

bool FileWatcher::shouldDebounce(const std::string& path, FileAction action) {
    std::lock_guard<std::mutex> lock(mutex_);
    
    auto it = debounceMap_.find(path);
    if (it == debounceMap_.end()) {
        return false; // No previous event, don't debounce
    }
    
    auto now = std::chrono::steady_clock::now();
    auto elapsed = std::chrono::duration_cast<std::chrono::milliseconds>(
        now - it->second.lastEvent
    );
    
    // Debounce if same action within debounce delay
    if (elapsed < debounceDelay_ && it->second.lastAction == action) {
        Logger::trace("Debouncing event for: {}", path);
        return true;
    }
    
    return false;
}

void FileWatcher::updateDebounceEntry(const std::string& path, FileAction action) {
    std::lock_guard<std::mutex> lock(mutex_);
    
    DebounceEntry entry;
    entry.lastEvent = std::chrono::steady_clock::now();
    entry.lastAction = action;
    
    debounceMap_[path] = entry;
}

} // namespace baludesk
