#pragma once

#include <string>
#include <memory>
#include <functional>
#include <vector>
#include <queue>
#include <mutex>
#include <atomic>
#include <thread>
#include <chrono>
#include "change_detector.h"  // For DetectedChange, ConflictInfo

namespace baludesk {

// Forward declarations
class FileWatcher;
class HttpClient;
class Database;
class ConflictResolver;
class ChangeDetector;

// Sync status enumeration
enum class SyncStatus {
    IDLE,
    SYNCING,
    PAUSED,
    SYNC_ERROR
};

// File change action
enum class FileAction {
    CREATED,
    MODIFIED,
    DELETED
};

// File event structure
struct FileEvent {
    std::string path;
    FileAction action;
    uint64_t size;
    std::string timestamp;
};

// Sync folder configuration
struct SyncFolder {
    std::string id;
    std::string localPath;
    std::string remotePath;
    SyncStatus status;
    bool enabled;
    std::string createdAt;
    std::string lastSync;
};

// Sync statistics
struct SyncStats {
    SyncStatus status;
    uint64_t uploadSpeed;      // bytes/sec
    uint64_t downloadSpeed;
    uint32_t pendingUploads;
    uint32_t pendingDownloads;
    std::string lastSync;
};

/**
 * SyncEngine - Core synchronization engine
 * 
 * Responsibilities:
 * - Manage sync folders
 * - Coordinate file watching, change detection, and sync operations
 * - Handle conflicts
 * - Provide sync status updates
 */
class SyncEngine {
public:
    SyncEngine();
    ~SyncEngine();

    // Lifecycle
    bool initialize(const std::string& dbPath, const std::string& serverUrl);
    void start();
    void stop();
    bool isRunning() const;

    // Authentication
    bool login(const std::string& username, const std::string& password);
    void logout();
    bool isAuthenticated() const;

    // Sync folder management
    bool addSyncFolder(SyncFolder& folder);  // Modified to set folder.id
    bool removeSyncFolder(const std::string& folderId);
    bool pauseSync(const std::string& folderId);
    bool resumeSync(const std::string& folderId);
    std::vector<SyncFolder> getSyncFolders() const;

    // Sync operations & state
    void triggerSync(const std::string& folderId = "");
    void triggerBidirectionalSync(const std::string& folderId = "");  // Sprint 3 - Active
    SyncStats getSyncState() const;

    // Callbacks for status updates
    using StatusCallback = std::function<void(const SyncStats&)>;
    using FileChangeCallback = std::function<void(const FileEvent&)>;
    using ErrorCallback = std::function<void(const std::string&)>;

    void setStatusCallback(StatusCallback callback);
    void setFileChangeCallback(FileChangeCallback callback);
    void setErrorCallback(ErrorCallback callback);

private:
    // Internal sync loop
    void syncLoop();
    void processFileEvent(const FileEvent& event);
    void scanLocalChanges(const SyncFolder& folder);
    void fetchRemoteChanges(const SyncFolder& folder);
    void uploadFile(const std::string& localPath, const std::string& remotePath);
    void downloadFile(const std::string& remotePath, const std::string& localPath);
    void handleConflict(const std::string& path);
    
    // Sprint 3 methods - Active
    void syncBidirectional(const SyncFolder& folder);
    void handleRemoteChange(const DetectedChange& change, const SyncFolder& folder);
    void handleLocalChange(const DetectedChange& change, const SyncFolder& folder);
    void resolveConflict(const ConflictInfo& conflict, const SyncFolder& folder);

    // Update stats
    void updateStats();
    void notifyStatusChange();

    // Components
    std::unique_ptr<FileWatcher> fileWatcher_;
    std::unique_ptr<HttpClient> httpClient_;
    std::unique_ptr<Database> database_;
    std::unique_ptr<ConflictResolver> conflictResolver_;
    std::unique_ptr<ChangeDetector> changeDetector_;

    // State
    std::atomic<bool> running_{false};
    std::atomic<bool> authenticated_{false};
    std::thread syncThread_;
    std::mutex mutex_;

    // Event queue
    std::queue<FileEvent> eventQueue_;
    std::mutex queueMutex_;

    // Callbacks
    StatusCallback statusCallback_;
    FileChangeCallback fileChangeCallback_;
    ErrorCallback errorCallback_;

    // Stats
    SyncStats stats_;
    std::mutex statsMutex_;
};

} // namespace baludesk
