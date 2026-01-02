#pragma once

#include <string>
#include <vector>
#include <memory>
#include <curl/curl.h>

namespace baludesk {

struct RemoteFile {
    std::string name;
    std::string path;
    uint64_t size;
    bool isDirectory;
    std::string modifiedAt;
};

struct RemoteChange {
    std::string path;
    std::string action; // created, modified, deleted
    std::string timestamp;
};

/**
 * HttpClient - REST API client for BaluHost NAS
 * 
 * Handles all HTTP communication using libcurl
 */
class HttpClient {
public:
    explicit HttpClient(const std::string& baseUrl);
    ~HttpClient();

    // Authentication
    bool login(const std::string& username, const std::string& password);
    void setAuthToken(const std::string& token);
    void clearAuthToken();
    bool isAuthenticated() const;

    // File operations
    std::vector<RemoteFile> listFiles(const std::string& path);
    bool uploadFile(const std::string& localPath, const std::string& remotePath);
    bool downloadFile(const std::string& remotePath, const std::string& localPath);
    bool deleteFile(const std::string& remotePath);

    // Sync operations
    std::vector<RemoteChange> getChangesSince(const std::string& timestamp);

    // Configuration
    void setTimeout(long timeoutSeconds);
    void setVerbose(bool verbose);

private:
    std::string performRequest(const std::string& url, const std::string& method,
                               const std::string& body = "");
    static size_t writeCallback(void* contents, size_t size, size_t nmemb, void* userp);
    static size_t readCallback(void* ptr, size_t size, size_t nmemb, void* userp);

    std::string baseUrl_;
    std::string authToken_;
    CURL* curl_;
    long timeout_;
    bool verbose_;
};

} // namespace baludesk
