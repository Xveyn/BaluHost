/**
 * API client for energy monitoring and statistics
 */

import { apiClient } from '../lib/api';

// TypeScript interfaces
export interface EnergyPeriodStats {
  device_id: number;
  device_name: string;
  start_time: string;
  end_time: string;
  samples_count: number;
  avg_watts: number;
  min_watts: number;
  max_watts: number;
  total_energy_kwh: number;
  uptime_percentage: number;
  downtime_minutes: number;
}

export interface HourlySample {
  timestamp: string;
  avg_watts: number;
  sample_count: number;
}

export interface EnergyDashboard {
  device_id: number;
  device_name: string;
  today: EnergyPeriodStats | null;
  week: EnergyPeriodStats | null;
  month: EnergyPeriodStats | null;
  hourly_samples: HourlySample[];
  current_watts: number;
  is_online: boolean;
  last_updated: string;
}

export interface EnergyCostEstimate {
  device_id: number;
  device_name: string;
  period_name: string;
  total_kwh: number;
  cost_per_kwh: number;
  estimated_cost: number;
  currency: string;
}

// API Functions

export async function getEnergyDashboard(deviceId: number): Promise<EnergyDashboard> {
  const response = await apiClient.get<EnergyDashboard>(`/api/energy/dashboard/${deviceId}`);
  return response.data;
}

export async function getTodayStats(deviceId: number): Promise<EnergyPeriodStats | null> {
  const response = await apiClient.get<EnergyPeriodStats | null>(`/api/energy/stats/${deviceId}/today`);
  return response.data;
}

export async function getWeekStats(deviceId: number): Promise<EnergyPeriodStats | null> {
  const response = await apiClient.get<EnergyPeriodStats | null>(`/api/energy/stats/${deviceId}/week`);
  return response.data;
}

export async function getMonthStats(deviceId: number): Promise<EnergyPeriodStats | null> {
  const response = await apiClient.get<EnergyPeriodStats | null>(`/api/energy/stats/${deviceId}/month`);
  return response.data;
}

export async function getEnergyCost(
  deviceId: number,
  period: 'today' | 'week' | 'month' = 'today',
  costPerKwh: number = 0.40,
  currency: string = 'EUR'
): Promise<EnergyCostEstimate> {
  const response = await apiClient.get<EnergyCostEstimate>(
    `/api/energy/cost/${deviceId}?period=${period}&cost_per_kwh=${costPerKwh}&currency=${currency}`
  );
  return response.data;
}

export async function getHourlySamples(
  deviceId: number,
  hours: number = 24
): Promise<HourlySample[]> {
  const response = await apiClient.get<HourlySample[]>(
    `/api/energy/hourly/${deviceId}?hours=${hours}`
  );
  return response.data;
}

// Energy Price Configuration
export interface EnergyPriceConfig {
  id: number;
  cost_per_kwh: number;
  currency: string;
  updated_at: string;
  updated_by_user_id: number | null;
}

export interface EnergyPriceConfigUpdate {
  cost_per_kwh: number;
  currency: string;
}

export async function getEnergyPriceConfig(): Promise<EnergyPriceConfig> {
  const response = await apiClient.get<EnergyPriceConfig>('/api/energy/price');
  return response.data;
}

export async function updateEnergyPriceConfig(
  data: EnergyPriceConfigUpdate
): Promise<EnergyPriceConfig> {
  const response = await apiClient.put<EnergyPriceConfig>('/api/energy/price', data);
  return response.data;
}

// Cumulative Energy Data
export interface CumulativeDataPoint {
  timestamp: string;
  cumulative_kwh: number;
  cumulative_cost: number;
  instant_watts: number;
}

export interface CumulativeEnergyResponse {
  device_id: number;
  device_name: string;
  period: string;
  cost_per_kwh: number;
  currency: string;
  total_kwh: number;
  total_cost: number;
  data_points: CumulativeDataPoint[];
}

export async function getCumulativeEnergy(
  deviceId: number,
  period: 'today' | 'week' | 'month' = 'today'
): Promise<CumulativeEnergyResponse> {
  const response = await apiClient.get<CumulativeEnergyResponse>(
    `/api/energy/cumulative/${deviceId}?period=${period}`
  );
  return response.data;
}
