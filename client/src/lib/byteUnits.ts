/**
 * Module-level store for byte unit display preference (binary vs decimal).
 *
 * Works like i18n — formatBytes() reads the current mode directly,
 * no React Context required. React components that need reactivity
 * use useSyncExternalStore via the useByteUnitMode hook.
 */

export type ByteUnitMode = 'binary' | 'decimal';

interface UnitConfig {
  divisor: number;
  units: string[];
}

const STORAGE_KEY = 'baluhost-byte-units';

const UNIT_CONFIGS: Record<ByteUnitMode, UnitConfig> = {
  binary:  { divisor: 1024, units: ['B', 'KiB', 'MiB', 'GiB', 'TiB', 'PiB'] },
  decimal: { divisor: 1000, units: ['B', 'KB', 'MB', 'GB', 'TB', 'PB'] },
};

let _mode: ByteUnitMode = 'binary';

// Init from localStorage (safe for SSR / test environments)
try {
  const stored = localStorage.getItem(STORAGE_KEY);
  if (stored === 'binary' || stored === 'decimal') _mode = stored;
} catch {
  // localStorage unavailable — keep default
}

const _listeners = new Set<() => void>();

export function getByteUnitMode(): ByteUnitMode {
  return _mode;
}

export function setByteUnitMode(mode: ByteUnitMode): void {
  if (mode === _mode) return;
  _mode = mode;
  try {
    localStorage.setItem(STORAGE_KEY, mode);
  } catch {
    // ignore
  }
  _listeners.forEach((cb) => cb());
}

export function getUnitConfig(mode: ByteUnitMode): UnitConfig {
  return UNIT_CONFIGS[mode];
}

// useSyncExternalStore API
export function subscribe(cb: () => void): () => void {
  _listeners.add(cb);
  return () => { _listeners.delete(cb); };
}

export function getSnapshot(): ByteUnitMode {
  return _mode;
}
