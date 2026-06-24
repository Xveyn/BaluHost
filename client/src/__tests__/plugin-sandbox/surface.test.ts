import { describe, it, expect } from 'vitest';
import { buildSurface } from '../../plugin-runtime/surface';

describe('buildSurface', () => {
  it('exposes React, the ui primitive set, icons, and utils', () => {
    const s = buildSurface();
    expect(typeof s.React.createElement).toBe('function');
    expect(typeof s.hooks.useState).toBe('function');
    // full primitive set (matches the old initPluginSDK surface)
    for (const k of ['Button','Card','CardHeader','CardContent','CardFooter','Badge','Modal',
      'Input','Textarea','Select','ProgressBar','Spinner','LoadingOverlay','EmptyState',
      'Tabs','TabPanel','ByteSizeInput']) {
      expect(s.ui[k as keyof typeof s.ui], `ui.${k}`).toBeTruthy();
    }
    expect(typeof s.icons).toBe('object');
    expect(typeof s.utils.formatBytes).toBe('function');
    expect(s.utils.cn('a', false, 'b')).toBe('a b');
  });
});
