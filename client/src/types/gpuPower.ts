export type GpuPowerState = "active" | "standby" | "deep_idle";

export type AmdProfileMode =
  | "BOOTUP_DEFAULT"
  | "POWER_SAVING"
  | "VIDEO"
  | "VR"
  | "COMPUTE"
  | "CUSTOM"
  | "3D_FULL_SCREEN";

export interface AmdStateConfig {
  performance_level?: string | null;
  profile_mode?: AmdProfileMode | null;
}

export interface NvidiaStateConfig {
  min_clock_mhz?: number | null;
  max_clock_mhz?: number | null;
  power_limit_watts?: number | null;
}

export interface GpuPowerConfig {
  enabled: boolean;
  idle_window_seconds: number;
  deep_idle_extra_seconds: number;
  deep_idle_grace_seconds: number;
  usage_threshold_percent: number;
  monitor_interval_seconds: number;
  amd_active: AmdStateConfig;
  amd_standby: AmdStateConfig;
  amd_deep_idle: AmdStateConfig;
  nvidia_active: NvidiaStateConfig;
  nvidia_standby: NvidiaStateConfig;
  nvidia_deep_idle: NvidiaStateConfig;
}

export interface GpuPowerDemandInfo {
  source: string;
  registered_at: string;
  expires_at: string | null;
  description: string | null;
}

export interface GpuPowerStatus {
  enabled: boolean;
  detected: boolean;
  vendor: string | null;
  current_state: GpuPowerState;
  last_transition: string | null;
  last_reason: string | null;
  active_demands: GpuPowerDemandInfo[];
  has_write_permission: boolean;
  estimated_power_watts: number | null;
  display_count: number;
  usage_percent: number | null;
}

export interface GpuPowerCapabilities {
  vendor: string | null;
  amd_performance_levels: string[];
  amd_profile_modes: string[];
  nvidia_min_clock_mhz: number | null;
  nvidia_max_clock_mhz: number | null;
  nvidia_min_power_watts: number | null;
  nvidia_max_power_watts: number | null;
  nvidia_default_power_watts: number | null;
}

export interface GpuPowerHistoryEntry {
  timestamp: string;
  state: GpuPowerState;
  previous_state: GpuPowerState | null;
  reason: string;
  source: string | null;
  power_watts_at_transition: number | null;
}

export interface GpuPowerHistoryResponse {
  entries: GpuPowerHistoryEntry[];
  total: number;
}
