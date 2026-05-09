/**
 * Sleep Mode Page
 *
 * Combines the sleep mode control panel, core operating hours configuration,
 * legacy sleep config, and history into a single page rendered as a tab in
 * SystemControlPage.
 */

import { OsSleepSettingsBanner } from '../components/power/OsSleepSettingsBanner';
import { SleepModePanel } from '../components/power/SleepModePanel';
import { AlwaysAwakePanel } from '../components/power/AlwaysAwakePanel';
import { CoreUptimePanel } from '../components/power/CoreUptimePanel';
import { SleepConfigPanel } from '../components/power/SleepConfigPanel';
import { SleepHistoryTable } from '../components/power/SleepHistoryTable';

export default function SleepMode() {
  return (
    <div className="space-y-6">
      <OsSleepSettingsBanner />
      <SleepModePanel />
      <AlwaysAwakePanel />
      <CoreUptimePanel />
      <SleepConfigPanel />
      <SleepHistoryTable />
    </div>
  );
}
