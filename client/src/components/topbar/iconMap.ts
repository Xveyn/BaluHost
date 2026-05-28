import {
  Zap, Shield, Upload, RefreshCw, HardDrive, Moon, Lock, Thermometer,
  Coffee, Clock, Save,
} from 'lucide-react';
import type { LucideIcon } from 'lucide-react';

const ICONS: Record<string, LucideIcon> = {
  Zap, Shield, Upload, RefreshCw, HardDrive, Moon, Lock, Thermometer, Coffee, Clock, Save,
};

export function resolveIcon(name: string | null | undefined): LucideIcon | null {
  if (!name) return null;
  return ICONS[name] ?? null;
}
