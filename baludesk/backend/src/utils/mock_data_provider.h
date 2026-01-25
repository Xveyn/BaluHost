#pragma once

#include "system_info.h"
#include "raid_info.h"

namespace baludesk {

/**
 * Power monitoring data structure
 */
struct PowerMonitoring {
    double currentPower;        // Current power consumption in Watts
    double energyToday;         // Total energy consumed today in kWh
    double trendDelta;          // Power trend delta in Watts (+/- from average)
    int deviceCount;            // Number of monitored devices
    double maxPower;            // Maximum power capacity in Watts (for progress calculation)
};

/**
 * Provides mock/test data for development and testing
 * Used when devMode is set to "mock" to return predictable test data
 */
class MockDataProvider {
public:
    /**
     * Get mock system information for dev-mode testing
     * Returns fixed test values: 45% CPU, 8 cores, 16GB RAM, 1TB disk
     * @return SystemInfo struct with mock data
     */
    static SystemInfo getMockSystemInfo();

    /**
     * Get mock RAID status for dev-mode testing
     * Returns 2 arrays: md0 (RAID1, optimal), md1 (RAID5, rebuilding @ 67.5%)
     * @return RaidStatus struct with mock data
     */
    static RaidStatus getMockRaidStatus();

    /**
     * Get mock power monitoring data for dev-mode testing
     * Returns: 87.3W current, 1.85 kWh today, -5.2W trend (decreasing), 3 devices
     * @return PowerMonitoring struct with mock data
     */
    static PowerMonitoring getMockPowerMonitoring();
};

} // namespace baludesk
