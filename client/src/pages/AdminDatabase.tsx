import { useState } from 'react'
import { AdminBadge } from '../components/ui/AdminBadge'
import { useAdminDatabaseBrowse } from '../hooks/useAdminDatabaseBrowse'
import DatabaseCategoryNav, { type CategoryType } from '../components/admin/admin-database/DatabaseCategoryNav'
import TableBrowser from '../components/admin/admin-database/TableBrowser'
import AnalyticsContent, { type AnalyticsTabType } from '../components/admin/admin-database/AnalyticsContent'

export default function AdminDatabase() {
  const [activeCategory, setActiveCategory] = useState<CategoryType>('browse')
  const [analyticsTab, setAnalyticsTab] = useState<AnalyticsTabType>('stats')

  const browse = useAdminDatabaseBrowse()

  return (
    <div className="space-y-6 min-w-0">
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3 sm:gap-4">
        <div className="flex items-center gap-3">
          <h1 className="text-2xl sm:text-3xl font-semibold text-white">
            Database Management
          </h1>
          <AdminBadge size="md" />
        </div>
        <p className="text-xs sm:text-sm text-slate-400">
          Control database access, view statistics, and manage maintenance
        </p>
      </div>

      {/* Two-Level Navigation */}
      <DatabaseCategoryNav
        activeCategory={activeCategory}
        onCategoryChange={setActiveCategory}
        analyticsTab={analyticsTab}
        onAnalyticsTabChange={setAnalyticsTab}
      />

      {/* Content */}
      {activeCategory === 'browse'
        ? <TableBrowser {...browse} />
        : <AnalyticsContent analyticsTab={analyticsTab} />}
    </div>
  )
}
