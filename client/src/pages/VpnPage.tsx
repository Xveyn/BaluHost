import { useTranslation } from 'react-i18next';
import VpnManagement from '../components/VpnManagement';

export default function VpnPage() {
  const { t } = useTranslation('common');

  return (
    <div className="space-y-4 sm:space-y-6">
      <div>
        <h1 className="text-2xl sm:text-3xl font-semibold text-white">
          {t('navigation.vpnManagement')}
        </h1>
        <p className="mt-1 text-sm text-slate-400">
          {t('navigation.vpnManagementDesc')}
        </p>
      </div>

      <VpnManagement />
    </div>
  );
}
