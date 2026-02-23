import { useSyncExternalStore } from 'react';
import { subscribe, getSnapshot, setByteUnitMode, type ByteUnitMode } from '../lib/byteUnits';

export function useByteUnitMode(): [ByteUnitMode, (mode: ByteUnitMode) => void] {
  const mode = useSyncExternalStore(subscribe, getSnapshot);
  return [mode, setByteUnitMode];
}
