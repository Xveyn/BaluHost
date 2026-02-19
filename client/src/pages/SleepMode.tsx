/**
 * Sleep Mode Page
 *
 * Combines the sleep mode control panel, configuration, and history
 * into a single page rendered as a tab in SystemControlPage.
 */

import { SleepModePanel } from '../components/power/SleepModePanel';
import { SleepConfigPanel } from '../components/power/SleepConfigPanel';
import { SleepHistoryTable } from '../components/power/SleepHistoryTable';

export default function SleepMode() {
  return (
    <div className="space-y-6">
      {/* Status & Controls */}
      <SleepModePanel />

      {/* Configuration */}
      <SleepConfigPanel />

      {/* History */}
      <SleepHistoryTable />
    </div>
  );
}
