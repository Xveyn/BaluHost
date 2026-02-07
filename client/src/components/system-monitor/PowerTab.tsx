/**
 * PowerTab -- Power/energy monitoring tab with Tapo device integration.
 */

import { useState, useEffect, useCallback, useMemo } from 'react';
import { useTranslation } from 'react-i18next';
import { Link } from 'react-router-dom';
import {
  ComposedChart,
  Area,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
  Legend,
} from 'recharts';
import toast from 'react-hot-toast';
import { extractErrorMessage } from '../../lib/api';
import { MetricChart } from '../monitoring';
import { formatTimeForRange, parseUtcTimestamp } from '../../lib/dateUtils';
import type { ChartTimeRange } from '../../lib/dateUtils';
import { getPowerHistory } from '../../api/power';
import type { PowerMonitoringResponse } from '../../api/power';
import {
  getEnergyPriceConfig,
  updateEnergyPriceConfig,
  getCumulativeEnergy,
  type EnergyPriceConfig,
  type CumulativeEnergyResponse,
} from '../../api/energy';
import { StatCard } from '../ui/StatCard';
import { formatNumber } from '../../lib/formatters';

type CumulativePeriod = 'today' | 'week' | 'month';

export function PowerTab() {
  const { t, i18n } = useTranslation(['system', 'common']);
  const [powerData, setPowerData] = useState<PowerMonitoringResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // Energy price config state
  const [priceConfig, setPriceConfig] = useState<EnergyPriceConfig | null>(null);
  const [editingPrice, setEditingPrice] = useState(false);
  const [priceInput, setPriceInput] = useState('');
  const [savingPrice, setSavingPrice] = useState(false);

  // Cumulative energy state
  const [cumulativePeriod, setCumulativePeriod] = useState<CumulativePeriod>('today');
  const [cumulativeData, setCumulativeData] = useState<CumulativeEnergyResponse | null>(null);
  const [cumulativeLoading, setCumulativeLoading] = useState(false);
  const [selectedDeviceId, setSelectedDeviceId] = useState<number | null>(null);

  const fetchPower = useCallback(async () => {
    try {
      const data = await getPowerHistory();
      setPowerData(data);
      setError(null);
    } catch (err: any) {
      // Don't show error for no devices configured
      if (err.response?.status !== 404) {
        setError(err.message || 'Failed to load power data');
      }
    } finally {
      setLoading(false);
    }
  }, []);

  // Fetch price config on mount
  useEffect(() => {
    const fetchPriceConfig = async () => {
      try {
        const config = await getEnergyPriceConfig();
        setPriceConfig(config);
        setPriceInput(config.cost_per_kwh.toString());
      } catch (err) {
        console.error('Failed to load price config:', err);
      }
    };
    fetchPriceConfig();
  }, []);

  // Set device ID when powerData becomes available
  useEffect(() => {
    if (powerData && powerData.devices.length > 0 && !selectedDeviceId) {
      setSelectedDeviceId(powerData.devices[0].device_id);
    }
  }, [powerData, selectedDeviceId]);

  // Fetch cumulative data with separate interval (60s - matches DB write interval)
  useEffect(() => {
    if (!selectedDeviceId) return;

    const fetchCumulative = async () => {
      setCumulativeLoading(true);
      try {
        const data = await getCumulativeEnergy(selectedDeviceId, cumulativePeriod);
        setCumulativeData(data);
      } catch (err) {
        console.error('Failed to load cumulative data:', err);
      } finally {
        setCumulativeLoading(false);
      }
    };

    // Initial fetch
    fetchCumulative();

    // Separate interval: 60 seconds (matches DB write interval)
    const interval = setInterval(fetchCumulative, 60000);
    return () => clearInterval(interval);
  }, [selectedDeviceId, cumulativePeriod]);

  const handleSavePrice = async () => {
    const newPrice = parseFloat(priceInput);
    if (isNaN(newPrice) || newPrice < 0.01 || newPrice > 10.0) {
      toast.error(t('monitor.power.priceMustBeBetween'));
      return;
    }

    setSavingPrice(true);
    try {
      const updated = await updateEnergyPriceConfig({
        cost_per_kwh: newPrice,
        currency: priceConfig?.currency || 'EUR',
      });
      setPriceConfig(updated);
      setEditingPrice(false);
      toast.success(t('monitor.power.priceUpdated'));
      // Refresh cumulative data with new price
      if (selectedDeviceId) {
        const data = await getCumulativeEnergy(selectedDeviceId, cumulativePeriod);
        setCumulativeData(data);
      }
    } catch (err: any) {
      toast.error(extractErrorMessage(err.response?.data?.detail, t('monitor.power.saveError')));
    } finally {
      setSavingPrice(false);
    }
  };

  useEffect(() => {
    fetchPower();
    const interval = setInterval(fetchPower, 5000);
    return () => clearInterval(interval);
  }, [fetchPower]);

  // Calculate cumulative energy consumption from samples
  const calculateCumulativeEnergy = useCallback((samples: { timestamp: string; watts: number }[]) => {
    if (samples.length < 2) return 0;

    let totalWh = 0;
    for (let i = 1; i < samples.length; i++) {
      const prevTime = new Date(samples[i - 1].timestamp).getTime();
      const currTime = new Date(samples[i].timestamp).getTime();
      const hours = (currTime - prevTime) / (1000 * 60 * 60);
      const avgWatts = (samples[i - 1].watts + samples[i].watts) / 2;
      totalWh += avgWatts * hours;
    }
    return totalWh / 1000; // Convert Wh to kWh
  }, []);

  // Calculate total cumulative energy across all devices
  const totalCumulativeEnergy = useMemo(() => {
    if (!powerData) return 0;
    return powerData.devices.reduce((sum, device) => {
      return sum + calculateCumulativeEnergy(device.samples);
    }, 0);
  }, [powerData, calculateCumulativeEnergy]);

  if (loading) {
    return (
      <div className="flex items-center justify-center py-12">
        <div className="inline-block h-8 w-8 animate-spin rounded-full border-4 border-slate-600 border-t-blue-500" />
      </div>
    );
  }

  if (error) {
    return <div className="text-red-400 text-center py-8">{error}</div>;
  }

  if (!powerData || powerData.devices.length === 0) {
    return (
      <div className="text-center py-12">
        <svg
          className="mx-auto h-16 w-16 text-slate-600"
          fill="none"
          viewBox="0 0 24 24"
          stroke="currentColor"
        >
          <path
            strokeLinecap="round"
            strokeLinejoin="round"
            strokeWidth={2}
            d="M13 10V3L4 14h7v7l9-11h-9z"
          />
        </svg>
        <p className="mt-4 text-slate-400">{t('monitor.power.noTapoDevices')}</p>
        <p className="text-sm text-slate-500 mt-1">
          {t('monitor.power.configureTapoDevice')}
        </p>
        <Link
          to="/admin/system-control?tab=smart"
          className="inline-block mt-4 px-4 py-2 text-sm bg-sky-500/20 text-sky-400 hover:bg-sky-500/30 border border-sky-500/40 rounded-lg transition-colors"
        >
          {t('monitor.power.configureSmartDevices')} →
        </Link>
      </div>
    );
  }

  return (
    <div className="space-y-4 sm:space-y-6">
      {/* Total Power Stats */}
      <div className="grid grid-cols-2 gap-3 sm:gap-5 lg:grid-cols-4">
        <StatCard
          label={t('monitor.power.currentPower')}
          value={formatNumber(powerData.total_current_power, 1)}
          unit="W"
          color="yellow"
          icon={<span className="text-yellow-400 text-base sm:text-xl">⚡</span>}
        />
        <StatCard
          label={t('monitor.power.cumulativeSession')}
          value={formatNumber(totalCumulativeEnergy, 4)}
          unit="kWh"
          color="orange"
          icon={<span className="text-orange-400 text-base sm:text-xl">Σ</span>}
        />
        <StatCard
          label={t('monitor.power.todayTotal')}
          value={formatNumber(powerData.devices.reduce((sum, d) => sum + (d.latest_sample?.energy_today ?? 0), 0), 2)}
          unit="kWh"
          color="green"
          icon={<span className="text-green-400 text-base sm:text-xl">📊</span>}
        />
        <StatCard
          label={t('monitor.power.devices')}
          value={powerData.devices.length}
          color="blue"
          icon={<span className="text-blue-400 text-base sm:text-xl">#</span>}
        />
      </div>

      {/* Per-device stats */}
      {powerData.devices.map((device) => {
        const deviceCumulativeEnergy = calculateCumulativeEnergy(device.samples);

        return (
          <div key={device.device_id} className="card border-slate-800/60 bg-slate-900/55 p-4 sm:p-6">
            <h3 className="mb-3 sm:mb-4 text-base sm:text-lg font-semibold text-white">{device.device_name}</h3>
            <div className="grid grid-cols-2 gap-3 sm:gap-4 lg:grid-cols-5">
              <div>
                <p className="text-[10px] sm:text-xs text-slate-400">{t('monitor.power.powerLabel')}</p>
                <p className="text-lg sm:text-xl font-semibold text-white">
                  {device.latest_sample?.watts != null ? formatNumber(device.latest_sample.watts, 1) : '-'} <span className="text-sm sm:text-base text-slate-400">W</span>
                </p>
              </div>
              <div>
                <p className="text-[10px] sm:text-xs text-slate-400">{t('monitor.power.voltage')}</p>
                <p className="text-lg sm:text-xl font-semibold text-white">
                  {device.latest_sample?.voltage != null ? formatNumber(device.latest_sample.voltage, 1) : '-'} <span className="text-sm sm:text-base text-slate-400">V</span>
                </p>
              </div>
              <div>
                <p className="text-[10px] sm:text-xs text-slate-400">{t('monitor.power.current')}</p>
                <p className="text-lg sm:text-xl font-semibold text-white">
                  {device.latest_sample?.current != null ? formatNumber(device.latest_sample.current, 3) : '-'} <span className="text-sm sm:text-base text-slate-400">A</span>
                </p>
              </div>
              <div>
                <p className="text-[10px] sm:text-xs text-slate-400">{t('monitor.power.today')}</p>
                <p className="text-lg sm:text-xl font-semibold text-white">
                  {device.latest_sample?.energy_today != null ? formatNumber(device.latest_sample.energy_today, 2) : '-'} <span className="text-sm sm:text-base text-slate-400">kWh</span>
                </p>
              </div>
              <div>
                <p className="text-[10px] sm:text-xs text-slate-400">{t('monitor.power.cumulativeSession')}</p>
                <p className="text-lg sm:text-xl font-semibold text-orange-400">
                  {formatNumber(deviceCumulativeEnergy, 4)} <span className="text-sm sm:text-base text-slate-400">kWh</span>
                </p>
              </div>
            </div>

            {/* Mini chart for this device */}
            {device.samples.length > 0 && (
              <div className="mt-3 sm:mt-4">
                <MetricChart
                  data={device.samples.map((s) => ({
                    time: s.timestamp,
                    watts: s.watts,
                  }))}
                  lines={[{ dataKey: 'watts', name: t('monitor.power.powerWatts'), color: '#eab308' }]}
                  height={180}
                  showArea
                  timeRange="1h"
                />
              </div>
            )}
          </div>
        );
      })}

      {/* Cumulative Energy Chart Section */}
      <div className="card border-slate-800/60 bg-slate-900/55 p-4 sm:p-6">
        {/* Header with Price Config */}
        <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3 mb-4">
          <div className="flex items-center gap-3">
            <h3 className="text-base sm:text-lg font-semibold text-white">
              {t('monitor.power.cumulativeConsumptionCosts')}
            </h3>
            {priceConfig && (
              <div className="flex items-center gap-2">
                {editingPrice ? (
                  <div className="flex items-center gap-2">
                    <input
                      type="number"
                      step="0.01"
                      min="0.01"
                      max="10"
                      value={priceInput}
                      onChange={(e) => setPriceInput(e.target.value)}
                      className="w-20 px-2 py-1 text-sm bg-slate-800 border border-slate-700 rounded text-white focus:border-blue-500 focus:outline-none"
                      disabled={savingPrice}
                    />
                    <span className="text-slate-400 text-sm">{priceConfig.currency}/kWh</span>
                    <button
                      onClick={handleSavePrice}
                      disabled={savingPrice}
                      className="px-2 py-1 text-xs bg-green-600 hover:bg-green-700 text-white rounded disabled:opacity-50"
                    >
                      {savingPrice ? '...' : '✓'}
                    </button>
                    <button
                      onClick={() => {
                        setEditingPrice(false);
                        setPriceInput(priceConfig.cost_per_kwh.toString());
                      }}
                      disabled={savingPrice}
                      className="px-2 py-1 text-xs bg-slate-700 hover:bg-slate-600 text-white rounded disabled:opacity-50"
                    >
                      ✕
                    </button>
                  </div>
                ) : (
                  <button
                    onClick={() => setEditingPrice(true)}
                    className="flex items-center gap-1 px-2 py-1 text-xs bg-slate-800 hover:bg-slate-700 text-slate-300 rounded border border-slate-700"
                  >
                    <span>{formatNumber(priceConfig.cost_per_kwh, 2)} {priceConfig.currency}/kWh</span>
                    <svg className="w-3 h-3" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15.232 5.232l3.536 3.536m-2.036-5.036a2.5 2.5 0 113.536 3.536L6.5 21.036H3v-3.572L16.732 3.732z" />
                    </svg>
                  </button>
                )}
              </div>
            )}
          </div>

          {/* Period Selector */}
          <div className="flex gap-1 sm:gap-2">
            {(['today', 'week', 'month'] as CumulativePeriod[]).map((period) => (
              <button
                key={period}
                onClick={() => setCumulativePeriod(period)}
                className={`px-3 py-1.5 text-xs sm:text-sm rounded-md transition-colors ${
                  cumulativePeriod === period
                    ? 'bg-blue-500/20 text-blue-400 border border-blue-500/40'
                    : 'bg-slate-800 text-slate-400 hover:bg-slate-700 border border-transparent'
                }`}
              >
                {period === 'today' ? t('monitor.power.periodToday') : period === 'week' ? t('monitor.power.periodWeek') : t('monitor.power.periodMonth')}
              </button>
            ))}
          </div>
        </div>

        {/* Summary Stats */}
        {cumulativeData && (
          <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 mb-4">
            <div className="bg-slate-800/50 rounded-lg p-3">
              <p className="text-xs text-slate-400">{t('monitor.power.totalConsumption')}</p>
              <p className="text-lg font-semibold text-emerald-400">
                {formatNumber(cumulativeData.total_kwh, 3)} <span className="text-sm text-slate-400">kWh</span>
              </p>
            </div>
            <div className="bg-slate-800/50 rounded-lg p-3">
              <p className="text-xs text-slate-400">{t('monitor.power.totalCosts')}</p>
              <p className="text-lg font-semibold text-orange-400">
                {formatNumber(cumulativeData.total_cost, 2)} <span className="text-sm text-slate-400">{cumulativeData.currency}</span>
              </p>
            </div>
            <div className="bg-slate-800/50 rounded-lg p-3">
              <p className="text-xs text-slate-400">{t('monitor.power.electricityPrice')}</p>
              <p className="text-lg font-semibold text-slate-300">
                {formatNumber(cumulativeData.cost_per_kwh, 2)} <span className="text-sm text-slate-400">{cumulativeData.currency}/kWh</span>
              </p>
            </div>
            <div className="bg-slate-800/50 rounded-lg p-3">
              <p className="text-xs text-slate-400">{t('monitor.power.dataPoints')}</p>
              <p className="text-lg font-semibold text-slate-300">
                {cumulativeData.data_points.length}
              </p>
            </div>
          </div>
        )}

        {/* Chart */}
        {cumulativeLoading ? (
          <div className="flex items-center justify-center py-12">
            <div className="inline-block h-8 w-8 animate-spin rounded-full border-4 border-slate-600 border-t-blue-500" />
          </div>
        ) : cumulativeData && cumulativeData.data_points.length > 0 ? (
          <div className="h-[300px] sm:h-[350px]">
            <ResponsiveContainer width="100%" height="100%">
              <ComposedChart
                data={cumulativeData.data_points.map((dp) => ({
                  time: formatTimeForRange(dp.timestamp, cumulativePeriod as ChartTimeRange, i18n.language),
                  fullTime: parseUtcTimestamp(dp.timestamp).toLocaleString(i18n.language),
                  kwh: dp.cumulative_kwh,
                  cost: dp.cumulative_cost,
                  watts: dp.instant_watts,
                }))}
                margin={{ top: 10, right: 10, left: 0, bottom: 0 }}
              >
                <defs>
                  <linearGradient id="colorKwh" x1="0" y1="0" x2="0" y2="1">
                    <stop offset="5%" stopColor="#10b981" stopOpacity={0.3} />
                    <stop offset="95%" stopColor="#10b981" stopOpacity={0} />
                  </linearGradient>
                </defs>
                <CartesianGrid strokeDasharray="3 3" stroke="#334155" />
                <XAxis
                  dataKey="time"
                  stroke="#64748b"
                  fontSize={11}
                  tickLine={false}
                  interval="preserveStartEnd"
                  minTickGap={cumulativePeriod === 'week' ? 70 : 40}
                />
                <YAxis
                  yAxisId="left"
                  stroke="#10b981"
                  fontSize={11}
                  tickLine={false}
                  axisLine={false}
                  tickFormatter={(v) => formatNumber(v, 2)}
                  label={{ value: 'kWh', angle: -90, position: 'insideLeft', fill: '#10b981', fontSize: 11 }}
                />
                <YAxis
                  yAxisId="right"
                  orientation="right"
                  stroke="#f97316"
                  fontSize={11}
                  tickLine={false}
                  axisLine={false}
                  tickFormatter={(v) => formatNumber(v, 2)}
                  label={{ value: cumulativeData.currency, angle: 90, position: 'insideRight', fill: '#f97316', fontSize: 11 }}
                />
                <Tooltip
                  contentStyle={{
                    backgroundColor: '#1e293b',
                    border: '1px solid #334155',
                    borderRadius: '8px',
                    fontSize: '12px',
                  }}
                  labelStyle={{ color: '#94a3b8' }}
                  formatter={(value: number, name: string) => {
                    if (name === 'kwh') return [`${formatNumber(value, 4)} kWh`, t('monitor.power.consumption')];
                    if (name === 'cost') return [`${formatNumber(value, 4)} ${cumulativeData.currency}`, t('monitor.power.costsLabel')];
                    if (name === 'watts') return [`${formatNumber(value, 1)} W`, t('monitor.power.powerLabel')];
                    return [value, name];
                  }}
                  labelFormatter={(label, payload) => {
                    if (payload && payload[0]) {
                      return payload[0].payload.fullTime;
                    }
                    return label;
                  }}
                />
                <Legend
                  wrapperStyle={{ fontSize: '12px' }}
                  formatter={(value) => {
                    if (value === 'kwh') return t('monitor.power.consumptionKwh');
                    if (value === 'cost') return `${t('monitor.power.costsLabel')} (${cumulativeData.currency})`;
                    return value;
                  }}
                />
                <Area
                  yAxisId="left"
                  type="monotone"
                  dataKey="kwh"
                  stroke="#10b981"
                  strokeWidth={2}
                  fill="url(#colorKwh)"
                  name="kwh"
                />
                <Line
                  yAxisId="right"
                  type="monotone"
                  dataKey="cost"
                  stroke="#f97316"
                  strokeWidth={2}
                  dot={false}
                  name="cost"
                />
              </ComposedChart>
            </ResponsiveContainer>
          </div>
        ) : (
          <div className="text-center py-8 text-slate-400">
            {t('monitor.noDataForPeriod')}
          </div>
        )}
      </div>
    </div>
  );
}
