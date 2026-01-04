#pragma once

#include <string>
#include <vector>
#include <nlohmann/json.hpp>

namespace baludesk {

struct RaidDevice {
    std::string name;
    std::string state;  // active, failed, spare, etc.

    nlohmann::json toJson() const {
        return nlohmann::json{
            {"name", name},
            {"state", state}
        };
    }
};

struct RaidArray {
    std::string name;
    std::string level;  // RAID0, RAID1, RAID5, RAID6, RAID10
    std::string status; // optimal, degraded, rebuilding, inactive
    long long size_bytes = 0;
    double resync_progress = 0.0;  // 0-100
    std::vector<RaidDevice> devices;

    nlohmann::json toJson() const {
        nlohmann::json devicesJson = nlohmann::json::array();
        for (const auto& dev : devices) {
            devicesJson.push_back(dev.toJson());
        }

        return nlohmann::json{
            {"name", name},
            {"level", level},
            {"status", status},
            {"size_bytes", size_bytes},
            {"resync_progress", resync_progress},
            {"devices", devicesJson}
        };
    }
};

struct RaidStatus {
    std::vector<RaidArray> arrays;
    bool dev_mode = false;

    nlohmann::json toJson() const {
        nlohmann::json arraysJson = nlohmann::json::array();
        for (const auto& array : arrays) {
            arraysJson.push_back(array.toJson());
        }

        return nlohmann::json{
            {"arrays", arraysJson},
            {"dev_mode", dev_mode}
        };
    }
};

class RaidInfoCollector {
public:
    static RaidStatus getRaidStatus();
    static RaidStatus getMockRaidStatus();

private:
    static RaidStatus parseRaidStatus();
};
}  // namespace baludesk