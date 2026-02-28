/**
 * Feature flags based on build-time device mode.
 *
 * `__DEVICE_MODE__` is replaced at build time by Vite's `define` option.
 * Dead code is eliminated by the minifier (e.g. `"pi" === "desktop"` → `false`).
 */
export const FEATURES = {
  // Available on both desktop and Pi
  dashboard: true,
  systemMonitor: true,

  // Desktop/NAS only — tree-shaken out of Pi builds
  fileManager: __DEVICE_MODE__ === 'desktop',
  userManagement: __DEVICE_MODE__ === 'desktop',
  adminDatabase: __DEVICE_MODE__ === 'desktop',
  raidManagement: __DEVICE_MODE__ === 'desktop',
  vpnManagement: __DEVICE_MODE__ === 'desktop',
  fanControl: __DEVICE_MODE__ === 'desktop',
  powerManagement: __DEVICE_MODE__ === 'desktop',
  fileSharing: __DEVICE_MODE__ === 'desktop',
  schedulers: __DEVICE_MODE__ === 'desktop',
  pihole: __DEVICE_MODE__ === 'desktop',
  plugins: __DEVICE_MODE__ === 'desktop',
  settings: __DEVICE_MODE__ === 'desktop',
  logging: __DEVICE_MODE__ === 'desktop',
  devices: __DEVICE_MODE__ === 'desktop',
  sync: __DEVICE_MODE__ === 'desktop',
  cloudImport: __DEVICE_MODE__ === 'desktop',
  updates: __DEVICE_MODE__ === 'desktop',
  notifications: __DEVICE_MODE__ === 'desktop',
  apiCenter: __DEVICE_MODE__ === 'desktop',

  // Pi only — tree-shaken out of desktop builds
  wolButton: __DEVICE_MODE__ === 'pi',
  snapshotView: __DEVICE_MODE__ === 'pi',
  inboxStatus: __DEVICE_MODE__ === 'pi',
  piDashboard: __DEVICE_MODE__ === 'pi',
} as const;

export const isDesktop = __DEVICE_MODE__ === 'desktop';
export const isPi = __DEVICE_MODE__ === 'pi';
