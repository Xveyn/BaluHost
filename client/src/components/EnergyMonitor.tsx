/**
 * Energy Monitor Component
 *
 * Displays comprehensive energy consumption statistics with charts,
 * downtime tracking, and cost estimates.
 */

import React, { useState, useEffect } from 'react';
import {
  Zap,
  TrendingUp,
  Clock,
  DollarSign,
  AlertCircle,
  BarChart3,
  Calendar,
  Activity
} from 'lucide-react';
import {
  LineChart,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
} from 'recharts';
import toast from 'react-hot-toast';
import {
  getEnergyDashboard,
  getEnergyCost,
  getHourlySamples,
} from '../api/energy';
import type { EnergyDashboard, EnergyCostEstimate } from '../api/energy';
import { listTapoDevices, getPowerHistory } from '../api/power';
import type { TapoDevice } from '../api/power';

type TimeWindow = '10min' | '1hour' | '24hours' | '7days';

const EnergyMonitor: React.FC = () => {
  const [devices, setDevices] = useState<TapoDevice[]>([]);
  const [selectedDeviceId, setSelectedDeviceId] = useState<number | null>(null);
  const [dashboard, setDashboard] = useState<EnergyDashboard | null>(null);
  const [costs, setCosts] = useState<{
    today: EnergyCostEstimate | null;
    week: EnergyCostEstimate | null;
    month: EnergyCostEstimate | null;
  }>({ today: null, week: null, month: null });
  const [loading, setLoading] = useState(true);
  const [costPerKwh, setCostPerKwh] = useState(0.40);
  const [timeWindow, setTimeWindow] = useState<TimeWindow>('10min');
  const [chartData, setChartData] = useState<any[]>([]);

  // Load devices
  useEffect(() => {
    const loadDevices = async () => {
      try {
        const deviceList = await listTapoDevices();
        setDevices(deviceList);

        // Auto-select first device
        if (deviceList.length > 0 && !selectedDeviceId) {
          setSelectedDeviceId(deviceList[0].id);
        }
      } catch (error: any) {
        console.error('Failed to load devices:', error);
        toast.error('Failed to load devices');
      } finally {
        setLoading(false);
      }
    };

    loadDevices();
  }, []);

  // Load dashboard data when device is selected
  useEffect(() => {
    if (!selectedDeviceId) return;

    const loadDashboard = async () => {
      setLoading(true);
      try {
        const data = await getEnergyDashboard(selectedDeviceId);
        setDashboard(data);

        // Load cost estimates
        const [todayCost, weekCost, monthCost] = await Promise.all([
          getEnergyCost(selectedDeviceId, 'today', costPerKwh),
          getEnergyCost(selectedDeviceId, 'week', costPerKwh),
          getEnergyCost(selectedDeviceId, 'month', costPerKwh),
        ]);

        setCosts({ today: todayCost, week: weekCost, month: monthCost });
      } catch (error: any) {
        console.error('Failed to load dashboard:', error);
        toast.error('Failed to load energy data');
      } finally {
        setLoading(false);
      }
    };

    loadDashboard();

    // Refresh every 30 seconds
    const interval = setInterval(loadDashboard, 30000);
    return () => clearInterval(interval);
  }, [selectedDeviceId, costPerKwh]);

  // Load chart data based on time window
  useEffect(() => {
    if (!selectedDeviceId) return;

    const loadChartData = async () => {
      try {
        let data: any[] = [];

        switch (timeWindow) {
          case '10min':
            // Use live memory buffer (updates every 5 seconds)
            const powerHistory = await getPowerHistory();
            const deviceHistory = powerHistory.devices.find(d => d.device_id === selectedDeviceId);
            if (deviceHistory && deviceHistory.samples.length > 0) {
              data = deviceHistory.samples.map(sample => ({
                time: new Date(sample.timestamp).toLocaleTimeString('de-DE', {
                  hour: '2-digit',
                  minute: '2-digit',
                  second: '2-digit'
                }),
                watts: sample.watts,
                fullTimestamp: sample.timestamp
              }));
            }
            break;

          case '1hour':
            // Use hourly samples from DB (last hour)
            const hourSamples = await getHourlySamples(selectedDeviceId, 1);
            data = hourSamples.map(sample => ({
              time: new Date(sample.timestamp).toLocaleTimeString('de-DE', {
                hour: '2-digit',
                minute: '2-digit'
              }),
              watts: sample.avg_watts,
              fullTimestamp: sample.timestamp
            }));
            break;

          case '24hours':
            // Use hourly samples from DB (last 24 hours)
            const daySamples = await getHourlySamples(selectedDeviceId, 24);
            data = daySamples.map(sample => ({
              time: new Date(sample.timestamp).toLocaleTimeString('de-DE', {
                hour: '2-digit',
                minute: '2-digit'
              }),
              watts: sample.avg_watts,
              fullTimestamp: sample.timestamp
            }));
            break;

          case '7days':
            // Use hourly samples from DB (last 7 days = 168 hours)
            const weekSamples = await getHourlySamples(selectedDeviceId, 168);
            data = weekSamples.map(sample => ({
              time: new Date(sample.timestamp).toLocaleDateString('de-DE', {
                month: 'short',
                day: 'numeric',
                hour: '2-digit'
              }),
              watts: sample.avg_watts,
              fullTimestamp: sample.timestamp
            }));
            break;
        }

        setChartData(data);
      } catch (error: any) {
        console.error('Failed to load chart data:', error);
      }
    };

    loadChartData();

    // Refresh interval based on time window
    const refreshInterval = timeWindow === '10min' ? 5000 : 30000; // 5s for live, 30s for historical
    const interval = setInterval(loadChartData, refreshInterval);
    return () => clearInterval(interval);
  }, [selectedDeviceId, timeWindow]);

  if (loading && devices.length === 0) {
    return (
      <div className="card">
        <p className="text-sm text-slate-500">Loading energy monitor...</p>
      </div>
    );
  }

  if (devices.length === 0) {
    return (
      <div className="card border-amber-500/20 bg-amber-500/5">
        <div className="flex items-center gap-3 text-amber-200">
          <AlertCircle className="w-6 h-6" />
          <div>
            <h3 className="font-semibold">No Devices Configured</h3>
            <p className="text-sm text-slate-400 mt-1">
              Configure a Tapo device in Settings to enable energy monitoring
            </p>
          </div>
        </div>
      </div>
    );
  }

  const stats = dashboard?.today;

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex flex-wrap items-center justify-between gap-4">
        <div>
          <h1 className="text-3xl font-semibold text-white">Energy Monitor</h1>
          <p className="mt-1 text-sm text-slate-400">
            Power consumption analysis and statistics
          </p>
        </div>

        {/* Device Selector */}
        {devices.length > 1 && (
          <select
            value={selectedDeviceId || ''}
            onChange={(e) => setSelectedDeviceId(Number(e.target.value))}
            className="input"
          >
            {devices.map((device) => (
              <option key={device.id} value={device.id}>
                {device.name}
              </option>
            ))}
          </select>
        )}
      </div>

      {/* Current Status */}
      <div className="card bg-gradient-to-br from-amber-500/10 to-orange-500/10 border-amber-500/20">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-4">
            <div className="p-3 rounded-xl bg-gradient-to-br from-amber-500 to-orange-500 text-white">
              <Zap className="w-8 h-8" />
            </div>
            <div>
              <p className="text-sm text-slate-400">Current Power</p>
              <p className="text-4xl font-bold text-white">
                {dashboard?.current_watts.toFixed(1) || '—'} W
              </p>
            </div>
          </div>
          <div className="text-right">
            <div className="flex items-center gap-2 text-sm">
              <div className={`h-2 w-2 rounded-full ${dashboard?.is_online ? 'bg-emerald-500' : 'bg-red-500'} animate-pulse`} />
              <span className="text-slate-400">
                {dashboard?.is_online ? 'Online' : 'Offline'}
              </span>
            </div>
            <p className="text-xs text-slate-500 mt-1">
              {dashboard?.last_updated ? new Date(dashboard.last_updated).toLocaleString('de-DE') : '—'}
            </p>
          </div>
        </div>
      </div>

      {/* Stats Grid */}
      <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-4 gap-4">
        {/* Today Stats */}
        <div className="card border-slate-800/40 bg-slate-900/60">
          <div className="flex items-center gap-3 mb-3">
            <Calendar className="w-5 h-5 text-sky-400" />
            <h3 className="font-semibold text-white">Today</h3>
          </div>
          {stats ? (
            <>
              <div className="space-y-2">
                <div className="flex justify-between text-sm">
                  <span className="text-slate-400">Energy</span>
                  <span className="text-white font-semibold">
                    {stats.total_energy_kwh.toFixed(3)} kWh
                  </span>
                </div>
                <div className="flex justify-between text-sm">
                  <span className="text-slate-400">Avg Power</span>
                  <span className="text-white font-semibold">
                    {stats.avg_watts.toFixed(1)} W
                  </span>
                </div>
                <div className="flex justify-between text-sm">
                  <span className="text-slate-400">Peak</span>
                  <span className="text-white font-semibold">
                    {stats.max_watts.toFixed(1)} W
                  </span>
                </div>
                <div className="flex justify-between text-sm">
                  <span className="text-slate-400">Cost</span>
                  <span className="text-emerald-400 font-semibold">
                    €{costs.today?.estimated_cost.toFixed(2) || '0.00'}
                  </span>
                </div>
              </div>
            </>
          ) : (
            <p className="text-sm text-slate-500">No data yet</p>
          )}
        </div>

        {/* Week Stats */}
        <div className="card border-slate-800/40 bg-slate-900/60">
          <div className="flex items-center gap-3 mb-3">
            <BarChart3 className="w-5 h-5 text-violet-400" />
            <h3 className="font-semibold text-white">This Week</h3>
          </div>
          {dashboard?.week ? (
            <>
              <div className="space-y-2">
                <div className="flex justify-between text-sm">
                  <span className="text-slate-400">Energy</span>
                  <span className="text-white font-semibold">
                    {dashboard.week.total_energy_kwh.toFixed(3)} kWh
                  </span>
                </div>
                <div className="flex justify-between text-sm">
                  <span className="text-slate-400">Avg Power</span>
                  <span className="text-white font-semibold">
                    {dashboard.week.avg_watts.toFixed(1)} W
                  </span>
                </div>
                <div className="flex justify-between text-sm">
                  <span className="text-slate-400">Uptime</span>
                  <span className="text-white font-semibold">
                    {dashboard.week.uptime_percentage.toFixed(1)}%
                  </span>
                </div>
                <div className="flex justify-between text-sm">
                  <span className="text-slate-400">Cost</span>
                  <span className="text-emerald-400 font-semibold">
                    €{costs.week?.estimated_cost.toFixed(2) || '0.00'}
                  </span>
                </div>
              </div>
            </>
          ) : (
            <p className="text-sm text-slate-500">No data yet</p>
          )}
        </div>

        {/* Month Stats */}
        <div className="card border-slate-800/40 bg-slate-900/60">
          <div className="flex items-center gap-3 mb-3">
            <TrendingUp className="w-5 h-5 text-emerald-400" />
            <h3 className="font-semibold text-white">This Month</h3>
          </div>
          {dashboard?.month ? (
            <>
              <div className="space-y-2">
                <div className="flex justify-between text-sm">
                  <span className="text-slate-400">Energy</span>
                  <span className="text-white font-semibold">
                    {dashboard.month.total_energy_kwh.toFixed(3)} kWh
                  </span>
                </div>
                <div className="flex justify-between text-sm">
                  <span className="text-slate-400">Avg Power</span>
                  <span className="text-white font-semibold">
                    {dashboard.month.avg_watts.toFixed(1)} W
                  </span>
                </div>
                <div className="flex justify-between text-sm">
                  <span className="text-slate-400">Uptime</span>
                  <span className="text-white font-semibold">
                    {dashboard.month.uptime_percentage.toFixed(1)}%
                  </span>
                </div>
                <div className="flex justify-between text-sm">
                  <span className="text-slate-400">Cost</span>
                  <span className="text-emerald-400 font-semibold">
                    €{costs.month?.estimated_cost.toFixed(2) || '0.00'}
                  </span>
                </div>
              </div>
            </>
          ) : (
            <p className="text-sm text-slate-500">No data yet</p>
          )}
        </div>

        {/* Downtime */}
        <div className="card border-slate-800/40 bg-slate-900/60">
          <div className="flex items-center gap-3 mb-3">
            <Clock className="w-5 h-5 text-red-400" />
            <h3 className="font-semibold text-white">Downtime</h3>
          </div>
          {stats ? (
            <>
              <div className="space-y-2">
                <div className="flex justify-between text-sm">
                  <span className="text-slate-400">Today</span>
                  <span className="text-white font-semibold">
                    {stats.downtime_minutes} min
                  </span>
                </div>
                <div className="flex justify-between text-sm">
                  <span className="text-slate-400">Week</span>
                  <span className="text-white font-semibold">
                    {dashboard?.week?.downtime_minutes || 0} min
                  </span>
                </div>
                <div className="flex justify-between text-sm">
                  <span className="text-slate-400">Month</span>
                  <span className="text-white font-semibold">
                    {dashboard?.month?.downtime_minutes || 0} min
                  </span>
                </div>
                <div className="flex justify-between text-sm">
                  <span className="text-slate-400">Uptime %</span>
                  <span className={`font-semibold ${stats.uptime_percentage > 99 ? 'text-emerald-400' : stats.uptime_percentage > 95 ? 'text-amber-400' : 'text-red-400'}`}>
                    {stats.uptime_percentage.toFixed(1)}%
                  </span>
                </div>
              </div>
            </>
          ) : (
            <p className="text-sm text-slate-500">No data yet</p>
          )}
        </div>
      </div>

      {/* Power Chart */}
      <div className="card border-slate-800/50 bg-slate-900/55">
        <div className="flex items-center justify-between mb-6">
          <div>
            <h2 className="text-xl font-semibold text-white">Power Consumption</h2>
            <p className="text-sm text-slate-400 mt-1">
              {timeWindow === '10min' && 'Last 10 minutes (live)'}
              {timeWindow === '1hour' && 'Last hour'}
              {timeWindow === '24hours' && 'Last 24 hours'}
              {timeWindow === '7days' && 'Last 7 days'}
            </p>
          </div>
          <Activity className="w-6 h-6 text-amber-500" />
        </div>

        {/* Time Window Selector */}
        <div className="flex gap-2 mb-6">
          {(['10min', '1hour', '24hours', '7days'] as TimeWindow[]).map((window) => (
            <button
              key={window}
              onClick={() => setTimeWindow(window)}
              className={`
                px-4 py-2 rounded-lg text-sm font-medium transition-all
                ${timeWindow === window
                  ? 'bg-amber-500 text-white shadow-lg shadow-amber-500/20'
                  : 'bg-slate-800/60 text-slate-400 hover:bg-slate-800 hover:text-slate-300'
                }
              `}
            >
              {window === '10min' && '10 Min'}
              {window === '1hour' && '1 Hour'}
              {window === '24hours' && '24 Hours'}
              {window === '7days' && '7 Days'}
            </button>
          ))}
        </div>

        {chartData.length > 0 ? (
          <div className="h-80">
            <ResponsiveContainer width="100%" height="100%">
              <LineChart data={chartData}>
                <CartesianGrid strokeDasharray="3 3" stroke="#334155" />
                <XAxis
                  dataKey="time"
                  stroke="#94a3b8"
                  style={{ fontSize: '12px' }}
                />
                <YAxis
                  stroke="#94a3b8"
                  style={{ fontSize: '12px' }}
                  label={{ value: 'Watts', angle: -90, position: 'insideLeft', style: { fill: '#94a3b8' } }}
                />
                <Tooltip
                  contentStyle={{
                    backgroundColor: '#1e293b',
                    border: '1px solid #334155',
                    borderRadius: '8px',
                    color: '#fff'
                  }}
                  formatter={(value: number) => [`${value.toFixed(1)} W`, 'Power']}
                />
                <Line
                  type="monotone"
                  dataKey="watts"
                  stroke="#f59e0b"
                  strokeWidth={2}
                  dot={false}
                  activeDot={{ r: 6 }}
                />
              </LineChart>
            </ResponsiveContainer>
          </div>
        ) : (
          <div className="h-80 flex items-center justify-center text-slate-500">
            <div className="text-center">
              <Activity className="w-12 h-12 mx-auto mb-3 opacity-50" />
              <p>No chart data available yet</p>
              <p className="text-xs mt-1">Data will appear after the first hour of monitoring</p>
            </div>
          </div>
        )}
      </div>

      {/* Cost Configuration */}
      <div className="card border-slate-800/40 bg-slate-900/60">
        <div className="flex items-center gap-3 mb-4">
          <DollarSign className="w-5 h-5 text-emerald-400" />
          <h3 className="font-semibold text-white">Cost Settings</h3>
        </div>
        <div className="flex items-center gap-4">
          <label className="text-sm text-slate-400">Cost per kWh (€)</label>
          <input
            type="number"
            step="0.01"
            min="0"
            value={costPerKwh}
            onChange={(e) => setCostPerKwh(Number(e.target.value))}
            className="input w-32"
          />
          <span className="text-xs text-slate-500">
            Current: €{costPerKwh.toFixed(2)}/kWh
          </span>
        </div>
      </div>
    </div>
  );
};

export default EnergyMonitor;
