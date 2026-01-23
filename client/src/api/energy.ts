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
