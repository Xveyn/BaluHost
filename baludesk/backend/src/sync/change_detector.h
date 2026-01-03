#pragma once

#include <string>
#include <vector>
#include <chrono>
#include <optional>

namespace baludesk {

// Forward declarations
class Database;
class HttpClient;

// Change Types
enum class ChangeType {
    CREATED,
    MODIFIED,
    DELETED
};

// Represents a detected change (local or remote)
struct DetectedChange {
    std::string path;           // Relative path
    ChangeType type;
    std::chrono::system_clock::time_point timestamp;
    std::optional<std::string> hash;  // SHA256 for modified files
    size_t size;                // File size
    bool isRemote;              // true = remote, false = local
};

// Conflict detection result
struct ConflictInfo {
    std::string path;
    std::chrono::system_clock::time_point localTimestamp;
    std::chrono::system_clock::time_point remoteTimestamp;
    std::string localHash;
    std::string remoteHash;
};

class ChangeDetector {
public:
    explicit ChangeDetector(Database* db, HttpClient* httpClient);
    ~ChangeDetector();

    // Remote change detection
    // Polls remote API for changes since last sync
    std::vector<DetectedChange> detectRemoteChanges(
        const std::string& syncFolderId,
        const std::chrono::system_clock::time_point& since
    );

    // Local change detection
    // Scans local filesystem for changes since last sync
    std::vector<DetectedChange> detectLocalChanges(
        const std::string& syncFolderId,
        const std::string& localPath
    );

    // Conflict detection
    // Compares local and remote changes to find conflicts
    std::vector<ConflictInfo> detectConflicts(
        const std::vector<DetectedChange>& localChanges,
        const std::vector<DetectedChange>& remoteChanges
    );

    // Metadata comparison
    // Checks if file has changed based on metadata
    bool hasFileChanged(
        const std::string& path,
        const std::chrono::system_clock::time_point& timestamp,
        const std::string& hash
    );

private:
    Database* db_;
    HttpClient* httpClient_;

    // Helper: Calculate SHA256 hash of file
    std::string calculateFileHash(const std::string& filePath);

    // Helper: Recursive directory scan
    void scanDirectory(
        const std::string& dirPath,
        const std::string& basePath,
        std::vector<DetectedChange>& changes
    );
};

} // namespace baludesk
