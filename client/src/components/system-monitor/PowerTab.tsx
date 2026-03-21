/**
 * PowerTab -- Power/energy monitoring tab with smart device integration.
 */

import { useState, useEffect, useCallback } from 'react';
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
import { getApiErrorMessage } from '../../lib/errorHandling';
import { formatTimeForRange, parseUtcTimestamp } from '../../lib/dateUtils';
import type { ChartTimeRange } from '../../lib/dateUtils';
import { smartDevicesApi } from '../../api/smart-devices';
import type { SmartDevice, PowerSummary } from '../../api/smart-devices';
import {
  getEnergyPriceConfig,
  updateEnergyPriceConfig,
  getCumulativeEnergy,
  getCumulativeEnergyTotal,
  type EnergyPriceConfig,
  type CumulativeEnergyResponse,
} from '../../api/energy';
import { StatCard } from '../ui/StatCard';
import { PluginBadge } from '../ui/PluginBadge';
import { formatNumber } from '../../lib/formatters';
import { usePlugins } from '../../contexts/PluginContext';

type CumulativePeriod = 'today' | 'week' | 'month';

export function PowerTab() {
  const { t, i18n } = useTranslation(['system', 'common']);
  const { plugins } = usePlugins();
  const [devices, setDevices] = useState<SmartDevice[]>([]);
  const [powerSummary, setPowerSummary] = useState<PowerSummary | null>(null);
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
      const [listRes, summaryRes] = await Promise.all([
        smartDevicesApi.list(),
        smartDevicesApi.getPowerSummary(),
      ]);
      // Filter to devices with power_monitor capability
      const powerDevices = listRes.data.devices.filter(d => d.capabilities?.includes('power_monitor'));
      setDevices(powerDevices);
      setPowerSummary(summaryRes.data);
      setError(null);
    } catch (err: unknown) {
      const isAxiosLike = err != null && typeof err === 'object' && 'response' in err;
      const status = isAxiosLike ? (err as { response?: { status?: number } }).response?.status : undefined;
      if (status !== 404) {
        setError(getApiErrorMessage(err, 'Failed to load power data'));
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
      } catch {
        // Non-critical: price config will remain null
      }
    };
    fetchPriceConfig();
  }, []);

  // Fetch cumulative data with separate interval (60s - matches DB write interval)
  useEffect(() => {
    const fetchCumulative = async () => {
      setCumulativeLoading(true);
      try {
        const data = selectedDeviceId === null
          ? await getCumulativeEnergyTotal(cumulativePeriod)
          : await getCumulativeEnergy(selectedDeviceId, cumulativePeriod);
        setCumulativeData(data);
      } catch {
        // Non-critical: cumulative data will remain null
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
      const refreshData = selectedDeviceId === null
        ? getCumulativeEnergyTotal(cumulativePeriod)
        : getCumulativeEnergy(selectedDeviceId, cumulativePeriod);
      setCumulativeData(await refreshData);
    } catch (err: unknown) {
      toast.error(getApiErrorMessage(err, t('monitor.power.saveError')));
    } finally {
      setSavingPrice(false);
    }
  };

  useEffect(() => {
    fetchPower();
    const interval = setInterval(fetchPower, 5000);
    return () => clearInterval(interval);
  }, [fetchPower]);

  const totalCurrentPower = powerSummary?.total_watts ?? 0;
  const powerPluginName = devices.length > 0
    ? plugins.find(p => p.name === devices[0].plugin_name)?.display_name
    : undefined;

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

  if (devices.length === 0) {
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
        <p className="mt-4 text-slate-400">{t('monitor.power.noSmartDevices', 'No smart devices with power monitoring configured')}</p>
        <Link
          to="/smart-devices"
          className="inline-block mt-4 px-4 py-2 text-sm bg-sky-500/20 text-sky-400 hover:bg-sky-500/30 border border-sky-500/40 rounded-lg transition-colors"
        >
          {t('monitor.power.configureSmartDevices', 'Configure Smart Devices')} →
        </Link>
      </div>
    );
  }

  return (
    <div className="space-y-4 sm:space-y-6 min-w-0">
      {/* Total Power Stats */}
      <div className="grid grid-cols-1 min-[400px]:grid-cols-2 gap-3 sm:gap-5 lg:grid-cols-4">
        <StatCard
          label={t('monitor.power.currentPower')}
          value={formatNumber(totalCurrentPower, 1)}
          unit="W"
          color="yellow"
          icon={<span className="text-yellow-400 text-base sm:text-xl">⚡</span>}
        />
        <StatCard
          label={t('monitor.power.onlineDevices', 'Online')}
          value={devices.filter(d => d.is_online).length}
          unit={`/ ${devices.length}`}
          color="green"
          icon={<span className="text-green-400 text-base sm:text-xl">📊</span>}
        />
        <StatCard
          label={t('monitor.power.devices')}
          value={devices.length}
          color="blue"
          icon={<span className="text-blue-400 text-base sm:text-xl">#</span>}
        />
      </div>

      {/* Per-device stats */}
      {devices.map((device) => {
        const pm = device.state?.power_monitor as { current_power?: number; voltage?: number; current_ma?: number; energy_today_wh?: number } | undefined;
        const watts = pm?.current_power;
        const voltage = pm?.voltage;
        const currentA = pm?.current_ma != null ? pm.current_ma / 1000 : undefined;
        const energyToday = pm?.energy_today_wh != null ? pm.energy_today_wh / 1000 : undefined;

        return (
          <div key={device.id} className="card border-slate-800/60 bg-slate-900/55 p-4 sm:p-6">
            <div className="flex items-center justify-between mb-3 sm:mb-4">
              <h3 className="text-base sm:text-lg font-semibold text-white">{device.name}</h3>
              <span className={`text-xs px-2 py-0.5 rounded-full ${device.is_online ? 'bg-green-500/20 text-green-400' : 'bg-red-500/20 text-red-400'}`}>
                {device.is_online ? t('monitor.power.online', 'Online') : t('monitor.power.offline', 'Offline')}
              </span>
            </div>
            <div className="grid grid-cols-1 min-[400px]:grid-cols-2 gap-3 sm:gap-4 lg:grid-cols-4">
              <div>
                <p className="text-[10px] sm:text-xs text-slate-400">{t('monitor.power.powerLabel')}</p>
                <p className="text-lg sm:text-xl font-semibold text-white">
                  {watts != null ? formatNumber(watts, 1) : '-'} <span className="text-sm sm:text-base text-slate-400">W</span>
                </p>
              </div>
              <div>
                <p className="text-[10px] sm:text-xs text-slate-400">{t('monitor.power.voltage')}</p>
                <p className="text-lg sm:text-xl font-semibold text-white">
                  {voltage != null ? formatNumber(voltage, 1) : '-'} <span className="text-sm sm:text-base text-slate-400">V</span>
                </p>
              </div>
              <div>
                <p className="text-[10px] sm:text-xs text-slate-400">{t('monitor.power.current')}</p>
                <p className="text-lg sm:text-xl font-semibold text-white">
                  {currentA != null ? formatNumber(currentA, 3) : '-'} <span className="text-sm sm:text-base text-slate-400">A</span>
                </p>
              </div>
              <div>
                <p className="text-[10px] sm:text-xs text-slate-400">{t('monitor.power.today')}</p>
                <p className="text-lg sm:text-xl font-semibold text-white">
                  {energyToday != null ? formatNumber(energyToday, 2) : '-'} <span className="text-sm sm:text-base text-slate-400">kWh</span>
                </p>
              </div>
            </div>
          </div>
        );
      })}

      {/* Cumulative Energy Chart Section */}
      <div className="card border-slate-800/60 bg-slate-900/55 p-4 sm:p-6">
        {/* Device tabs for chart */}
        <div className="flex items-center gap-1 overflow-x-auto pb-2">
          <button
            onClick={() => setSelectedDeviceId(null)}
            className={`shrink-0 px-3 py-1.5 rounded-lg text-sm font-medium transition-colors ${
              selectedDeviceId === null
                ? 'bg-blue-600 text-white'
                : 'bg-gray-700/50 text-gray-400 hover:text-gray-200'
            }`}
          >
            {t('monitor.power.total')}
          </button>
          {devices
            .filter(d => d.is_active && d.capabilities?.includes('power_monitor'))
            .map(device => (
              <button
                key={device.id}
                onClick={() => setSelectedDeviceId(device.id)}
                className={`shrink-0 px-3 py-1.5 rounded-lg text-sm font-medium transition-colors ${
                  selectedDeviceId === device.id
                    ? 'bg-blue-600 text-white'
                    : 'bg-gray-700/50 text-gray-400 hover:text-gray-200'
                }`}
              >
                {device.name}
              </button>
            ))}
        </div>

        {/* Header with Price Config */}
        <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3 mb-4">
          <div className="flex items-center gap-3">
            <h3 className="text-base sm:text-lg font-semibold text-white flex items-center">
              {t('monitor.power.cumulativeConsumptionCosts')}
              <PluginBadge pluginName={powerPluginName} size="sm" className="ml-2" />
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
          <div className="grid grid-cols-1 min-[400px]:grid-cols-2 sm:grid-cols-4 gap-3 mb-4">
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
