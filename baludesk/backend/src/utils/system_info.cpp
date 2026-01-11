#include "system_info.h"
#include "logger.h"
#include "../api/http_client.h"
#include "settings_manager.h"
#include <nlohmann/json.hpp>
#include <windows.h>
#include <psapi.h>
#include <thread>
#include <chrono>
#include <filesystem>

#pragma comment(lib, "psapi.lib")
#pragma comment(lib, "kernel32.lib")

namespace baludesk {

SystemInfo SystemInfoCollector::getSystemInfo() {
    SystemInfo info{};
    info.cpu = CpuInfo{0.0, 0, 0};
    info.memory = MemoryInfo{0, 0, 0};
    info.disk = DiskInfo{0, 0, 0};
    info.uptime = 0;
    info.serverUptime = 0;
    
    try {
        info.cpu = getCpuInfo();
        info.memory = getMemoryInfo();
        // Use aggregated disk information across all fixed drives
        info.disk = getAggregateDiskInfo();
        info.uptime = getUptime();

        // Try to fetch server (Python backend) uptime from the REST API
        try {
            using json = nlohmann::json;
            std::string serverBase = baludesk::SettingsManager::getInstance().getServerUrl();
            int serverPort = baludesk::SettingsManager::getInstance().getServerPort();
            // If serverBase does not include an explicit port, append the configured port
            size_t schemePos = serverBase.find("//");
            size_t hostPortPos = std::string::npos;
            if (schemePos != std::string::npos) {
                hostPortPos = serverBase.find(':', schemePos + 2);
            }
            if (hostPortPos == std::string::npos) {
                // remove trailing slash if present
                if (!serverBase.empty() && serverBase.back() == '/') serverBase.pop_back();
                serverBase += ":" + std::to_string(serverPort);
            }

            baludesk::HttpClient client(serverBase);
            // Increase timeout to 5s and perform retries with exponential backoff
            client.setTimeout(5); // seconds

            const int maxAttempts = 3;
            int attempt = 0;
            int backoffMs = 200;
            bool got = false;

            for (; attempt < maxAttempts; ++attempt) {
                try {
                    // Use absolute URL to avoid baseUrl_ concatenation issues
                    std::string resp = client.get(serverBase + "/api/system/info/local");
                    Logger::debug("Server /api/system/info/local response: {}", resp);
                    auto j = json::parse(resp);
                    if (j.contains("uptime")) {
                        double su = j["uptime"].get<double>();
                        if (su < 0) su = 0;
                        info.serverUptime = static_cast<uint64_t>(su);
                        Logger::debug("Fetched server uptime: {} s (attempt {})", info.serverUptime, attempt + 1);
                        got = true;
                        break;
                    }
                    // If the response doesn't contain uptime, treat as failure and retry
                    Logger::debug("Server uptime response missing 'uptime' field (attempt {})", attempt + 1);
                } catch (const std::exception& e) {
                    Logger::debug("Could not fetch server uptime (attempt {}): {}", attempt + 1, e.what());
                }

                // exponential backoff before next attempt
                if (attempt + 1 < maxAttempts) {
                    std::this_thread::sleep_for(std::chrono::milliseconds(backoffMs));
                    backoffMs *= 2;
                }
            }

            if (!got) {
                Logger::debug("Failed to fetch server uptime after {} attempts", maxAttempts);
            }
        } catch (const std::exception& e) {
            Logger::debug("Server uptime fetch skipped: {}", e.what());
        }
        
        Logger::debug("System info collected: CPU {}%, RAM {}/{} MB, Uptime {} s",
                     info.cpu.usage,
                     info.memory.used / (1024 * 1024),
                     info.memory.total / (1024 * 1024),
                     info.uptime);
    } catch (const std::exception& e) {
        Logger::error("Failed to collect system info: {}", e.what());
    }
    
    return info;
}

nlohmann::json SystemInfoCollector::toJson(const SystemInfo& info) {
    using json = nlohmann::json;
    
    return json{
        {"cpu", {
            {"usage", info.cpu.usage},
            {"cores", info.cpu.cores},
            {"frequency", info.cpu.frequency}
        }},
        {"memory", {
            {"total", info.memory.total},
            {"used", info.memory.used},
            {"available", info.memory.available}
        }},
        {"disk", {
            {"total", info.disk.total},
            {"used", info.disk.used},
            {"available", info.disk.available}
        }},
        {"uptime", info.uptime},
        {"serverUptime", info.serverUptime}
    };
}

CpuInfo SystemInfoCollector::getCpuInfo() {
    CpuInfo info = {0.0, 0, 0};
    
    try {
        // Get number of processors
        SYSTEM_INFO sysInfo;
        GetSystemInfo(&sysInfo);
        info.cores = sysInfo.dwNumberOfProcessors;
        
        // Get CPU frequency (simplified - reading from registry)
        HKEY hKey;
        if (RegOpenKeyExA(HKEY_LOCAL_MACHINE, 
                         "HARDWARE\\DESCRIPTION\\System\\CentralProcessor\\0",
                         0, KEY_READ, &hKey) == ERROR_SUCCESS) {
            DWORD freq = 0;
            DWORD size = sizeof(freq);
            
            if (RegQueryValueExA(hKey, "~MHz", NULL, NULL, 
                                (LPBYTE)&freq, &size) == ERROR_SUCCESS) {
                info.frequency = freq;
            }
            RegCloseKey(hKey);
        }
        
        // Get CPU usage using Process performance counter (simplified)
        // For now, use a basic estimate based on system uptime
        // A more robust implementation would use WMI or Performance Counters
        
        // Get CPU load from kernel processor time
        // Using GetSystemTimes for a quick estimate
        FILETIME idleTime, kernelTime, userTime;
        static FILETIME lastIdleTime = {0}, lastKernelTime = {0}, lastUserTime = {0};
        
        if (GetSystemTimes(&idleTime, &kernelTime, &userTime)) {
            ULARGE_INTEGER idle, kernel, user;
            idle.LowPart = idleTime.dwLowDateTime;
            idle.HighPart = idleTime.dwHighDateTime;
            kernel.LowPart = kernelTime.dwLowDateTime;
            kernel.HighPart = kernelTime.dwHighDateTime;
            user.LowPart = userTime.dwLowDateTime;
            user.HighPart = userTime.dwHighDateTime;
            
            if (lastKernelTime.dwLowDateTime != 0) {
                ULARGE_INTEGER lastIdle, lastKernel, lastUser;
                lastIdle.LowPart = lastIdleTime.dwLowDateTime;
                lastIdle.HighPart = lastIdleTime.dwHighDateTime;
                lastKernel.LowPart = lastKernelTime.dwLowDateTime;
                lastKernel.HighPart = lastKernelTime.dwHighDateTime;
                lastUser.LowPart = lastUserTime.dwLowDateTime;
                lastUser.HighPart = lastUserTime.dwHighDateTime;
                
                ULONGLONG idleDiff = idle.QuadPart - lastIdle.QuadPart;
                ULONGLONG kernelDiff = kernel.QuadPart - lastKernel.QuadPart;
                ULONGLONG userDiff = user.QuadPart - lastUser.QuadPart;
                ULONGLONG totalDiff = kernelDiff + userDiff;
                
                if (totalDiff > 0) {
                    info.usage = 100.0 * (1.0 - (double)idleDiff / totalDiff);
                    if (info.usage < 0) info.usage = 0;
                    if (info.usage > 100) info.usage = 100;
                }
            }
            
            lastIdleTime = idleTime;
            lastKernelTime = kernelTime;
            lastUserTime = userTime;
        }
        
        Logger::debug("CPU Info: {} cores, {} MHz, {} % usage",
                     info.cores, info.frequency, info.usage);
        
    } catch (const std::exception& e) {
        Logger::error("Failed to get CPU info: {}", e.what());
    }
    
    return info;
}

MemoryInfo SystemInfoCollector::getMemoryInfo() {
    MemoryInfo info = {0, 0, 0};
    
    try {
        MEMORYSTATUSEX statex;
        statex.dwLength = sizeof(statex);
        
        if (GlobalMemoryStatusEx(&statex)) {
            info.total = statex.ullTotalPhys;
            info.available = statex.ullAvailPhys;
            info.used = info.total - info.available;
            
            Logger::debug("Memory Info: {} / {} MB",
                         info.used / (1024 * 1024),
                         info.total / (1024 * 1024));
        }
    } catch (const std::exception& e) {
        Logger::error("Failed to get memory info: {}", e.what());
    }
    
    return info;
}

DiskInfo SystemInfoCollector::getDiskInfo(const std::string& path) {
    DiskInfo info = {0, 0, 0};
    
    try {
        ULARGE_INTEGER freeBytesAvailable, totalBytes, totalFreeBytes;
        
        if (GetDiskFreeSpaceExA(path.c_str(),
                               &freeBytesAvailable,
                               &totalBytes,
                               &totalFreeBytes)) {
            info.total = totalBytes.QuadPart;
            info.available = freeBytesAvailable.QuadPart;
            info.used = info.total - info.available;
            
            Logger::debug("Disk Info ({}): {} / {} MB",
                         path,
                         info.used / (1024 * 1024),
                         info.total / (1024 * 1024));
        }
    } catch (const std::exception& e) {
        Logger::error("Failed to get disk info: {}", e.what());
    }
    
    return info;
}

DiskInfo SystemInfoCollector::getAggregateDiskInfo() {
    DiskInfo aggregate = {0, 0, 0};
    try {
        DWORD bufSize = GetLogicalDriveStringsA(0, NULL);
        if (bufSize == 0) return aggregate;

        std::string buffer(bufSize, '\0');
        if (GetLogicalDriveStringsA(bufSize, &buffer[0]) == 0) return aggregate;

        const char* p = buffer.c_str();
        while (*p) {
            std::string drive = p; // e.g., "C:\\"
            UINT type = GetDriveTypeA(drive.c_str());
            if (type == DRIVE_FIXED || type == DRIVE_REMOTE) {
                ULARGE_INTEGER freeBytesAvailable, totalBytes, totalFreeBytes;
                if (GetDiskFreeSpaceExA(drive.c_str(), &freeBytesAvailable, &totalBytes, &totalFreeBytes)) {
                    aggregate.total += totalBytes.QuadPart;
                    aggregate.available += freeBytesAvailable.QuadPart;
                }
            }
            // advance to next null-terminated string
            p += drive.size() + 1;
        }

        if (aggregate.total >= aggregate.available) {
            aggregate.used = aggregate.total - aggregate.available;
        } else {
            aggregate.used = 0;
        }

        Logger::debug("Aggregated Disk Info: used={} MB total={} MB", aggregate.used / (1024 * 1024), aggregate.total / (1024 * 1024));
    } catch (const std::exception& e) {
        Logger::error("Failed to aggregate disk info: {}", e.what());
    }
    return aggregate;
}

uint64_t SystemInfoCollector::getUptime() {
    try {
        // Use GetTickCount64 to avoid 49.7-day wraparound and get milliseconds since system start
        ULONGLONG tickCount = GetTickCount64();
        uint64_t uptime = static_cast<uint64_t>(tickCount / 1000ULL); // Convert to seconds
        
        Logger::debug("System uptime: {} seconds", uptime);
        return uptime;
    } catch (const std::exception& e) {
        Logger::error("Failed to get uptime: {}", e.what());
        return 0;
    }
}

} // namespace baludesk
