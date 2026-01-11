#include "baluhost_client.h"
#include <curl/curl.h>
#include <spdlog/spdlog.h>
#include <fstream>
#include <sstream>

namespace baludesk {

// CURL write callback for string response
static size_t WriteCallback(void* contents, size_t size, size_t nmemb, void* userp) {
    ((std::string*)userp)->append((char*)contents, size * nmemb);
    return size * nmemb;
}

// CURL write callback for binary data
static size_t WriteBinaryCallback(void* contents, size_t size, size_t nmemb, void* userp) {
    auto* vec = reinterpret_cast<std::vector<uint8_t>*>(userp);
    if (!vec) return 0;
    const auto* data = reinterpret_cast<const uint8_t*>(contents);
    size_t total = size * nmemb;
    try {
        vec->reserve(vec->size() + total);
        vec->insert(vec->end(), data, data + total);
    } catch (...) {
        return 0;
    }
    return total;
}

BaluhostClient::BaluhostClient(const std::string& baseUrl)
    : baseUrl_(baseUrl) {
    curl_global_init(CURL_GLOBAL_DEFAULT);
}

BaluhostClient::~BaluhostClient() {
    curl_global_cleanup();
}

bool BaluhostClient::login(const std::string& username, const std::string& password) {
    nlohmann::json body = {
        {"username", username},
        {"password", password}
    };

    auto response = makeRequest("POST", "/api/auth/login", body, false);
    if (!response) {
        return false;
    }

    if (response->contains("access_token")) {
        authToken_ = (*response)["access_token"].get<std::string>();
        spdlog::info("BaluHost authentication successful");
        return true;
    }

    lastError_ = "No access token in login response";
    return false;
}

void BaluhostClient::setAuthToken(const std::string& token) {
    authToken_ = token;
}

bool BaluhostClient::isAuthenticated() const {
    return !authToken_.empty();
}

std::vector<FileItem> BaluhostClient::listFiles(const std::string& path, const std::string& mountId) {
    std::string endpoint = "/api/files/list?path=" + path;
    if (!mountId.empty()) {
        endpoint += "&mount=" + mountId;
    }

    auto response = makeRequest("GET", endpoint);
    if (!response) {
        return {};
    }

    std::vector<FileItem> files;
    if (response->contains("files") && response->at("files").is_array()) {
        for (const auto& item : response->at("files")) {
            files.push_back(parseFileItem(item));
        }
    }

    return files;
}

std::vector<Mountpoint> BaluhostClient::getMountpoints() {
    auto response = makeRequest("GET", "/api/files/mountpoints");
    if (!response) {
        return {};
    }

    std::vector<Mountpoint> mountpoints;
    if (response->contains("mountpoints") && response->at("mountpoints").is_array()) {
        for (const auto& item : response->at("mountpoints")) {
            mountpoints.push_back(parseMountpoint(item));
        }
    }

    return mountpoints;
}

bool BaluhostClient::createFolder(const std::string& path, const std::string& name, const std::string& mountId) {
    nlohmann::json body = {
        {"path", path},
        {"name", name}
    };
    if (!mountId.empty()) {
        body["mount_id"] = mountId;
    }

    auto response = makeRequest("POST", "/api/files/folder", body);
    return response.has_value();
}

bool BaluhostClient::renameFile(int fileId, const std::string& newName) {
    nlohmann::json body = {
        {"file_id", fileId},
        {"new_name", newName}
    };

    auto response = makeRequest("PUT", "/api/files/rename", body);
    return response.has_value();
}

bool BaluhostClient::moveFile(int fileId, const std::string& newPath) {
    nlohmann::json body = {
        {"file_id", fileId},
        {"new_path", newPath}
    };

    auto response = makeRequest("PUT", "/api/files/move", body);
    return response.has_value();
}

bool BaluhostClient::deleteFile(int fileId) {
    auto response = makeRequest("DELETE", "/api/files/" + std::to_string(fileId));
    return response.has_value();
}

bool BaluhostClient::downloadFile(int fileId, const std::string& localPath) {
    auto data = downloadBinary("/api/files/download/" + std::to_string(fileId));
    if (!data) {
        return false;
    }

    std::ofstream file(localPath, std::ios::binary);
    if (!file) {
        lastError_ = "Failed to open local file for writing: " + localPath;
        return false;
    }

    file.write(reinterpret_cast<const char*>(data->data()), data->size());
    return file.good();
}

bool BaluhostClient::downloadFileByPath(const std::string& remotePath, const std::string& localPath) {
    auto data = downloadBinary("/api/files/download/" + remotePath);
    if (!data) {
        return false;
    }

    std::ofstream file(localPath, std::ios::binary);
    if (!file) {
        lastError_ = "Failed to open local file for writing: " + localPath;
        return false;
    }

    file.write(reinterpret_cast<const char*>(data->data()), data->size());
    return file.good();
}

bool BaluhostClient::uploadFile(const std::string& localPath, const std::string& remotePath, const std::string& mountId) {
    // Read file into memory
    std::ifstream file(localPath, std::ios::binary | std::ios::ate);
    if (!file) {
        lastError_ = "Failed to open local file for reading: " + localPath;
        return false;
    }

    std::streamsize size = file.tellg();
    file.seekg(0, std::ios::beg);

    std::vector<uint8_t> buffer(size);
    if (!file.read(reinterpret_cast<char*>(buffer.data()), size)) {
        lastError_ = "Failed to read local file: " + localPath;
        return false;
    }

    // Extract filename from path
    std::string filename = localPath.substr(localPath.find_last_of("/\\") + 1);

    // Upload
    std::string endpoint = "/api/files/upload?path=" + remotePath;
    if (!mountId.empty()) {
        endpoint += "&mount=" + mountId;
    }

    return uploadBinary(endpoint, buffer, filename);
}

std::vector<Permission> BaluhostClient::getPermissions(int fileId) {
    auto response = makeRequest("GET", "/api/files/" + std::to_string(fileId) + "/permissions");
    if (!response) {
        return {};
    }

    std::vector<Permission> permissions;
    if (response->contains("permissions") && response->at("permissions").is_array()) {
        for (const auto& item : response->at("permissions")) {
            permissions.push_back(parsePermission(item));
        }
    }

    return permissions;
}

bool BaluhostClient::setPermission(int fileId, const std::string& username, 
                                   bool canView, bool canEdit, bool canDelete) {
    nlohmann::json body = {
        {"username", username},
        {"can_view", canView},
        {"can_edit", canEdit},
        {"can_delete", canDelete}
    };

    auto response = makeRequest("POST", "/api/files/" + std::to_string(fileId) + "/permissions", body);
    return response.has_value();
}

bool BaluhostClient::removePermission(int fileId, const std::string& username) {
    auto response = makeRequest("DELETE", "/api/files/" + std::to_string(fileId) + "/permissions/" + username);
    return response.has_value();
}

std::string BaluhostClient::getLastError() const {
    return lastError_;
}

std::optional<nlohmann::json> BaluhostClient::makeRequest(
    const std::string& method,
    const std::string& endpoint,
    const nlohmann::json& body,
    bool requireAuth
) {
    CURL* curl = curl_easy_init();
    if (!curl) {
        lastError_ = "Failed to initialize CURL";
        return std::nullopt;
    }

    std::string url = baseUrl_ + endpoint;
    std::string response_string;
    std::string error_buffer;

    curl_easy_setopt(curl, CURLOPT_URL, url.c_str());
    curl_easy_setopt(curl, CURLOPT_WRITEFUNCTION, WriteCallback);
    curl_easy_setopt(curl, CURLOPT_WRITEDATA, &response_string);
    
    // Verbose logging disabled by default
    curl_easy_setopt(curl, CURLOPT_VERBOSE, 0L);
    
    // Check if URL starts with https:// to determine SSL usage
    bool useSSL = (url.find("https://") == 0);
    
    if (useSSL) {
        // For HTTPS: Disable SSL verification for development (self-signed certs)
        curl_easy_setopt(curl, CURLOPT_SSL_VERIFYPEER, 0L);
        curl_easy_setopt(curl, CURLOPT_SSL_VERIFYHOST, 0L);
    } else {
        // For HTTP: Explicitly disable SSL to prevent Windows Schannel from auto-enabling it
        curl_easy_setopt(curl, CURLOPT_SSL_VERIFYPEER, 0L);
        curl_easy_setopt(curl, CURLOPT_SSL_VERIFYHOST, 0L);
        curl_easy_setopt(curl, CURLOPT_USE_SSL, CURLUSESSL_NONE);
    }
    
    // Set user agent
    curl_easy_setopt(curl, CURLOPT_USERAGENT, "BaluDesk/1.0");
    
    // DISABLE redirects to prevent HTTP->HTTPS redirect
    curl_easy_setopt(curl, CURLOPT_FOLLOWLOCATION, 0L);

    // Set method
    if (method == "POST") {
        curl_easy_setopt(curl, CURLOPT_POST, 1L);
    } else if (method == "PUT") {
        curl_easy_setopt(curl, CURLOPT_CUSTOMREQUEST, "PUT");
    } else if (method == "DELETE") {
        curl_easy_setopt(curl, CURLOPT_CUSTOMREQUEST, "DELETE");
    }

    // Set headers
    struct curl_slist* headers = nullptr;
    headers = curl_slist_append(headers, "Content-Type: application/json");
    
    if (requireAuth && !authToken_.empty()) {
        std::string auth_header = "Authorization: Bearer " + authToken_;
        headers = curl_slist_append(headers, auth_header.c_str());
    }
    
    curl_easy_setopt(curl, CURLOPT_HTTPHEADER, headers);

    // Set body if provided
    std::string body_string;
    if (!body.is_null()) {
        body_string = body.dump();
        curl_easy_setopt(curl, CURLOPT_POSTFIELDS, body_string.c_str());
        curl_easy_setopt(curl, CURLOPT_POSTFIELDSIZE, body_string.length());
    } else if (method == "POST" || method == "PUT") {
        // Empty body for POST/PUT
        curl_easy_setopt(curl, CURLOPT_POSTFIELDS, "");
        curl_easy_setopt(curl, CURLOPT_POSTFIELDSIZE, 0);
    }

    // Perform request
    CURLcode res = curl_easy_perform(curl);
    
    long response_code;
    curl_easy_getinfo(curl, CURLINFO_RESPONSE_CODE, &response_code);

    curl_slist_free_all(headers);
    curl_easy_cleanup(curl);

    if (res != CURLE_OK) {
        lastError_ = "CURL error: " + std::string(curl_easy_strerror(res));
        return std::nullopt;
    }

    if (response_code < 200 || response_code >= 300) {
        lastError_ = "HTTP error " + std::to_string(response_code) + ": " + response_string;
        spdlog::error("BaluHost API error: {}", lastError_);
        return std::nullopt;
    }

    try {
        return nlohmann::json::parse(response_string);
    } catch (const nlohmann::json::exception& e) {
        lastError_ = "JSON parse error: " + std::string(e.what());
        return std::nullopt;
    }
}

std::optional<std::vector<uint8_t>> BaluhostClient::downloadBinary(const std::string& endpoint) {
    CURL* curl = curl_easy_init();
    if (!curl) {
        lastError_ = "Failed to initialize CURL";
        return std::nullopt;
    }

    std::string url = baseUrl_ + endpoint;
    std::vector<uint8_t> data;

    curl_easy_setopt(curl, CURLOPT_URL, url.c_str());
    curl_easy_setopt(curl, CURLOPT_WRITEFUNCTION, WriteBinaryCallback);
    curl_easy_setopt(curl, CURLOPT_WRITEDATA, &data);

    // Set auth header
    struct curl_slist* headers = nullptr;
    if (!authToken_.empty()) {
        std::string auth_header = "Authorization: Bearer " + authToken_;
        headers = curl_slist_append(headers, auth_header.c_str());
        curl_easy_setopt(curl, CURLOPT_HTTPHEADER, headers);
    }

    CURLcode res = curl_easy_perform(curl);
    
    long response_code;
    curl_easy_getinfo(curl, CURLINFO_RESPONSE_CODE, &response_code);

    if (headers) curl_slist_free_all(headers);
    curl_easy_cleanup(curl);

    if (res != CURLE_OK) {
        lastError_ = "CURL error: " + std::string(curl_easy_strerror(res));
        return std::nullopt;
    }

    if (response_code < 200 || response_code >= 300) {
        lastError_ = "HTTP error " + std::to_string(response_code);
        return std::nullopt;
    }

    return data;
}

bool BaluhostClient::uploadBinary(const std::string& endpoint, 
                                   const std::vector<uint8_t>& data, 
                                   const std::string& filename) {
    CURL* curl = curl_easy_init();
    if (!curl) {
        lastError_ = "Failed to initialize CURL";
        return false;
    }

    std::string url = baseUrl_ + endpoint;
    std::string response_string;

    curl_mime* form = curl_mime_init(curl);
    curl_mimepart* field = curl_mime_addpart(form);
    curl_mime_name(field, "file");
    curl_mime_data(field, reinterpret_cast<const char*>(data.data()), data.size());
    curl_mime_filename(field, filename.c_str());

    curl_easy_setopt(curl, CURLOPT_URL, url.c_str());
    curl_easy_setopt(curl, CURLOPT_MIMEPOST, form);
    curl_easy_setopt(curl, CURLOPT_WRITEFUNCTION, WriteCallback);
    curl_easy_setopt(curl, CURLOPT_WRITEDATA, &response_string);

    // Set auth header
    struct curl_slist* headers = nullptr;
    if (!authToken_.empty()) {
        std::string auth_header = "Authorization: Bearer " + authToken_;
        headers = curl_slist_append(headers, auth_header.c_str());
        curl_easy_setopt(curl, CURLOPT_HTTPHEADER, headers);
    }

    CURLcode res = curl_easy_perform(curl);
    
    long response_code;
    curl_easy_getinfo(curl, CURLINFO_RESPONSE_CODE, &response_code);

    if (headers) curl_slist_free_all(headers);
    curl_mime_free(form);
    curl_easy_cleanup(curl);

    if (res != CURLE_OK) {
        lastError_ = "CURL error: " + std::string(curl_easy_strerror(res));
        return false;
    }

    if (response_code < 200 || response_code >= 300) {
        lastError_ = "HTTP error " + std::to_string(response_code) + ": " + response_string;
        return false;
    }

    return true;
}

FileItem BaluhostClient::parseFileItem(const nlohmann::json& json) {
    FileItem item;
    // Check both "file_id" (from Backend API) and "id" for compatibility
    if (json.contains("file_id") && !json["file_id"].is_null()) {
        item.id = json["file_id"].get<int>();
    } else {
        item.id = json.value("id", 0);
    }
    item.name = json.value("name", "");
    item.path = json.value("path", "");
    item.type = json.value("type", "file");
    item.size = json.value("size", 0LL);
    item.owner = json.value("owner", "");
    item.created_at = json.value("created_at", "");
    item.updated_at = json.value("updated_at", "");
    
    if (json.contains("mount_id") && !json["mount_id"].is_null()) {
        item.mount_id = json["mount_id"].get<int>();
    } else {
        item.mount_id = 0;
    }
    
    return item;
}

Mountpoint BaluhostClient::parseMountpoint(const nlohmann::json& json) {
    Mountpoint mp;
    
    // Handle id as integer or string
    if (json.contains("id") && !json["id"].is_null()) {
        if (json["id"].is_number()) {
            mp.id = std::to_string(json["id"].get<int>());
        } else if (json["id"].is_string()) {
            mp.id = json["id"].get<std::string>();
        }
    }
    
    // Handle all string fields with null checking
    mp.name = (json.contains("name") && !json["name"].is_null()) ? json["name"].get<std::string>() : "";
    mp.mount_path = (json.contains("path") && !json["path"].is_null()) ? json["path"].get<std::string>() : "";
    mp.raid_level = (json.contains("raid_level") && !json["raid_level"].is_null()) ? json["raid_level"].get<std::string>() : "";
    
    mp.total_size = json.value("size_bytes", 0LL);
    mp.used_size = json.value("used_bytes", 0LL);
    mp.available_size = json.value("available_bytes", 0LL);
    return mp;
}

Permission BaluhostClient::parsePermission(const nlohmann::json& json) {
    Permission perm;
    perm.username = json.value("username", "");
    perm.can_view = json.value("can_view", false);
    perm.can_edit = json.value("can_edit", false);
    perm.can_delete = json.value("can_delete", false);
    return perm;
}

} // namespace baludesk
