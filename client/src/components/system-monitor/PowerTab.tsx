/**
 * PowerTab -- Power/energy monitoring tab.
 *
 * Thin orchestrator: owns the chart selection state, delegates data to
 * `usePowerTabData` + `useEnergyPrice`, and composes the `power-tab/*` units.
 */

import { useState } from 'react';
import { useQueryClient } from '@tanstack/react-query';
import { useTranslation } from 'react-i18next';
import { PluginBadge } from '../ui/PluginBadge';
import { queryKeys } from '../../lib/queryKeys';
import { usePowerTabData } from '../../hooks/usePowerTabData';
import { useEnergyPrice } from '../../hooks/useEnergyPrice';
import {
  PowerLoading,
  PowerError,
  PowerEmptyState,
  PowerSummaryCards,
  PowerDeviceCard,
  EnergyPriceEditor,
  ChartDeviceTabs,
  ChartModePeriodControls,
  CustomRangePicker,
  EnergyChartSummary,
  EnergyChart,
} from './power-tab';

type CumulativePeriod = 'today' | 'week' | 'month' | 'custom';
type ChartMode = 'cumulative' | 'instant';

export function PowerTab() {
  const { t, i18n } = useTranslation(['system', 'common']);
  const queryClient = useQueryClient();

  // Chart selection state
  const [chartMode, setChartMode] = useState<ChartMode>('cumulative');
  const [cumulativePeriod, setCumulativePeriod] = useState<CumulativePeriod>('today');
  const [selectedDeviceId, setSelectedDeviceId] = useState<number | null>(null);
  // Custom range (applied values drive fetching; drafts live in CustomRangePicker)
  const [customStart, setCustomStart] = useState<string | null>(null);
  const [customEnd, setCustomEnd] = useState<string | null>(null);

  const data = usePowerTabData({ selectedDeviceId, cumulativePeriod, customStart, customEnd });
  const price = useEnergyPrice(() =>
    queryClient.invalidateQueries({
      queryKey: queryKeys.powerTab.cumulative(
        selectedDeviceId,
        data.cumulativeKeyArgs.period,
        data.cumulativeKeyArgs.start,
        data.cumulativeKeyArgs.end,
      ),
    }),
  );

  if (data.loading) return <PowerLoading />;
  if (data.error) return <PowerError error={data.error} />;
  if (data.devices.length === 0) return <PowerEmptyState />;

  return (
    <div className="space-y-4 sm:space-y-6 min-w-0">
      {/* Total Power Stats */}
      <PowerSummaryCards
        totalCurrentPower={data.totalCurrentPower}
        onlineCount={data.devices.filter((d) => d.is_online).length}
        deviceCount={data.devices.length}
      />

      {/* Per-device stats */}
      {data.devices.map((device) => (
        <PowerDeviceCard key={device.id} device={device} />
      ))}

      {/* Cumulative Energy Chart Section */}
      <div className="card border-slate-800/60 bg-slate-900/55 p-4 sm:p-6">
        {/* Device tabs for chart */}
        <ChartDeviceTabs
          devices={data.devices}
          selectedDeviceId={selectedDeviceId}
          onSelect={setSelectedDeviceId}
        />

        {/* Header with Price Config */}
        <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3 mb-4">
          <div className="flex items-center gap-3 flex-wrap">
            <h3 className="text-base sm:text-lg font-semibold text-white flex items-center">
              {chartMode === 'cumulative'
                ? t('monitor.power.cumulativeConsumptionCosts')
                : t('monitor.power.instantPowerConsumption')}
              <PluginBadge pluginName={data.powerPluginName} size="sm" className="ml-2" />
            </h3>
            {price.priceConfig && (
              <EnergyPriceEditor
                priceConfig={price.priceConfig}
                editing={price.editingPrice}
                priceInput={price.priceInput}
                saving={price.savingPrice}
                onEdit={() => price.setEditingPrice(true)}
                onInputChange={price.setPriceInput}
                onSave={price.savePrice}
                onCancel={() => {
                  price.setEditingPrice(false);
                  price.setPriceInput(price.priceConfig!.cost_per_kwh.toString());
                }}
              />
            )}
          </div>

          {/* Mode Toggle + Period Selector */}
          <ChartModePeriodControls
            chartMode={chartMode}
            onModeChange={setChartMode}
            cumulativePeriod={cumulativePeriod}
            onPeriodChange={setCumulativePeriod}
            customRange={
              <CustomRangePicker
                active={cumulativePeriod === 'custom'}
                onApply={(startIso, endIso) => {
                  setCustomStart(startIso);
                  setCustomEnd(endIso);
                  setCumulativePeriod('custom');
                }}
              />
            }
          />
        </div>

        {/* Summary Stats */}
        {data.cumulativeData && (
          <EnergyChartSummary chartMode={chartMode} cumulativeData={data.cumulativeData} />
        )}

        {/* Chart */}
        <EnergyChart
          chartMode={chartMode}
          cumulativeData={data.cumulativeData}
          cumulativeLoading={data.cumulativeLoading}
          cumulativePeriod={cumulativePeriod}
          language={i18n.language}
        />
      </div>
    </div>
  );
}
