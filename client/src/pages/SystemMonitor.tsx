import { useState, useEffect, useCallback } from 'react';
import { LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, Legend, ResponsiveContainer } from 'recharts';
import { buildApiUrl } from '../lib/api';

interface DiskIOSample {
  timestamp: number;
  readMbps: number;
  writeMbps: number;
  readIops: number;
  writeIops: number;
  avgResponseMs?: number;
  activeTimePercent?: number;
}

interface DiskIOHistory {
  diskName: string;
  samples: DiskIOSample[];
  model?: string | null;
}

interface DiskIOResponse {
  disks: DiskIOHistory[];
  interval: number;
}

export default function SystemMonitor() {
  const [diskData, setDiskData] = useState<DiskIOResponse | null>(null);
  const [selectedDisk, setSelectedDisk] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [viewMode, setViewMode] = useState<'throughput' | 'iops'>('throughput');

  const loadDiskIO = useCallback(async () => {
    const token = localStorage.getItem('token');

    try {
      const response = await fetch(buildApiUrl('/api/system/disk-io/history'), {
        headers: {
          'Authorization': `Bearer ${token}`
        }
      });

      if (!response.ok) {
        throw new Error('Failed to fetch disk I/O data');
      }

      const data: DiskIOResponse = await response.json();
      setDiskData(data);

      // Auto-select first disk if none selected
      if (!selectedDisk && data.disks.length > 0) {
        setSelectedDisk(data.disks[0].diskName);
      }
    } catch (err) {
      console.error('Failed to load disk I/O:', err);
    } finally {
      setLoading(false);
    }
  }, [selectedDisk]);

  useEffect(() => {
    setLoading(true);
    loadDiskIO();
    const interval = setInterval(loadDiskIO, 2000); // Update every 2 seconds
    return () => clearInterval(interval);
  }, [loadDiskIO]);

  const formatTimestamp = (timestamp: number): string => {
    const date = new Date(timestamp);
    return date.toLocaleTimeString('de-DE', { hour: '2-digit', minute: '2-digit', second: '2-digit' });
  };

  const getSelectedDiskData = () => {
    if (!diskData || !selectedDisk) return null;
    return diskData.disks.find(d => d.diskName === selectedDisk);
  };

  const getCurrentStats = () => {
    const disk = getSelectedDiskData();
    if (!disk || disk.samples.length === 0) {
      return { read: 0, write: 0, readIops: 0, writeIops: 0 };
    }
    
    const latest = disk.samples[disk.samples.length - 1];
    return {
      read: latest.readMbps,
      write: latest.writeMbps,
      readIops: latest.readIops,
      writeIops: latest.writeIops
    };
  };

  const getChartData = () => {
    const disk = getSelectedDiskData();
    if (!disk) return [];

    // Show last 60 samples (60 seconds)
    const samples = disk.samples.slice(-60);
    
    return samples.map(sample => ({
      time: formatTimestamp(sample.timestamp),
      timestamp: sample.timestamp,
      read: viewMode === 'throughput' ? sample.readMbps : sample.readIops,
      write: viewMode === 'throughput' ? sample.writeMbps : sample.writeIops,
    }));
  };

  // Loading component with animated dots
  const LoadingMonitor = () => {
    const [dots, setDots] = useState('');
    useEffect(() => {
      const sequence = ['.', '..', '...', '.', '..'];
      let idx = 0;
      const timer = setInterval(() => {
        setDots(sequence[idx]);
        idx = (idx + 1) % sequence.length;
      }, 450);
      return () => clearInterval(timer);
    }, []);
    return (
      <div className="card border-slate-800/60 bg-slate-900/55 py-12 text-center">
        <p className="text-sm text-slate-500">Initialisiere Disk Monitor{dots}</p>
      </div>
    );
  };

  if (loading && !diskData) {
    return (
      <LoadingMonitor />
    );
  }

  const currentStats = getCurrentStats();
  const chartData = getChartData();


  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex flex-wrap items-center justify-between gap-4">
        <div>
          <h1 className="text-3xl font-semibold text-white">Disk Monitor</h1>
          <p className="mt-1 text-sm text-slate-400">
            Echtzeit-Aktivität und Antwortzeiten der physischen Festplatten
          </p>
        </div>
        <div className="flex items-center gap-2 rounded-full border border-slate-800 bg-slate-900/70 px-4 py-2 text-xs text-slate-400 shadow-inner">
          <span className="h-2 w-2 animate-pulse rounded-full bg-emerald-400" />
          Live-Datenstream
        </div>
      </div>

      {/* Disk Selector */}
      {diskData && diskData.disks.length > 0 && (
        <div className="flex flex-wrap gap-3">
          {diskData.disks.map(disk => (
            <button
              key={disk.diskName}
              onClick={() => setSelectedDisk(disk.diskName)}
              className={`rounded-lg border px-4 py-2 text-sm font-medium transition-all ${
                selectedDisk === disk.diskName
                  ? 'border-blue-500 bg-blue-500/10 text-blue-400'
                  : 'border-slate-700 bg-slate-800/50 text-slate-400 hover:border-slate-600 hover:bg-slate-800'
              }`}
            >
              {disk.model ? `${disk.model} (${disk.diskName})` : disk.diskName}
            </button>
          ))}
        </div>
      )}

      {/* Current Stats Cards */}
      {selectedDisk && (
        <div className="grid grid-cols-1 gap-5 md:grid-cols-2 xl:grid-cols-6">
          <div className="card border-slate-800/60 bg-gradient-to-br from-blue-500/10 to-transparent p-5">
            <div className="flex items-center justify-between">
              <div>
                <p className="text-xs font-medium uppercase tracking-wider text-slate-400">
                  Lesen
                </p>
                <p className="mt-2 text-2xl font-semibold text-white">
                  {currentStats.read.toFixed(2)} MB/s
                </p>
              </div>
              <div className="rounded-full bg-blue-500/20 p-3">
                {/* Icon ohne Upload/Download Anmutung: Lesekopf Symbol */}
                <svg className="h-6 w-6 text-blue-400" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2}>
                  <rect x="5" y="4" width="14" height="16" rx="2" />
                  <path d="M9 8h6M9 12h4" strokeLinecap="round" />
                </svg>
              </div>
            </div>
          </div>

          <div className="card border-slate-800/60 bg-gradient-to-br from-green-500/10 to-transparent p-5">
            <div className="flex items-center justify-between">
              <div>
                <p className="text-xs font-medium uppercase tracking-wider text-slate-400">
                  Schreiben
                </p>
                <p className="mt-2 text-2xl font-semibold text-white">
                  {currentStats.write.toFixed(2)} MB/s
                </p>
              </div>
              <div className="rounded-full bg-green-500/20 p-3">
                {/* Schreibsymbol: Stift auf Platte */}
                <svg className="h-6 w-6 text-green-400" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2}>
                  <rect x="5" y="4" width="14" height="16" rx="2" />
                  <path d="M9 12l6-6" strokeLinecap="round" />
                  <path d="M9 16h6" strokeLinecap="round" />
                </svg>
              </div>
            </div>
          </div>

          <div className="card border-slate-800/60 bg-gradient-to-br from-purple-500/10 to-transparent p-5">
            <div className="flex items-center justify-between">
              <div>
                <p className="text-xs font-medium uppercase tracking-wider text-slate-400">
                  Lese-IOPS
                </p>
                <p className="mt-2 text-2xl font-semibold text-white">
                  {currentStats.readIops.toFixed(0)}
                </p>
              </div>
              <div className="rounded-full bg-purple-500/20 p-3">
                <svg className="h-6 w-6 text-purple-400" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M13 10V3L4 14h7v7l9-11h-7z" />
                </svg>
              </div>
            </div>
          </div>

          <div className="card border-slate-800/60 bg-gradient-to-br from-orange-500/10 to-transparent p-5">
            <div className="flex items-center justify-between">
              <div>
                <p className="text-xs font-medium uppercase tracking-wider text-slate-400">
                  Schreib-IOPS
                </p>
                <p className="mt-2 text-2xl font-semibold text-white">
                  {currentStats.writeIops.toFixed(0)}
                </p>
              </div>
              <div className="rounded-full bg-orange-500/20 p-3">
                <svg className="h-6 w-6 text-orange-400" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M13 10V3L4 14h7v7l9-11h-7z" />
                </svg>
              </div>
            </div>
          </div>

          <div className="card border-slate-800/60 bg-gradient-to-br from-cyan-500/10 to-transparent p-5">
            <div className="flex items-center justify-between">
              <div>
                <p className="text-xs font-medium uppercase tracking-wider text-slate-400">
                  Antwortzeit
                </p>
                <p className="mt-2 text-2xl font-semibold text-white">
                  {(() => {
                    const disk = getSelectedDiskData();
                    if (!disk || disk.samples.length === 0) return '0 ms';
                    const latest = disk.samples[disk.samples.length - 1];
                    return `${(latest.avgResponseMs ?? 0).toFixed(2)} ms`;
                  })()}
                </p>
              </div>
              <div className="rounded-full bg-cyan-500/20 p-3">
                <svg className="h-6 w-6 text-cyan-400" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2}>
                  <circle cx="12" cy="12" r="9" />
                  <path d="M12 12l5-4" strokeLinecap="round" strokeLinejoin="round" />
                  <path d="M12 7v5" strokeLinecap="round" />
                </svg>
              </div>
            </div>
          </div>

          <div className="card border-slate-800/60 bg-gradient-to-br from-teal-500/10 to-transparent p-5">
            <div className="flex items-center justify-between">
              <div>
                <p className="text-xs font-medium uppercase tracking-wider text-slate-400">
                  Aktive Zeit
                </p>
                <p className="mt-2 text-2xl font-semibold text-white">
                  {(() => {
                    const disk = getSelectedDiskData();
                    if (!disk || disk.samples.length === 0) return '0%';
                    const latest = disk.samples[disk.samples.length - 1];
                    return `${(latest.activeTimePercent ?? 0).toFixed(1)}%`;
                  })()}
                </p>
              </div>
              <div className="rounded-full bg-teal-500/20 p-3">
                <svg className="h-6 w-6 text-teal-400" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2}>
                  <path d="M4 4h16v4H4zM4 10h10v4H4zM4 16h7v4H4z" />
                </svg>
              </div>
            </div>
          </div>
        </div>
      )}

      {/* Chart */}
      {selectedDisk && (
        <div className="card border-slate-800/60 bg-slate-900/55 p-6">
          <div className="mb-4 flex items-center justify-between">
            <h2 className="text-lg font-semibold text-white">
              {getSelectedDiskData()?.model ? `${getSelectedDiskData()?.model} (${selectedDisk})` : selectedDisk} - Verlauf (letzte 60 Sekunden)
            </h2>
            <div className="flex gap-2">
              <button
                onClick={() => setViewMode('throughput')}
                className={`rounded-lg px-3 py-1.5 text-sm font-medium transition-all ${
                  viewMode === 'throughput'
                    ? 'bg-blue-500/20 text-blue-400'
                    : 'text-slate-400 hover:bg-slate-800'
                }`}
              >
                Durchsatz (MB/s)
              </button>
              <button
                onClick={() => setViewMode('iops')}
                className={`rounded-lg px-3 py-1.5 text-sm font-medium transition-all ${
                  viewMode === 'iops'
                    ? 'bg-blue-500/20 text-blue-400'
                    : 'text-slate-400 hover:bg-slate-800'
                }`}
              >
                IOPS
              </button>
            </div>
          </div>

          <ResponsiveContainer width="100%" height={400}>
            <LineChart data={chartData}>
              <CartesianGrid strokeDasharray="3 3" stroke="#334155" />
              <XAxis 
                dataKey="time" 
                stroke="#94a3b8"
                tick={{ fill: '#94a3b8', fontSize: 12 }}
                tickLine={{ stroke: '#334155' }}
              />
              <YAxis 
                stroke="#94a3b8"
                tick={{ fill: '#94a3b8', fontSize: 12 }}
                tickLine={{ stroke: '#334155' }}
                label={{ 
                  value: viewMode === 'throughput' ? 'MB/s' : 'IOPS', 
                  angle: -90, 
                  position: 'insideLeft',
                  style: { fill: '#94a3b8', fontSize: 12 }
                }}
              />
              <Tooltip 
                contentStyle={{ 
                  backgroundColor: '#1e293b', 
                  border: '1px solid #334155',
                  borderRadius: '8px',
                  color: '#f1f5f9'
                }}
                labelStyle={{ color: '#94a3b8' }}
              />
              <Legend 
                wrapperStyle={{ color: '#94a3b8' }}
                iconType="line"
              />
              <Line 
                type="monotone" 
                dataKey="read" 
                stroke="#3b82f6" 
                strokeWidth={2}
                name={viewMode === 'throughput' ? 'Lesen (MB/s)' : 'Lese-IOPS'}
                dot={false}
                animationDuration={300}
              />
              <Line 
                type="monotone" 
                dataKey="write" 
                stroke="#10b981" 
                strokeWidth={2}
                name={viewMode === 'throughput' ? 'Schreiben (MB/s)' : 'Schreib-IOPS'}
                dot={false}
                animationDuration={300}
              />
            </LineChart>
          </ResponsiveContainer>
        </div>
      )}

      {/* No Data Message */}
      {(!diskData || diskData.disks.length === 0) && (
        <div className="card border-slate-800/60 bg-slate-900/55 py-12 text-center">
          <svg className="mx-auto h-12 w-12 text-slate-600" fill="none" viewBox="0 0 24 24" stroke="currentColor">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M20 13V6a2 2 0 00-2-2H6a2 2 0 00-2 2v7m16 0v5a2 2 0 01-2 2H6a2 2 0 01-2-2v-5m16 0h-2.586a1 1 0 00-.707.293l-2.414 2.414a1 1 0 01-.707.293h-3.172a1 1 0 01-.707-.293l-2.414-2.414A1 1 0 006.586 13H4" />
          </svg>
          <p className="mt-4 text-sm text-slate-400">Keine Festplatten-Daten verfügbar</p>
          <p className="mt-1 text-xs text-slate-500">Warte auf erste Messung...</p>
        </div>
      )}
    </div>
  );
}
