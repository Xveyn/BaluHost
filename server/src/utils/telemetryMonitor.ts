import os from 'os';
import { promises as fs } from 'fs';
import { isDevelopmentMode } from './mockData.js';

interface CpuSample {
  timestamp: number;
  usage: number;
}

interface MemorySample {
  timestamp: number;
  used: number;
  total: number;
  percent: number;
}

interface NetworkSample {
  timestamp: number;
  downloadMbps: number;
  uploadMbps: number;
}

const SAMPLE_INTERVAL = Number(process.env.TELEMETRY_SAMPLE_INTERVAL ?? 3000);
const MAX_SAMPLES = Number(process.env.TELEMETRY_HISTORY_SIZE ?? 60);

let monitorTimer: NodeJS.Timer | null = null;
let previousCpuTotals: { idle: number; total: number } | null = null;
let previousNetworkBytes: { timestamp: number; rxBytes: number; txBytes: number } | null = null;

const cpuHistory: CpuSample[] = [];
const memoryHistory: MemorySample[] = [];
const networkHistory: NetworkSample[] = [];

const pushSample = <T>(collection: T[], sample: T) => {
  collection.push(sample);
  if (collection.length > MAX_SAMPLES) {
    collection.shift();
  }
};

const calculateCpuUsage = (): number => {
  const cpus = os.cpus();
  if (!cpus || cpus.length === 0) {
    return 0;
  }

  let idle = 0;
  let total = 0;

  for (const cpu of cpus) {
    const times = cpu.times;
    idle += times.idle;
    total += times.user + times.nice + times.sys + times.irq + times.idle;
  }

  if (!previousCpuTotals) {
    previousCpuTotals = { idle, total };
    return 0;
  }

  const idleDiff = idle - previousCpuTotals.idle;
  const totalDiff = total - previousCpuTotals.total;
  previousCpuTotals = { idle, total };

  if (totalDiff === 0) {
    return 0;
  }

  const usage = (1 - idleDiff / totalDiff) * 100;
  return Number.isFinite(usage) ? Math.max(0, Math.min(usage, 100)) : 0;
};

const readLinuxNetworkBytes = async (): Promise<{ rxBytes: number; txBytes: number } | null> => {
  try {
    const content = await fs.readFile('/proc/net/dev', 'utf8');
    const lines = content.trim().split('\n').slice(2);
    let rxBytes = 0;
    let txBytes = 0;

    for (const rawLine of lines) {
      const line = rawLine.trim();
      if (!line) continue;
      const [ifacePart, rest] = line.split(':');
      const iface = ifacePart.trim();
      if (iface === 'lo') continue;
      const parts = rest.trim().split(/\s+/);
      rxBytes += Number.parseInt(parts[0] ?? '0', 10);
      txBytes += Number.parseInt(parts[8] ?? '0', 10);
    }

    return { rxBytes, txBytes };
  } catch (error) {
    console.error('Failed to read /proc/net/dev:', error);
    return null;
  }
};

const generateMockNetworkSample = (previous?: NetworkSample): { downloadMbps: number; uploadMbps: number } => {
  const baseDown = previous ? previous.downloadMbps : 1.2;
  const baseUp = previous ? previous.uploadMbps : 0.6;
  const nextDown = Math.max(0, baseDown + (Math.random() - 0.5) * 1.2);
  const nextUp = Math.max(0, baseUp + (Math.random() - 0.5) * 0.8);
  return {
    downloadMbps: Number(nextDown.toFixed(2)),
    uploadMbps: Number(nextUp.toFixed(2))
  };
};

const sampleTelemetry = async (): Promise<void> => {
  const now = Date.now();

  const cpuUsage = calculateCpuUsage();
  const totalMem = os.totalmem();
  const freeMem = os.freemem();
  const usedMem = totalMem - freeMem;
  const memoryPercent = totalMem > 0 ? (usedMem / totalMem) * 100 : 0;

  pushSample(cpuHistory, {
    timestamp: now,
    usage: Number(cpuUsage.toFixed(2))
  });

  pushSample(memoryHistory, {
    timestamp: now,
    used: usedMem,
    total: totalMem,
    percent: Number(memoryPercent.toFixed(2))
  });

  if (isDevelopmentMode() || process.platform !== 'linux') {
    const previousSample = networkHistory[networkHistory.length - 1];
    const mockSample = generateMockNetworkSample(previousSample);
    pushSample(networkHistory, {
      timestamp: now,
      downloadMbps: mockSample.downloadMbps,
      uploadMbps: mockSample.uploadMbps
    });
    return;
  }

  const byteSnapshot = await readLinuxNetworkBytes();
  if (!byteSnapshot) {
    return;
  }

  if (!previousNetworkBytes) {
    previousNetworkBytes = { timestamp: now, rxBytes: byteSnapshot.rxBytes, txBytes: byteSnapshot.txBytes };
    return;
  }

  const timeDiff = (now - previousNetworkBytes.timestamp) / 1000;
  if (timeDiff <= 0) {
    previousNetworkBytes = { timestamp: now, rxBytes: byteSnapshot.rxBytes, txBytes: byteSnapshot.txBytes };
    return;
  }

  const rxDiff = byteSnapshot.rxBytes - previousNetworkBytes.rxBytes;
  const txDiff = byteSnapshot.txBytes - previousNetworkBytes.txBytes;

  previousNetworkBytes = { timestamp: now, rxBytes: byteSnapshot.rxBytes, txBytes: byteSnapshot.txBytes };

  const downloadMbps = Math.max(0, (rxDiff * 8) / (timeDiff * 1_000_000));
  const uploadMbps = Math.max(0, (txDiff * 8) / (timeDiff * 1_000_000));

  pushSample(networkHistory, {
    timestamp: now,
    downloadMbps: Number(downloadMbps.toFixed(2)),
    uploadMbps: Number(uploadMbps.toFixed(2))
  });
};

export const startTelemetryMonitor = (): void => {
  if (monitorTimer) {
    return;
  }

  void sampleTelemetry();
  monitorTimer = setInterval(() => {
    void sampleTelemetry();
  }, SAMPLE_INTERVAL);
};

export const getCpuHistory = (): CpuSample[] => [...cpuHistory];

export const getMemoryHistory = (): MemorySample[] => [...memoryHistory];

export const getNetworkHistory = (): NetworkSample[] => [...networkHistory];

export const getLatestCpuUsage = (): number | null => {
  const latest = cpuHistory[cpuHistory.length - 1];
  return latest ? latest.usage : null;
};

export const getLatestMemorySample = (): MemorySample | null => {
  const latest = memoryHistory[memoryHistory.length - 1];
  return latest ?? null;
};

export type { CpuSample, MemorySample, NetworkSample };
