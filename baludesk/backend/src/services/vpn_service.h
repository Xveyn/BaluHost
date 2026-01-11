#pragma once

#include <string>
#include <vector>

namespace baludesk {

/**
 * VPN Service for testing VPN configurations
 * Supports multiple VPN types: OpenVPN, WireGuard, IPSec, L2TP, PPTP, OpenConnect
 */
class VpnService {
public:
    /**
     * Supported VPN types
     */
    enum class VpnType {
        OpenVPN,
        WireGuard,
        IPSec,
        L2TP,
        PPTP,
        OpenConnect,
        Unknown
    };

    /**
     * Result of VPN connection test
     */
    struct ConnectionResult {
        bool connected;
        std::string message;
        std::string errorCode;
    };

    VpnService();
    ~VpnService();

    /**
     * Parse VPN type from string
     * @param vpnTypeStr VPN type string (OpenVPN, WireGuard, etc.)
     * @return Parsed VPN type
     */
    static VpnType parseVpnType(const std::string& vpnTypeStr);

    /**
     * Get VPN type as string
     * @param vpnType VPN type enum
     * @return VPN type string
     */
    static std::string vpnTypeToString(VpnType vpnType);

    /**
     * Test VPN connection by validating configuration
     * @param vpnType Type of VPN (OpenVPN, WireGuard, etc.)
     * @param configContent VPN configuration file content
     * @param certificate Optional VPN certificate
     * @param privateKey Optional VPN private key
     * @return ConnectionResult with connection status and message
     */
    ConnectionResult testConnection(
        const std::string& vpnType,
        const std::string& configContent,
        const std::string& certificate = "",
        const std::string& privateKey = ""
    );

private:
    /**
     * Validate OpenVPN configuration
     */
    bool validateOpenVpnConfig(
        const std::string& configContent,
        const std::string& certificate,
        const std::string& privateKey
    ) const;

    /**
     * Validate WireGuard configuration
     */
    bool validateWireGuardConfig(const std::string& configContent) const;

    /**
     * Validate IPSec configuration
     */
    bool validateIPSecConfig(const std::string& configContent) const;

    /**
     * Validate L2TP configuration
     */
    bool validateL2TPConfig(const std::string& configContent) const;

    /**
     * Validate PPTP configuration
     */
    bool validatePPTPConfig(const std::string& configContent) const;

    /**
     * Validate OpenConnect configuration
     */
    bool validateOpenConnectConfig(const std::string& configContent) const;

    /**
     * Check if configuration contains required lines
     */
    bool hasConfigLine(const std::string& config, const std::string& line) const;
};

} // namespace baludesk
