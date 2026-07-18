import { useTranslation } from 'react-i18next';
import { useAuth } from '../contexts/AuthContext';
import { usePlugins } from '../contexts/PluginContext';
import { isPi } from '../lib/features';
import { resolvePluginString } from '../lib/pluginI18n';
import { buildNavItems, PI_NAV_PATHS, pluginNavIcon, type LayoutNavItem } from '../components/layout/layoutNavConfig';

export function useLayoutNav(): { allNavItems: LayoutNavItem[]; adminStartIndex: number } {
  const { t } = useTranslation('common');
  const { isAdmin } = useAuth();
  const { pluginNavItems } = usePlugins();

  const navItems = buildNavItems(t);

  // Add plugin navigation items
  const pluginItems: LayoutNavItem[] = isPi ? [] : pluginNavItems
    .filter((item) => !item.admin_only || isAdmin)
    .map((item) => ({
      path: `/plugins/${item.path}`,
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      label: resolvePluginString((item as any)._translations, `nav.${item.label}`, item.label),
      description: 'Plugin',
      icon: pluginNavIcon,
      adminOnly: item.admin_only,
      isPlugin: true,
    }));

  // Filter nav items based on user role (and device mode)
  const filteredNavItems = navItems
    .filter((item) => (isPi ? PI_NAV_PATHS.has(item.path) : !item.adminOnly || isAdmin));

  // Find where admin items start (for showing separator)
  const adminStartIndex = isPi ? -1 : filteredNavItems.findIndex((item) => item.adminOnly);

  return { allNavItems: [...filteredNavItems, ...pluginItems], adminStartIndex };
}
