#pragma once

#include <string>
#include <vector>

namespace baludesk {

/**
 * SSH Service for remote server connections and command execution
 * Provides interface for SSH authentication, connection testing, and command execution
 */
class SshService {
public:
    /**
     * Result of SSH connection test
     */
    struct ConnectionResult {
        bool connected;
        std::string message;
        std::string errorCode;
    };

    /**
     * Result of SSH command execution
     */
    struct ExecutionResult {
        bool success;
        std::string output;
        std::string errorOutput;
        int exitCode;
    };

    SshService();
    ~SshService();

    /**
     * Test connection to a remote server
     * @param host SSH host address
     * @param port SSH port (default 22)
     * @param username SSH username
     * @param privateKey SSH private key content (PEM format)
     * @param timeout Connection timeout in seconds (default 10)
     * @return ConnectionResult with connection status and message
     */
    ConnectionResult testConnection(
        const std::string& host,
        int port,
        const std::string& username,
        const std::string& privateKey,
        int timeout = 10
    );

    /**
     * Execute a command on a remote server
     * @param host SSH host address
     * @param port SSH port (default 22)
     * @param username SSH username
     * @param privateKey SSH private key content (PEM format)
     * @param command Command to execute
     * @param timeout Command timeout in seconds (default 30)
     * @return ExecutionResult with command output and exit code
     */
    ExecutionResult executeCommand(
        const std::string& host,
        int port,
        const std::string& username,
        const std::string& privateKey,
        const std::string& command,
        int timeout = 30
    );

private:
    /**
     * Initialize SSH library (called once on startup)
     */
    static void initializeLibssh2();

    /**
     * Cleanup SSH library (called on shutdown)
     */
    static void cleanupLibssh2();

    /**
     * Validate SSH private key format
     */
    bool validatePrivateKey(const std::string& privateKey) const;

    /**
     * Validate host address format
     */
    bool validateHost(const std::string& host) const;

    static bool libssh2_initialized_;
};

} // namespace baludesk
