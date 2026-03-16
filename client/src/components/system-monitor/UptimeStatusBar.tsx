/**
 * UptimeStatusBar -- Status-page-style horizontal bar visualization.
 *
 * Renders N vertical segments color-coded by uptime status,
 * similar to status.anthropic.com or statuspage.io.
 */

import { useMemo } from 'react';
import { useTranslation } from 'react-i18next';
import type { TimeRange, UptimeSample } from '../../api/monitoring';
import { parseUtcTimestamp } from '../../lib/dateUtils';

interface UptimeTimeslot {
  startTime: Date;
  endTime: Date;
  sampleCount: number;
  uptimePercent: number;
  status: 'online' | 'offline' | 'partial' | 'no-data';
  restartCount: number;
}

interface UptimeStatusBarProps {
  samples: UptimeSample[];
  timeRange: TimeRange;
  label: string;
  uptimeField: 'server_uptime_seconds' | 'system_uptime_seconds';
}

const SEGMENT_CONFIG: Record<TimeRange, { segments: number; durationMs: number }> = {
  '10m': { segments: 60, durationMs: 10 * 60 * 1000 },
  '1h':  { segments: 72, durationMs: 60 * 60 * 1000 },
  '24h': { segments: 90, durationMs: 24 * 60 * 60 * 1000 },
  '7d':  { segments: 90, durationMs: 7 * 24 * 60 * 60 * 1000 },
};

const TIME_LABELS: Record<TimeRange, { left: string; right: string }> = {
  '10m': { left: 'ago10m', right: 'now' },
  '1h':  { left: 'ago1h',  right: 'now' },
  '24h': { left: 'ago24h', right: 'now' },
  '7d':  { left: 'ago7d',  right: 'today' },
};

function getSlotColor(slot: UptimeTimeslot): string {
  if (slot.status === 'no-data') return '#334155';
  if (slot.uptimePercent === 100) return '#22c55e';
  if (slot.uptimePercent >= 95) return '#84cc16';
  if (slot.uptimePercent >= 75) return '#eab308';
  if (slot.uptimePercent >= 50) return '#f97316';
  if (slot.uptimePercent > 0) return '#ef4444';
  return '#dc2626';
}

function formatSlotTime(date: Date): string {
  return date.toLocaleString(undefined, {
    month: 'short',
    day: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
  });
}

export function UptimeStatusBar({ samples, timeRange, label, uptimeField }: UptimeStatusBarProps) {
  const { t } = useTranslation('system');
  const config = SEGMENT_CONFIG[timeRange];

  const timeslots = useMemo<UptimeTimeslot[]>(() => {
    const clientNow = Date.now();
    const bucketDuration = config.durationMs / config.segments;

    // Parse all samples
    const allParsed = samples
      .map(s => ({ ...s, _time: parseUtcTimestamp(s.timestamp).getTime() }))
      .sort((a, b) => a._time - b._time);

    // Use the latest sample timestamp as reference for "now" if available.
    // This prevents clock/timezone differences between server and client
    // from causing all samples to be filtered out.
    const now = allParsed.length > 0
      ? Math.max(clientNow, allParsed[allParsed.length - 1]._time)
      : clientNow;
    const rangeStart = now - config.durationMs;

    const parsed = allParsed.filter(s => s._time >= rangeStart && s._time <= now);

    const slots: UptimeTimeslot[] = [];

    for (let i = 0; i < config.segments; i++) {
      const bucketStart = rangeStart + i * bucketDuration;
      const bucketEnd = bucketStart + bucketDuration;

      // Samples in this bucket
      const bucketSamples = parsed.filter(s => s._time >= bucketStart && s._time < bucketEnd);

      if (bucketSamples.length === 0) {
        slots.push({
          startTime: new Date(bucketStart),
          endTime: new Date(bucketEnd),
          sampleCount: 0,
          uptimePercent: 0,
          status: 'no-data',
          restartCount: 0,
        });
        continue;
      }

      // Detect restarts: uptime field drops between consecutive samples
      let restartCount = 0;
      for (let j = 1; j < bucketSamples.length; j++) {
        if (bucketSamples[j][uptimeField] < bucketSamples[j - 1][uptimeField]) {
          restartCount++;
        }
      }

      // Also check against the last sample from the previous bucket
      if (i > 0 && slots[i - 1].status !== 'no-data') {
        const prevBucketSamples = parsed.filter(s => {
          const prevStart = rangeStart + (i - 1) * bucketDuration;
          const prevEnd = prevStart + bucketDuration;
          return s._time >= prevStart && s._time < prevEnd;
        });
        if (prevBucketSamples.length > 0) {
          const lastPrev = prevBucketSamples[prevBucketSamples.length - 1];
          if (bucketSamples[0][uptimeField] < lastPrev[uptimeField]) {
            restartCount++;
          }
        }
      }

      // Coverage: how much of the bucket duration is covered by samples
      const firstSampleTime = bucketSamples[0]._time;
      const lastSampleTime = bucketSamples[bucketSamples.length - 1]._time;
      const coverage = bucketSamples.length === 1
        ? Math.min(1, bucketSamples.length / 3) // Single sample: partial coverage
        : Math.min(1, (lastSampleTime - firstSampleTime) / bucketDuration + 0.1);

      const uptimePercent = restartCount > 0
        ? Math.max(0, Math.round((1 - restartCount * 0.2) * coverage * 100))
        : Math.round(coverage * 100);

      const clampedPercent = Math.min(100, Math.max(0, uptimePercent));

      slots.push({
        startTime: new Date(bucketStart),
        endTime: new Date(bucketEnd),
        sampleCount: bucketSamples.length,
        uptimePercent: restartCount > 0 ? clampedPercent : 100,
        status: restartCount > 0 ? 'partial' : 'online',
        restartCount,
      });
    }

    return slots;
  }, [samples, config, uptimeField]);

  // Overall uptime percentage
  const overallUptime = useMemo(() => {
    const monitored = timeslots.filter(s => s.status !== 'no-data');
    if (monitored.length === 0) return null;
    return Math.round(
      (monitored.reduce((sum, s) => sum + s.uptimePercent, 0) / monitored.length) * 100
    ) / 100;
  }, [timeslots]);

  const labels = TIME_LABELS[timeRange];

  return (
    <div className="relative rounded-2xl border border-slate-800/60 bg-slate-900/55 p-3 sm:p-4 shadow-[0_20px_60px_rgba(2,6,23,0.55)] backdrop-blur-xl">
      {/* Header: label + overall uptime */}
      <div className="flex items-center justify-between mb-2">
        <div className="flex items-center gap-2">
          <span
            className="inline-block w-2 h-2 rounded-full"
            style={{ backgroundColor: overallUptime === null ? '#334155' : overallUptime === 100 ? '#22c55e' : overallUptime >= 95 ? '#84cc16' : '#ef4444' }}
          />
          <span className="text-sm font-medium text-white">{label}</span>
        </div>
        <span className="text-sm text-slate-400">
          {overallUptime !== null
            ? t('monitor.uptime.uptimePercent', { percent: overallUptime.toFixed(2) })
            : t('monitor.uptime.noData')}
        </span>
      </div>

      {/* Status bar segments */}
      <div className="flex h-8 sm:h-10">
        {timeslots.map((slot, idx) => (
          <div
            key={idx}
            className={`group relative flex-1 min-w-0 transition-opacity hover:opacity-80 cursor-pointer${
              idx === 0 ? ' rounded-l' : ''}${idx === config.segments - 1 ? ' rounded-r' : ''}`}
            style={{ backgroundColor: getSlotColor(slot) }}
          >
            {/* Tooltip */}
            <div
              className={`hidden group-hover:block absolute bottom-full mb-2 z-50 w-48 p-2 rounded-lg bg-slate-800 border border-slate-700 shadow-xl text-xs ${
                idx < 5 ? 'left-0' : idx > config.segments - 5 ? 'right-0' : 'left-1/2 -translate-x-1/2'
              }`}
            >
              <p className="text-slate-300 font-medium">
                {formatSlotTime(slot.startTime)}
              </p>
              <p className="text-slate-400">
                → {formatSlotTime(slot.endTime)}
              </p>
              {slot.status === 'no-data' ? (
                <p className="text-slate-500 mt-1">{t('monitor.uptime.noDataSlot')}</p>
              ) : (
                <>
                  <p className="text-white mt-1">
                    {t('monitor.uptime.slotUptime', { percent: slot.uptimePercent })}
                  </p>
                  {slot.restartCount > 0 && (
                    <p className="text-amber-400">
                      {t('monitor.uptime.restartDetected', { count: slot.restartCount })}
                    </p>
                  )}
                </>
              )}
            </div>
          </div>
        ))}
      </div>

      {/* Time labels */}
      <div className="flex justify-between mt-1.5">
        <span className="text-[10px] sm:text-xs text-slate-500">
          {t(`monitor.uptime.${labels.left}`)}
        </span>
        <span className="text-[10px] sm:text-xs text-slate-500">
          {t(`monitor.uptime.${labels.right}`)}
        </span>
      </div>
    </div>
  );
}
