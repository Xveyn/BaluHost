export type { ApiEndpoint, ApiSection } from './types';
export { methodColors } from './types';

import type { ApiSection } from './types';
import { coreSections } from './sections-core';
import { sharingSections } from './sections-sharing';
import { deviceSections } from './sections-devices';
import { systemSections } from './sections-system';
import { adminSections } from './sections-admin';
import { featureSections } from './sections-features';

export const apiSections = [
  ...coreSections,
  ...sharingSections,
  ...deviceSections,
  ...systemSections,
  ...adminSections,
  ...featureSections,
];

export interface ApiCategory {
  id: string;
  label: string;
  sections: ApiSection[];
}

export const apiCategories: ApiCategory[] = [
  { id: 'core', label: 'Core', sections: coreSections },
  { id: 'sharing', label: 'Sharing', sections: sharingSections },
  { id: 'devices', label: 'Devices', sections: deviceSections },
  { id: 'system', label: 'System', sections: systemSections },
  { id: 'admin', label: 'Admin', sections: adminSections },
  { id: 'features', label: 'Features', sections: featureSections },
];
