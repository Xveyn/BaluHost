import { apiClient } from "../lib/api";
import type {
  GpuPowerCapabilities,
  GpuPowerConfig,
  GpuPowerHistoryResponse,
  GpuPowerStatus,
} from "../types/gpuPower";

export const gpuPowerApi = {
  getStatus: () =>
    apiClient.get<GpuPowerStatus>("/api/gpu-power/status").then((r) => r.data),

  getConfig: () =>
    apiClient.get<GpuPowerConfig>("/api/gpu-power/config").then((r) => r.data),

  putConfig: (body: GpuPowerConfig) =>
    apiClient.put<GpuPowerConfig>("/api/gpu-power/config", body).then((r) => r.data),

  getCapabilities: () =>
    apiClient.get<GpuPowerCapabilities>("/api/gpu-power/capabilities").then((r) => r.data),

  registerDemand: (source: string, timeoutSeconds?: number, description?: string) =>
    apiClient
      .post<{ source: string; success: boolean }>("/api/gpu-power/demand", {
        source,
        timeout_seconds: timeoutSeconds,
        description,
      })
      .then((r) => r.data),

  unregisterDemand: (source: string) =>
    apiClient
      .delete<{ source: string; removed: boolean }>(
        `/api/gpu-power/demand/${encodeURIComponent(source)}`
      )
      .then((r) => r.data),

  getHistory: (limit = 100) =>
    apiClient
      .get<GpuPowerHistoryResponse>(`/api/gpu-power/history?limit=${limit}`)
      .then((r) => r.data),
};
