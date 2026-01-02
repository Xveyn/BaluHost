#include "sync/sync_engine.h"
#include "sync/file_watcher.h"
#include "api/http_client.h"
#include "db/database.h"
#include "sync/conflict_resolver.h"
#include "sync/change_detector.h"
#include "utils/logger.h"
#include <chrono>
#include <thread>

namespace baludesk {

SyncEngine::SyncEngine() {
    stats_.status = SyncStatus::IDLE;
    stats_.uploadSpeed = 0;
    stats_.downloadSpeed = 0;
    stats_.pendingUploads = 0;
    stats_.pendingDownloads = 0;
}

SyncEngine::~SyncEngine() {
    stop();
}

bool SyncEngine::initialize(const std::string& dbPath, const std::string& serverUrl) {
    try {
        Logger::info("Initializing SyncEngine...");
        
        // Initialize database
        database_ = std::make_unique<Database>(dbPath);
        if (!database_->initialize()) {
            Logger::error("Failed to initialize database");
            return false;
        }

        // Initialize HTTP client
        httpClient_ = std::make_unique<HttpClient>(serverUrl);

        // Initialize other components
        fileWatcher_ = std::make_unique<FileWatcher>();
        conflictResolver_ = std::make_unique<ConflictResolver>();
        changeDetector_ = std::make_unique<ChangeDetector>(database_.get());

        // Set file watcher callback
        fileWatcher_->setCallback([this](const FileEvent& event) {
            std::lock_guard<std::mutex> lock(queueMutex_);
            eventQueue_.push(event);
        });

        Logger::info("SyncEngine initialized successfully");
        return true;
    } catch (const std::exception& e) {
        Logger::error("Failed to initialize SyncEngine: " + std::string(e.what()));
        return false;
    }
}

void SyncEngine::start() {
    if (running_) {
        Logger::warn("SyncEngine already running");
        return;
    }

    Logger::info("Starting SyncEngine...");
    running_ = true;
    stats_.status = SyncStatus::IDLE;

    // Start sync loop in separate thread
    syncThread_ = std::thread([this]() {
        syncLoop();
    });

    // Start file watchers for all enabled folders
    auto folders = getSyncFolders();
    for (const auto& folder : folders) {
        if (folder.enabled && folder.status != SyncStatus::PAUSED) {
            fileWatcher_->watch(folder.localPath);
        }
    }

    notifyStatusChange();
}

void SyncEngine::stop() {
    if (!running_) {
        return;
    }

    Logger::info("Stopping SyncEngine...");
    running_ = false;

    // Stop file watcher
    if (fileWatcher_) {
        fileWatcher_->stop();
    }

    // Wait for sync thread
    if (syncThread_.joinable()) {
        syncThread_.join();
    }

    stats_.status = SyncStatus::IDLE;
    notifyStatusChange();
}

bool SyncEngine::isRunning() const {
    return running_;
}

bool SyncEngine::login(const std::string& username, const std::string& password) {
    Logger::info("Attempting login for user: " + username);
    
    if (!httpClient_) {
        Logger::error("HTTP client not initialized");
        return false;
    }

    if (httpClient_->login(username, password)) {
        authenticated_ = true;
        Logger::info("Login successful");
        return true;
    }

    authenticated_ = false;
    Logger::error("Login failed");
    return false;
}

void SyncEngine::logout() {
    authenticated_ = false;
    if (httpClient_) {
        httpClient_->clearAuthToken();
    }
    Logger::info("Logged out");
}

bool SyncEngine::isAuthenticated() const {
    return authenticated_;
}

std::string SyncEngine::addSyncFolder(const std::string& localPath, const std::string& remotePath) {
    Logger::info("Adding sync folder: " + localPath + " -> " + remotePath);
    
    SyncFolder folder;
    folder.id = database_->generateId();
    folder.localPath = localPath;
    folder.remotePath = remotePath;
    folder.status = SyncStatus::IDLE;
    folder.enabled = true;
    folder.createdAt = std::to_string(std::time(nullptr));

    if (database_->addSyncFolder(folder)) {
        // Start watching this folder
        if (running_) {
            fileWatcher_->watch(localPath);
        }
        
        // Trigger initial sync
        triggerSync(folder.id);
        
        return folder.id;
    }

    return "";
}

bool SyncEngine::removeSyncFolder(const std::string& folderId) {
    Logger::info("Removing sync folder: " + folderId);
    
    auto folder = database_->getSyncFolder(folderId);
    if (!folder.id.empty()) {
        fileWatcher_->unwatch(folder.localPath);
        return database_->removeSyncFolder(folderId);
    }
    
    return false;
}

bool SyncEngine::pauseSyncFolder(const std::string& folderId) {
    auto folder = database_->getSyncFolder(folderId);
    if (!folder.id.empty()) {
        folder.status = SyncStatus::PAUSED;
        fileWatcher_->unwatch(folder.localPath);
        return database_->updateSyncFolder(folder);
    }
    return false;
}

bool SyncEngine::resumeSyncFolder(const std::string& folderId) {
    auto folder = database_->getSyncFolder(folderId);
    if (!folder.id.empty()) {
        folder.status = SyncStatus::IDLE;
        fileWatcher_->watch(folder.localPath);
        triggerSync(folderId);
        return database_->updateSyncFolder(folder);
    }
    return false;
}

std::vector<SyncFolder> SyncEngine::getSyncFolders() const {
    return database_->getSyncFolders();
}

void SyncEngine::triggerSync(const std::string& folderId) {
    Logger::info("Triggering sync" + (folderId.empty() ? "" : " for folder: " + folderId));
    
    // Implementation will scan for changes and sync
    // This is a simplified version - full implementation in next iteration
}

SyncStats SyncEngine::getStats() const {
    std::lock_guard<std::mutex> lock(statsMutex_);
    return stats_;
}

void SyncEngine::setStatusCallback(StatusCallback callback) {
    statusCallback_ = callback;
}

void SyncEngine::setFileChangeCallback(FileChangeCallback callback) {
    fileChangeCallback_ = callback;
}

void SyncEngine::setErrorCallback(ErrorCallback callback) {
    errorCallback_ = callback;
}

void SyncEngine::syncLoop() {
    Logger::info("Sync loop started");
    
    while (running_) {
        try {
            // Process file events from queue
            {
                std::lock_guard<std::mutex> lock(queueMutex_);
                while (!eventQueue_.empty()) {
                    auto event = eventQueue_.front();
                    eventQueue_.pop();
                    processFileEvent(event);
                }
            }

            // Periodic sync check (every 30 seconds)
            auto folders = getSyncFolders();
            for (const auto& folder : folders) {
                if (folder.enabled && folder.status != SyncStatus::PAUSED) {
                    fetchRemoteChanges(folder);
                }
            }

            updateStats();
            
        } catch (const std::exception& e) {
            Logger::error("Error in sync loop: " + std::string(e.what()));
            if (errorCallback_) {
                errorCallback_(e.what());
            }
        }

        // Sleep for a bit
        std::this_thread::sleep_for(std::chrono::seconds(30));
    }
    
    Logger::info("Sync loop stopped");
}

void SyncEngine::processFileEvent(const FileEvent& event) {
    Logger::debug("Processing file event: " + event.path);
    
    // Find which folder this belongs to
    auto folders = getSyncFolders();
    for (const auto& folder : folders) {
        if (event.path.find(folder.localPath) == 0) {
            // File belongs to this sync folder
            std::string relativePath = event.path.substr(folder.localPath.length());
            std::string remotePath = folder.remotePath + relativePath;
            
            switch (event.action) {
                case FileAction::CREATED:
                case FileAction::MODIFIED:
                    uploadFile(event.path, remotePath);
                    break;
                case FileAction::DELETED:
                    // Handle deletion
                    break;
            }
            
            if (fileChangeCallback_) {
                fileChangeCallback_(event);
            }
            break;
        }
    }
}

void SyncEngine::scanLocalChanges(const SyncFolder& folder) {
    // TODO: Implement local change scanning
    Logger::debug("Scanning local changes for: " + folder.localPath);
}

void SyncEngine::fetchRemoteChanges(const SyncFolder& folder) {
    // TODO: Implement remote change fetching
    Logger::debug("Fetching remote changes for: " + folder.remotePath);
}

void SyncEngine::uploadFile(const std::string& localPath, const std::string& remotePath) {
    Logger::info("Uploading: " + localPath + " -> " + remotePath);
    
    if (!authenticated_) {
        Logger::error("Not authenticated");
        return;
    }

    try {
        stats_.status = SyncStatus::SYNCING;
        notifyStatusChange();
        
        if (httpClient_->uploadFile(localPath, remotePath)) {
            Logger::info("Upload successful: " + localPath);
        } else {
            Logger::error("Upload failed: " + localPath);
        }
        
        stats_.status = SyncStatus::IDLE;
        notifyStatusChange();
    } catch (const std::exception& e) {
        Logger::error("Upload error: " + std::string(e.what()));
        stats_.status = SyncStatus::ERROR;
        notifyStatusChange();
    }
}

void SyncEngine::downloadFile(const std::string& remotePath, const std::string& localPath) {
    Logger::info("Downloading: " + remotePath + " -> " + localPath);
    
    // TODO: Implement download
}

void SyncEngine::handleConflict(const std::string& path) {
    Logger::warn("Conflict detected: " + path);
    
    // TODO: Implement conflict handling
}

void SyncEngine::updateStats() {
    std::lock_guard<std::mutex> lock(statsMutex_);
    
    // Update statistics
    // TODO: Calculate real values
    stats_.lastSync = std::to_string(std::time(nullptr));
}

void SyncEngine::notifyStatusChange() {
    if (statusCallback_) {
        statusCallback_(getStats());
    }
}

} // namespace baludesk
