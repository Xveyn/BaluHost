#pragma once

#include <string>
#include <functional>
#include <chrono>

namespace baludesk {

// Forward declarations
class Database;
class HttpClient;

// Conflict Resolution Strategies
enum class ResolutionStrategy {
    LAST_WRITE_WINS,     // Newest file wins
    KEEP_BOTH,           // Rename and keep both versions
    MANUAL,              // User decides (requires UI callback)
    LOCAL_WINS,          // Always prefer local
    REMOTE_WINS          // Always prefer remote
};

// Resolution result
struct ResolutionResult {
    bool success;
    std::string action;           // "uploaded", "downloaded", "renamed", "manual"
    std::string finalPath;        // Final path after resolution
    std::string errorMessage;
};

class ConflictResolver {
public:
    explicit ConflictResolver(
        Database* db,
        HttpClient* httpClient,
        ResolutionStrategy defaultStrategy = ResolutionStrategy::LAST_WRITE_WINS
    );
    ~ConflictResolver();

    // Resolve a single conflict
    ResolutionResult resolve(
        const std::string& localPath,
        const std::string& remotePath,
        const std::chrono::system_clock::time_point& localTimestamp,
        const std::chrono::system_clock::time_point& remoteTimestamp,
        ResolutionStrategy strategy
    );

    // Resolve using default strategy
    ResolutionResult resolveAuto(
        const std::string& localPath,
        const std::string& remotePath,
        const std::chrono::system_clock::time_point& localTimestamp,
        const std::chrono::system_clock::time_point& remoteTimestamp
    );

    // Set manual resolution callback (for UI)
    using ManualResolutionCallback = std::function<ResolutionStrategy(
        const std::string& localPath,
        const std::string& remotePath
    )>;
    void setManualCallback(ManualResolutionCallback callback);

    // Change default strategy
    void setDefaultStrategy(ResolutionStrategy strategy);

private:
    Database* db_;
    HttpClient* httpClient_;
    ResolutionStrategy defaultStrategy_;
    ManualResolutionCallback manualCallback_;

    // Strategy implementations
    ResolutionResult resolveLastWriteWins(
        const std::string& localPath,
        const std::string& remotePath,
        const std::chrono::system_clock::time_point& localTimestamp,
        const std::chrono::system_clock::time_point& remoteTimestamp
    );

    ResolutionResult resolveKeepBoth(
        const std::string& localPath,
        const std::string& remotePath
    );

    ResolutionResult resolveManual(
        const std::string& localPath,
        const std::string& remotePath
    );
};

} // namespace baludesk
