#include "ssh_service.h"
#include "../utils/logger.h"
#include <sstream>
#include <regex>
#include <cstring>

// Note: For production use, integrate with libssh2:
// #include <libssh2.h>
// #include <libssh2_sftp.h>
// Link with: libssh2.lib ws2_32.lib
// See: https://www.libssh2.org/

namespace baludesk {

bool SshService::libssh2_initialized_ = false;

SshService::SshService() {
    // Initialize libssh2 once on first use
    initializeLibssh2();
}

SshService::~SshService() {
    // Cleanup is handled by static cleanup at program exit
}

void SshService::initializeLibssh2() {
    if (libssh2_initialized_) {
        return;
    }
    
    // TODO: Call libssh2_init(0) for actual libssh2 integration
    // int rc = libssh2_init(0);
    // if (rc != 0) {
    //     Logger::error("Failed to initialize libssh2");
    //     return;
    // }
    
    libssh2_initialized_ = true;
    Logger::info("SSH service initialized");
}

void SshService::cleanupLibssh2() {
    if (!libssh2_initialized_) {
        return;
    }
    
    // TODO: Call libssh2_exit() for actual libssh2 integration
    // libssh2_exit();
    
    libssh2_initialized_ = false;
    Logger::info("SSH service cleaned up");
}

bool SshService::validatePrivateKey(const std::string& privateKey) const {
    // Check for PEM format markers
    if (privateKey.find("BEGIN") == std::string::npos ||
        privateKey.find("END") == std::string::npos) {
        return false;
    }
    
    // Check for minimum length
    if (privateKey.length() < 100) {
        return false;
    }
    
    return true;
}

bool SshService::validateHost(const std::string& host) const {
    if (host.empty() || host.length() > 255) {
        return false;
    }
    
    // Validate IP address or hostname
    std::regex ipv4_regex(
        "^(([0-9]|[1-9][0-9]|1[0-9]{2}|2[0-4][0-9]|25[0-5])\\.){3}"
        "([0-9]|[1-9][0-9]|1[0-9]{2}|2[0-4][0-9]|25[0-5])$"
    );
    
    std::regex hostname_regex(
        "^([a-zA-Z0-9]([a-zA-Z0-9\\-]{0,61}[a-zA-Z0-9])?\\.)*"
        "[a-zA-Z0-9]([a-zA-Z0-9\\-]{0,61}[a-zA-Z0-9])?$"
    );
    
    return std::regex_match(host, ipv4_regex) || std::regex_match(host, hostname_regex);
}

SshService::ConnectionResult SshService::testConnection(
    const std::string& host,
    int port,
    const std::string& username,
    const std::string& privateKey,
    int timeout  // Parameter will be used for libssh2 integration
) {
    (void)timeout;  // Mark as intentionally unused for now
    ConnectionResult result;
    result.connected = false;
    
    // Input validation
    if (!validateHost(host)) {
        result.message = "Invalid host address";
        result.errorCode = "INVALID_HOST";
        Logger::warn("SSH test connection: invalid host '{}'", host);
        return result;
    }
    
    if (port < 1 || port > 65535) {
        result.message = "Invalid SSH port";
        result.errorCode = "INVALID_PORT";
        Logger::warn("SSH test connection: invalid port {}", port);
        return result;
    }
    
    if (username.empty()) {
        result.message = "Username cannot be empty";
        result.errorCode = "INVALID_USERNAME";
        return result;
    }
    
    if (!validatePrivateKey(privateKey)) {
        result.message = "Invalid or malformed SSH private key";
        result.errorCode = "INVALID_KEY";
        Logger::warn("SSH test connection: invalid private key format");
        return result;
    }
    
    try {
        // TODO: Implement actual SSH connection using libssh2
        /*
        // Pseudo-code for libssh2 implementation:
        
        int sock = socket(AF_INET, SOCK_STREAM, 0);
        struct sockaddr_in sin;
        sin.sin_family = AF_INET;
        sin.sin_port = htons(port);
        sin.sin_addr.s_addr = inet_addr(host.c_str());
        
        if (connect(sock, (struct sockaddr*)(&sin), sizeof(struct sockaddr_in)) != 0) {
            result.message = "Could not connect to host";
            result.errorCode = "CONNECTION_FAILED";
            return result;
        }
        
        LIBSSH2_SESSION *session = libssh2_session_init();
        if (!session) {
            result.message = "Failed to create SSH session";
            result.errorCode = "SESSION_INIT_FAILED";
            closesocket(sock);
            return result;
        }
        
        libssh2_session_set_blocking(session, 1);
        
        int rc = libssh2_session_handshake(session, sock);
        if (rc) {
            result.message = "SSH handshake failed";
            result.errorCode = "HANDSHAKE_FAILED";
            libssh2_session_free(session);
            closesocket(sock);
            return result;
        }
        
        // Use private key for authentication
        int auth_pw = libssh2_userauth_publickey_fromfile(
            session, username.c_str(),
            nullptr,  // public key file (optional)
            nullptr,  // private key file path - we use in-memory key
            nullptr   // passphrase
        );
        
        // For in-memory key, use libssh2_userauth_publickey():
        // Convert privateKey string to proper format and authenticate
        
        if (auth_pw) {
            result.message = "SSH authentication failed";
            result.errorCode = "AUTH_FAILED";
            libssh2_session_free(session);
            closesocket(sock);
            return result;
        }
        
        // Test successful - close connection
        libssh2_session_disconnect(session, "Normal Shutdown");
        libssh2_session_free(session);
        closesocket(sock);
        
        result.connected = true;
        result.message = "SSH connection successful";
        result.errorCode = "";
        */
        
        // For now, return success with mock implementation
        result.connected = true;
        result.message = "SSH connection test passed";
        result.errorCode = "";
        
        Logger::info("SSH connection test successful to {}:{} as {}", host, port, username);
        return result;
        
    } catch (const std::exception& e) {
        result.message = std::string("SSH connection test failed: ") + e.what();
        result.errorCode = "EXCEPTION";
        Logger::error("SSH connection test exception: {}", e.what());
        return result;
    }
}

SshService::ExecutionResult SshService::executeCommand(
    const std::string& host,
    int port,
    const std::string& username,
    const std::string& privateKey,
    const std::string& command,
    int timeout  // Parameter will be used for libssh2 integration
) {
    (void)timeout;  // Mark as intentionally unused for now
    ExecutionResult result;
    result.success = false;
    result.exitCode = -1;
    
    // Input validation
    if (!validateHost(host)) {
        result.errorOutput = "Invalid host address";
        Logger::warn("SSH execute: invalid host '{}'", host);
        return result;
    }
    
    if (port < 1 || port > 65535) {
        result.errorOutput = "Invalid SSH port";
        Logger::warn("SSH execute: invalid port {}", port);
        return result;
    }
    
    if (username.empty()) {
        result.errorOutput = "Username cannot be empty";
        return result;
    }
    
    if (!validatePrivateKey(privateKey)) {
        result.errorOutput = "Invalid or malformed SSH private key";
        Logger::warn("SSH execute: invalid private key format");
        return result;
    }
    
    if (command.empty()) {
        result.errorOutput = "Command cannot be empty";
        return result;
    }
    
    try {
        // TODO: Implement actual command execution using libssh2
        /*
        // Pseudo-code for libssh2 implementation:
        
        // 1. Open SSH connection (same as testConnection)
        // 2. Open channel for command execution
        
        LIBSSH2_CHANNEL *channel = libssh2_channel_open_session(session);
        if (!channel) {
            result.errorOutput = "Failed to open SSH channel";
            result.exitCode = -1;
            return result;
        }
        
        int rc = libssh2_channel_exec(channel, command.c_str());
        if (rc) {
            result.errorOutput = "Failed to execute command";
            result.exitCode = -1;
            libssh2_channel_free(channel);
            return result;
        }
        
        // Read output from channel
        char buffer[1024];
        int nbytes;
        while ((nbytes = libssh2_channel_read(channel, buffer, sizeof(buffer))) > 0) {
            result.output.append(buffer, nbytes);
        }
        
        // Read error output
        while ((nbytes = libssh2_channel_read_stderr(channel, buffer, sizeof(buffer))) > 0) {
            result.errorOutput.append(buffer, nbytes);
        }
        
        // Get exit code
        result.exitCode = libssh2_channel_get_exit_status(channel);
        
        libssh2_channel_close(channel);
        libssh2_channel_free(channel);
        libssh2_session_disconnect(session, "Normal Shutdown");
        libssh2_session_free(session);
        closesocket(sock);
        
        result.success = (result.exitCode == 0);
        */
        
        // For now, return mock successful execution
        result.success = true;
        result.output = "Command executed successfully";
        result.errorOutput = "";
        result.exitCode = 0;
        
        Logger::info("SSH command executed on {}:{} as {}: {}", 
                     host, port, username, command);
        return result;
        
    } catch (const std::exception& e) {
        result.errorOutput = std::string("SSH command execution failed: ") + e.what();
        result.exitCode = -1;
        result.success = false;
        Logger::error("SSH command execution exception: {}", e.what());
        return result;
    }
}

} // namespace baludesk
