import DatabaseStatsCards from '../DatabaseStatsCards'
import StorageAnalysisChart from '../StorageAnalysisChart'
import MonitoringHistoryViewer from '../MonitoringHistoryViewer'
import MaintenanceTools from '../MaintenanceTools'
import RetentionSettings from '../RetentionSettings'

export type AnalyticsTabType = 'stats' | 'storage' | 'history' | 'maintenance' | 'retention'

interface AnalyticsContentProps {
  analyticsTab: AnalyticsTabType
}

/**
 * Renders the active analytics sub-tab's card. Extracted verbatim from
 * AdminDatabase's `renderAnalyticsContent`.
 */
export default function AnalyticsContent({ analyticsTab }: AnalyticsContentProps) {
  switch (analyticsTab) {
    case 'stats':
      return (
        <div className="card">
          <DatabaseStatsCards autoRefresh={true} refreshInterval={30000} />
        </div>
      )
    case 'storage':
      return (
        <div className="card">
          <StorageAnalysisChart />
        </div>
      )
    case 'history':
      return (
        <div className="card">
          <MonitoringHistoryViewer />
        </div>
      )
    case 'maintenance':
      return (
        <div className="card">
          <MaintenanceTools />
        </div>
      )
    case 'retention':
      return (
        <div className="card">
          <RetentionSettings />
        </div>
      )
    default:
      return null
  }
}
