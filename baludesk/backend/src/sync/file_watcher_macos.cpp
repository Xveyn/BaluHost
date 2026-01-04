#include "file_watcher_macos.h"
#include "utils/logger.h"
#include <filesystem>
#include <vector>
#include <dispatch/dispatch.h>

namespace fs = std::filesystem;

namespace baludesk {

MacOSFileWatcher::MacOSFileWatcher() {
    mainQueue_ = dispatch_get_main_queue();
    Logger::info("macOS FileWatcher initialized");
}

MacOSFileWatcher::~MacOSFileWatcher() {
    stopAll();
    Logger::info("macOS FileWatcher destroyed");
}

bool MacOSFileWatcher::startWatch(const std::string& path) {
    std::lock_guard<std::mutex> lock(mutex_);

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

    // Create dispatch queue for this watch
    ctx->queue = dispatch_queue_create(
        ("com.baludesk.filewatcher." + path).c_str(),
        DISPATCH_QUEUE_SERIAL
    );

    if (!ctx->queue) {
        Logger::error("Failed to create dispatch queue for: {}", path);
        return false;
    }

    // Convert path to CFString
    CFStringRef pathCF = CFStringCreateWithCString(
        kCFAllocatorDefault,
        path.c_str(),
        kCFStringEncodingUTF8
    );

    if (!pathCF) {
        Logger::error("Failed to create CFString for path: {}", path);
        dispatch_release(ctx->queue);
        return false;
    }

    // Create array of paths to watch
    CFArrayRef pathsToWatch = CFArrayCreate(
        kCFAllocatorDefault,
        (const void**)&pathCF,
        1,
        &kCFTypeArrayCallBacks
    );
    CFRelease(pathCF);

    if (!pathsToWatch) {
        Logger::error("Failed to create paths array");
        dispatch_release(ctx->queue);
        return false;
    }

    // Create FSEventStream
    // Use kFSEventStreamCreateFlagFileEvents for file-level events
    // Use 0 for default behavior (coalesced directory events)
    FSEventStreamContext fseContext = {0, this, nullptr, nullptr, nullptr};
    
    ctx->stream = FSEventStreamCreate(
        kCFAllocatorDefault,
        &MacOSFileWatcher::fsEventsCallback,
        &fseContext,
        pathsToWatch,
        kFSEventStreamEventIdSinceNow,  // Start from now
        0.5,  // Latency in seconds (debouncing)
        kFSEventStreamCreateFlagFileEvents  // Report file-level events
    );
    CFRelease(pathsToWatch);

    if (!ctx->stream) {
        Logger::error("Failed to create FSEventStream for: {}", path);
        dispatch_release(ctx->queue);
        return false;
    }

    // Schedule stream on the dispatch queue
    FSEventStreamSetDispatchQueue(ctx->stream, ctx->queue);

    // Start the stream
    if (!FSEventStreamStart(ctx->stream)) {
        Logger::error("Failed to start FSEventStream for: {}", path);
        FSEventStreamInvalidate(ctx->stream);
        FSEventStreamRelease(ctx->stream);
        dispatch_release(ctx->queue);
        return false;
    }

    watches_[path] = std::move(ctx);
    Logger::info("Started watching: {}", path);
    return true;
}

void MacOSFileWatcher::stopWatch(const std::string& path) {
    std::lock_guard<std::mutex> lock(mutex_);

    auto it = watches_.find(path);
    if (it == watches_.end()) {
        return;
    }

    auto& ctx = it->second;

    // Stop and release the stream
    if (ctx->stream) {
        FSEventStreamStop(ctx->stream);
        FSEventStreamInvalidate(ctx->stream);
        FSEventStreamRelease(ctx->stream);
        ctx->stream = nullptr;
    }

    // Release the queue
    if (ctx->queue) {
        dispatch_release(ctx->queue);
        ctx->queue = nullptr;
    }

    watches_.erase(it);
    Logger::info("Stopped watching: {}", path);
}

void MacOSFileWatcher::stopAll() {
    std::lock_guard<std::mutex> lock(mutex_);

    for (auto it = watches_.begin(); it != watches_.end(); ++it) {
        auto& ctx = it->second;

        if (ctx->stream) {
            FSEventStreamStop(ctx->stream);
            FSEventStreamInvalidate(ctx->stream);
            FSEventStreamRelease(ctx->stream);
        }

        if (ctx->queue) {
            dispatch_release(ctx->queue);
        }
    }

    watches_.clear();
    Logger::info("Stopped all watches");
}

bool MacOSFileWatcher::isWatching(const std::string& path) const {
    std::lock_guard<std::mutex> lock(mutex_);
    return watches_.find(path) != watches_.end();
}

void MacOSFileWatcher::setCallback(std::function<void(const FileEvent&)> callback) {
    std::lock_guard<std::mutex> lock(mutex_);
    callback_ = std::move(callback);
}

// ============================================================================
// Private Implementation
// ============================================================================

void MacOSFileWatcher::fsEventsCallback(
    ConstFSEventStreamRef streamRef,
    void* clientCallbackInfo,
    size_t numEvents,
    void* eventPaths,
    const FSEventStreamEventFlags eventFlags[],
    const FSEventStreamEventId eventIds[]
) {
    // Recover the MacOSFileWatcher instance
    MacOSFileWatcher* self = static_cast<MacOSFileWatcher*>(clientCallbackInfo);
    
    // Convert FSEvents data to C++ vectors
    char** paths = static_cast<char**>(eventPaths);
    std::vector<std::string> pathVec;
    std::vector<FSEventStreamEventFlags> flagVec;
    
    for (size_t i = 0; i < numEvents; i++) {
        pathVec.push_back(std::string(paths[i]));
        flagVec.push_back(eventFlags[i]);
    }

    // Process events on the main thread to avoid race conditions
    dispatch_async(dispatch_get_main_queue(), ^{
        self->processFSEvents(pathVec, flagVec);
    });
}

void MacOSFileWatcher::processFSEvents(
    const std::vector<std::string>& paths,
    const std::vector<FSEventStreamEventFlags>& flags
) {
    std::lock_guard<std::mutex> lock(mutex_);

    if (!callback_) {
        return;
    }

    for (size_t i = 0; i < paths.size(); i++) {
        const std::string& eventPath = paths[i];
        FSEventStreamEventFlags eventFlags = flags[i];

        // Filter out events we're not interested in
        if (eventFlags & kFSEventStreamEventFlagItemIsDir) {
            // Optionally skip directories for now
            continue;
        }

        FileAction action = determineFSEventAction(eventFlags);

        // Create file event
        FileEvent event;
        event.path = eventPath;
        event.action = action;
        event.size = fs::exists(eventPath) ? fs::file_size(eventPath) : 0;
        
        // Convert time_point to ISO8601 string
        auto now = std::chrono::system_clock::now();
        auto now_time_t = std::chrono::system_clock::to_time_t(now);
        std::tm tm = *std::localtime(&now_time_t);
        char buffer[32];
        std::strftime(buffer, sizeof(buffer), "%Y-%m-%dT%H:%M:%S", &tm);
        event.timestamp = std::string(buffer);

        Logger::debug("File event: {} {}", 
            action == FileAction::CREATED ? "CREATE" :
            action == FileAction::MODIFIED ? "MODIFY" : "DELETE",
            eventPath);

        // Invoke callback
        callback_(event);
    }
}

FileAction MacOSFileWatcher::determineFSEventAction(FSEventStreamEventFlags flags) {
    // FSEvents flags mapping:
    // - ItemCreated: file/dir was created
    // - ItemRemoved: file/dir was deleted
    // - ItemModified: file/dir was modified (contents, metadata, etc.)
    
    if (flags & kFSEventStreamEventFlagItemCreated) {
        return FileAction::CREATED;
    } else if (flags & kFSEventStreamEventFlagItemRemoved) {
        return FileAction::DELETED;
    } else {
        // Default to MODIFIED for any other changes
        return FileAction::MODIFIED;
    }
}

} // namespace baludesk
