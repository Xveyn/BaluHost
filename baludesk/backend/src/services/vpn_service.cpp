#include "vpn_service.h"
#include "../utils/logger.h"
#include <algorithm>
#include <sstream>

namespace baludesk {

VpnService::VpnService() {
    Logger::info("VPN service initialized");
}

VpnService::~VpnService() {
    Logger::info("VPN service cleaned up");
}

VpnService::VpnType VpnService::parseVpnType(const std::string& vpnTypeStr) {
    std::string lower = vpnTypeStr;
    std::transform(lower.begin(), lower.end(), lower.begin(), ::tolower);
    
    if (lower == "openvpn") return VpnType::OpenVPN;
    if (lower == "wireguard") return VpnType::WireGuard;
    if (lower == "ipsec") return VpnType::IPSec;
    if (lower == "l2tp") return VpnType::L2TP;
    if (lower == "pptp") return VpnType::PPTP;
    if (lower == "openconnect") return VpnType::OpenConnect;
    
    return VpnType::Unknown;
}

std::string VpnService::vpnTypeToString(VpnType vpnType) {
    switch (vpnType) {
        case VpnType::OpenVPN:
            return "OpenVPN";
        case VpnType::WireGuard:
            return "WireGuard";
        case VpnType::IPSec:
            return "IPSec";
        case VpnType::L2TP:
            return "L2TP";
        case VpnType::PPTP:
            return "PPTP";
        case VpnType::OpenConnect:
            return "OpenConnect";
        default:
            return "Unknown";
    }
}

bool VpnService::hasConfigLine(const std::string& config, const std::string& line) const {
    return config.find(line) != std::string::npos;
}

bool VpnService::validateOpenVpnConfig(
    const std::string& configContent,
    const std::string& certificate,
    const std::string& privateKey
) const {
    // Check for required OpenVPN directives
    if (!hasConfigLine(configContent, "client") && !hasConfigLine(configContent, "server")) {
        Logger::warn("OpenVPN config: missing client/server directive");
        return false;
    }
    
    // Check for remote server in client mode
    if (hasConfigLine(configContent, "client")) {
        if (!hasConfigLine(configContent, "remote")) {
            Logger::warn("OpenVPN client: missing remote directive");
            return false;
        }
    }
    
    // Check for certificate/key if embedded
    if (hasConfigLine(configContent, "<cert>") || hasConfigLine(configContent, "<ca>")) {
        if (!hasConfigLine(configContent, "</cert>") && !hasConfigLine(configContent, "</ca>")) {
            Logger::warn("OpenVPN config: incomplete embedded certificates");
            return false;
        }
    }
    
    // If external cert/key provided, validate format
    if (!certificate.empty()) {
        if (certificate.find("BEGIN CERTIFICATE") == std::string::npos ||
            certificate.find("END CERTIFICATE") == std::string::npos) {
            Logger::warn("OpenVPN: invalid certificate format");
            return false;
        }
    }
    
    if (!privateKey.empty()) {
        if (privateKey.find("BEGIN") == std::string::npos ||
            privateKey.find("END") == std::string::npos) {
            Logger::warn("OpenVPN: invalid private key format");
            return false;
        }
    }
    
    return true;
}

bool VpnService::validateWireGuardConfig(const std::string& configContent) const {
    // Check for required WireGuard sections
    if (!hasConfigLine(configContent, "[Interface]")) {
        Logger::warn("WireGuard config: missing [Interface] section");
        return false;
    }
    
    // Check for required Interface settings
    if (!hasConfigLine(configContent, "PrivateKey") && 
        !hasConfigLine(configContent, "privatekey")) {
        Logger::warn("WireGuard config: missing PrivateKey");
        return false;
    }
    
    if (!hasConfigLine(configContent, "Address") && 
        !hasConfigLine(configContent, "address")) {
        Logger::warn("WireGuard config: missing Address");
        return false;
    }
    
    // For clients, check for Peer section
    if (!hasConfigLine(configContent, "[Peer]") && 
        !hasConfigLine(configContent, "[peer]")) {
        Logger::warn("WireGuard config: missing [Peer] section");
        return false;
    }
    
    return true;
}

bool VpnService::validateIPSecConfig(const std::string& configContent) const {
    // Check for connection definitions
    if (!hasConfigLine(configContent, "conn ") && 
        !hasConfigLine(configContent, "config ")) {
        Logger::warn("IPSec config: missing connection definition");
        return false;
    }
    
    // Basic validation - IPSec configs vary widely
    if (configContent.length() < 50) {
        Logger::warn("IPSec config: configuration too short");
        return false;
    }
    
    return true;
}

bool VpnService::validateL2TPConfig(const std::string& configContent) const {
    // Check for LAC or LNS definition
    if (!hasConfigLine(configContent, "[lac ") && 
        !hasConfigLine(configContent, "[lns ")) {
        Logger::warn("L2TP config: missing LAC or LNS definition");
        return false;
    }
    
    // Check for lcp-echo or similar keep-alive
    if (!hasConfigLine(configContent, "lcp-echo") && 
        !hasConfigLine(configContent, "idle")) {
        Logger::warn("L2TP config: missing keep-alive settings");
        return false;
    }
    
    return true;
}

bool VpnService::validatePPTPConfig(const std::string& configContent) const {
    // PPTP configs are typically simple, mainly check for server address
    if (!hasConfigLine(configContent, "server") && 
        !hasConfigLine(configContent, "remote")) {
        Logger::warn("PPTP config: missing server/remote directive");
        return false;
    }
    
    return true;
}

bool VpnService::validateOpenConnectConfig(const std::string& configContent) const {
    // OpenConnect is often command-based, check for server address
    if (!hasConfigLine(configContent, "server") && 
        !hasConfigLine(configContent, "vpnhost") &&
        !hasConfigLine(configContent, "URL")) {
        Logger::warn("OpenConnect config: missing server/vpnhost/URL");
        return false;
    }
    
    return true;
}

VpnService::ConnectionResult VpnService::testConnection(
    const std::string& vpnType,
    const std::string& configContent,
    const std::string& certificate,
    const std::string& privateKey
) {
    ConnectionResult result;
    result.connected = false;
    
    // Input validation
    if (configContent.empty()) {
        result.message = "VPN configuration cannot be empty";
        result.errorCode = "EMPTY_CONFIG";
        return result;
    }
    
    if (configContent.length() < 10) {
        result.message = "VPN configuration too short";
        result.errorCode = "INVALID_CONFIG";
        return result;
    }
    
    try {
        VpnType type = parseVpnType(vpnType);
        
        bool isValid = false;
        std::string validationMessage;
        
        switch (type) {
            case VpnType::OpenVPN:
                isValid = validateOpenVpnConfig(configContent, certificate, privateKey);
                validationMessage = isValid ? 
                    "OpenVPN configuration is valid" : 
                    "OpenVPN configuration validation failed";
                break;
                
            case VpnType::WireGuard:
                isValid = validateWireGuardConfig(configContent);
                validationMessage = isValid ? 
                    "WireGuard configuration is valid" : 
                    "WireGuard configuration validation failed";
                break;
                
            case VpnType::IPSec:
                isValid = validateIPSecConfig(configContent);
                validationMessage = isValid ? 
                    "IPSec configuration is valid" : 
                    "IPSec configuration validation failed";
                break;
                
            case VpnType::L2TP:
                isValid = validateL2TPConfig(configContent);
                validationMessage = isValid ? 
                    "L2TP configuration is valid" : 
                    "L2TP configuration validation failed";
                break;
                
            case VpnType::PPTP:
                isValid = validatePPTPConfig(configContent);
                validationMessage = isValid ? 
                    "PPTP configuration is valid" : 
                    "PPTP configuration validation failed";
                break;
                
            case VpnType::OpenConnect:
                isValid = validateOpenConnectConfig(configContent);
                validationMessage = isValid ? 
                    "OpenConnect configuration is valid" : 
                    "OpenConnect configuration validation failed";
                break;
                
            default:
                result.message = "Unknown VPN type: " + vpnType;
                result.errorCode = "UNKNOWN_VPN_TYPE";
                return result;
        }
        
        if (isValid) {
            result.connected = true;
            result.message = validationMessage;
            result.errorCode = "";
            Logger::info("VPN configuration test passed for type: {}", vpnType);
        } else {
            result.connected = false;
            result.message = validationMessage;
            result.errorCode = "VALIDATION_FAILED";
            Logger::warn("VPN configuration validation failed: {}", vpnType);
        }
        
        return result;
        
    } catch (const std::exception& e) {
        result.message = std::string("VPN configuration test failed: ") + e.what();
        result.errorCode = "EXCEPTION";
        Logger::error("VPN configuration test exception: {}", e.what());
        return result;
    }
}

} // namespace baludesk
