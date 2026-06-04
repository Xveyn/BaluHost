import type { ElementType } from 'react'
import { Cpu, MemoryStick, Network, HardDrive, Activity, Zap, Clock, MonitorPlay, Database } from 'lucide-react'

export interface MetricDisplayConfig {
  labelKey: string
  icon: ElementType
  color: string
}

export const METRIC_CONFIG: Record<string, MetricDisplayConfig> = {
  cpu: { labelKey: 'admin:databaseStats.metrics.cpu', icon: Cpu, color: 'blue' },
  memory: { labelKey: 'admin:databaseStats.metrics.memory', icon: MemoryStick, color: 'emerald' },
  network: { labelKey: 'admin:databaseStats.metrics.network', icon: Network, color: 'purple' },
  disk_io: { labelKey: 'admin:databaseStats.metrics.diskIo', icon: HardDrive, color: 'amber' },
  process: { labelKey: 'admin:databaseStats.metrics.process', icon: Activity, color: 'rose' },
  power: { labelKey: 'admin:databaseStats.metrics.power', icon: Zap, color: 'amber' },
  uptime: { labelKey: 'admin:databaseStats.metrics.uptime', icon: Clock, color: 'blue' },
  gpu: { labelKey: 'admin:databaseStats.metrics.gpu', icon: MonitorPlay, color: 'emerald' },
}

export const DEFAULT_METRIC_CONFIG: MetricDisplayConfig = {
  labelKey: '',
  icon: Database,
  color: 'slate',
}
