#pragma once

#include <nlohmann/json.hpp>
#include <cstdint>

namespace baludesk {

struct CpuInfo {
    double usage;          // CPU usage in percent (0-100)
    uint32_t cores;        // Number of CPU cores
    uint32_t frequency;    // CPU frequency in MHz
};

struct MemoryInfo {
    uint64_t total;        // Total RAM in bytes
    uint64_t used;         // Used RAM in bytes
    uint64_t available;    // Available RAM in bytes
};

struct DiskInfo {
    uint64_t total;        // Total disk space in bytes
    uint64_t used;         // Used disk space in bytes
    uint64_t available;    // Available disk space in bytes
};

struct SystemInfo {
    CpuInfo cpu;
    MemoryInfo memory;
    DiskInfo disk;
    uint64_t uptime;       // System uptime in seconds
};

class SystemInfoCollector {
public:
    /**
     * Get current system information
     * @return SystemInfo struct with current system metrics
     */
    static SystemInfo getSystemInfo();
    
    /**
     * Convert SystemInfo to JSON
     * @param info SystemInfo struct
     * @return JSON representation
     */
    static nlohmann::json toJson(const SystemInfo& info);

private:
    /**
     * Get CPU information (Windows implementation)
     */
    static CpuInfo getCpuInfo();
    
    /**
     * Get memory information (Windows implementation)
     */
    static MemoryInfo getMemoryInfo();
    
    /**
     * Get disk information (Windows implementation)
     * @param path Directory path to check (default: C:\)
     */
    static DiskInfo getDiskInfo(const std::string& path = "C:\\");
    
    /**
     * Get system uptime in seconds
     */
    static uint64_t getUptime();
};

} // namespace baludesk
