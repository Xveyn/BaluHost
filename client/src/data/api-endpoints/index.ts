export type { ApiEndpoint, ApiSection } from './types';
export { methodColors } from './types';

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
