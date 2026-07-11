import { useTranslation } from 'react-i18next';
import { Users, Share2, Cloud } from 'lucide-react';
import { StatCard } from '../ui/StatCard';
import { formatBytes } from '../../lib/formatters';
import type { ShareStatistics } from '../../api/shares';
import type { CloudExportStatistics } from '../../api/cloud-export';
import type { SharesTab } from './types';

interface SharesStatCardsProps {
  activeTab: SharesTab;
  statistics: ShareStatistics | null;
  cloudStats: CloudExportStatistics | null;
}

export function SharesStatCards({ activeTab, statistics, cloudStats }: SharesStatCardsProps) {
  const { t } = useTranslation(['shares', 'common']);

  if (activeTab !== 'cloud-exports' && statistics) {
    return (
      <div className="grid grid-cols-1 min-[400px]:grid-cols-2 gap-3 sm:gap-5">
        <StatCard
          label={t('stats.userShares')}
          value={statistics.active_file_shares}
          subValue={t('stats.ofTotal', { total: statistics.total_file_shares })}
          color="purple"
          icon={<Users className="h-5 w-5 sm:h-6 sm:w-6 text-purple-400" />}
        />
        <StatCard
          label={t('stats.sharedWithMe')}
          value={statistics.files_shared_with_me}
          subValue={t('stats.filesAccessible')}
          color="amber"
          icon={<Share2 className="h-5 w-5 sm:h-6 sm:w-6 text-amber-400" />}
        />
      </div>
    );
  }

  if (activeTab === 'cloud-exports' && cloudStats) {
    return (
      <div className="grid grid-cols-1 min-[400px]:grid-cols-2 gap-3 sm:gap-5">
        <StatCard
          label={t('shares:cloudExport.activeShares', 'Active Cloud Shares')}
          value={cloudStats.active_exports}
          subValue={t('stats.ofTotal', { total: cloudStats.total_exports })}
          color="blue"
          icon={<Cloud className="h-5 w-5 sm:h-6 sm:w-6 text-blue-400" />}
        />
        <StatCard
          label={t('shares:cloudExport.uploadVolume', 'Upload Volume')}
          value={formatBytes(cloudStats.total_upload_bytes)}
          subValue={t('shares:cloudExport.totalUploaded', 'Total uploaded')}
          color="green"
          icon={<Cloud className="h-5 w-5 sm:h-6 sm:w-6 text-green-400" />}
        />
      </div>
    );
  }

  return null;
}
