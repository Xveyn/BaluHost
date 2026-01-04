#include "system_info.h"
#include "logger.h"
#include <windows.h>
#include <psapi.h>
#include <filesystem>

#pragma comment(lib, "psapi.lib")
#pragma comment(lib, "kernel32.lib")

namespace baludesk {

SystemInfo SystemInfoCollector::getSystemInfo() {
    SystemInfo info;
    
    try {
        info.cpu = getCpuInfo();
        info.memory = getMemoryInfo();
        info.disk = getDiskInfo();
        info.uptime = getUptime();
        
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
        {"uptime", info.uptime}
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

uint64_t SystemInfoCollector::getUptime() {
    try {
        // GetTickCount returns milliseconds since system start
        DWORD tickCount = GetTickCount();
        uint64_t uptime = tickCount / 1000; // Convert to seconds
        
        Logger::debug("System uptime: {} seconds", uptime);
        return uptime;
    } catch (const std::exception& e) {
        Logger::error("Failed to get uptime: {}", e.what());
        return 0;
    }
}

} // namespace baludesk
