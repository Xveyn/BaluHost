/**
 * BenchmarkResults component
 *
 * Displays benchmark results in a CrystalDiskMark-style grid:
 * - Sequential read/write in MB/s
 * - Random read/write in IOPS
 * - Color-coded values for easy comparison
 */
import { useTranslation } from 'react-i18next';
import { formatThroughput, formatIops } from '../../api/benchmark';
import type { BenchmarkSummaryResults } from '../../api/benchmark';

interface BenchmarkResultsProps {
  results: BenchmarkSummaryResults;
  diskName: string;
  diskModel?: string;
}

interface ResultRowProps {
  label: string;
  readValue: string;
  writeValue: string;
  unit?: string;
}

function ResultRow({ label, readValue, writeValue }: ResultRowProps) {
  return (
    <div className="grid grid-cols-3 gap-2">
      <div className="text-sm text-slate-400 font-medium py-2">{label}</div>
      <div className="bg-slate-700/50 rounded-lg py-2 px-3 text-center">
        <span className="text-sky-400 font-mono text-lg font-semibold">{readValue}</span>
      </div>
      <div className="bg-slate-700/50 rounded-lg py-2 px-3 text-center">
        <span className="text-rose-400 font-mono text-lg font-semibold">{writeValue}</span>
      </div>
    </div>
  );
}

export default function BenchmarkResults({ results, diskName, diskModel }: BenchmarkResultsProps) {
  const { t } = useTranslation('system');
  // Check if we have any results
  const hasResults =
    results.seq_read_mbps !== undefined ||
    results.seq_write_mbps !== undefined ||
    results.rand_read_iops !== undefined ||
    results.rand_write_iops !== undefined;

  if (!hasResults) {
    return (
      <div className="bg-slate-800 rounded-lg p-6 border border-slate-700 text-center text-slate-400">
        {t('benchmark.noResults')}
      </div>
    );
  }

  return (
    <div className="bg-slate-800 rounded-lg border border-slate-700 overflow-hidden">
      {/* Header */}
      <div className="bg-slate-900 px-4 py-3 border-b border-slate-700">
        <div className="flex items-center justify-between">
          <div>
            <h3 className="font-semibold text-white">{diskName}</h3>
            {diskModel && <p className="text-xs text-slate-400 mt-0.5">{diskModel}</p>}
          </div>
          <div className="text-xs text-slate-500 font-mono">{t('benchmark.crystalDiskMarkStyle')}</div>
        </div>
      </div>

      {/* Results grid */}
      <div className="p-4">
        {/* Column headers */}
        <div className="grid grid-cols-3 gap-2 mb-3">
          <div className="text-sm font-medium text-slate-500"></div>
          <div className="text-center text-sm font-medium text-sky-500">{t('benchmark.read')}</div>
          <div className="text-center text-sm font-medium text-rose-500">{t('benchmark.write')}</div>
        </div>

        {/* Sequential results */}
        <div className="space-y-2 mb-4">
          <ResultRow
            label="SEQ1M Q8T1"
            readValue={formatThroughput(results.seq_read_mbps)}
            writeValue={formatThroughput(results.seq_write_mbps)}
          />
          {(results.seq_read_q1_mbps !== undefined || results.seq_write_q1_mbps !== undefined) && (
            <ResultRow
              label="SEQ1M Q1T1"
              readValue={formatThroughput(results.seq_read_q1_mbps)}
              writeValue={formatThroughput(results.seq_write_q1_mbps)}
            />
          )}
        </div>

        {/* Divider */}
        <div className="border-t border-slate-700 my-4" />

        {/* Random results */}
        <div className="space-y-2">
          <ResultRow
            label="RND4K Q32T1"
            readValue={formatIops(results.rand_read_iops)}
            writeValue={formatIops(results.rand_write_iops)}
          />
          {(results.rand_read_q1_iops !== undefined || results.rand_write_q1_iops !== undefined) && (
            <ResultRow
              label="RND4K Q1T1"
              readValue={formatIops(results.rand_read_q1_iops)}
              writeValue={formatIops(results.rand_write_q1_iops)}
            />
          )}
        </div>

        {/* Legend */}
        <div className="mt-4 pt-3 border-t border-slate-700">
          <div className="flex flex-wrap gap-4 text-xs text-slate-500">
            <span><strong>SEQ</strong> = {t('benchmark.sequential')}</span>
            <span><strong>RND</strong> = {t('benchmark.random')}</span>
            <span><strong>Q</strong> = {t('benchmark.queueDepth')}</span>
            <span><strong>T</strong> = {t('benchmark.threads')}</span>
          </div>
        </div>
      </div>
    </div>
  );
}

/**
 * Compact version of results for history view
 */
export function BenchmarkResultsCompact({ results }: { results: BenchmarkSummaryResults }) {
  const { t } = useTranslation('system');
  return (
    <div className="grid grid-cols-2 gap-2 text-sm">
      <div className="flex justify-between">
        <span className="text-slate-500">{t('benchmark.seqRead')}:</span>
        <span className="text-sky-400 font-mono">{formatThroughput(results.seq_read_mbps)}</span>
      </div>
      <div className="flex justify-between">
        <span className="text-slate-500">{t('benchmark.seqWrite')}:</span>
        <span className="text-rose-400 font-mono">{formatThroughput(results.seq_write_mbps)}</span>
      </div>
      <div className="flex justify-between">
        <span className="text-slate-500">{t('benchmark.randRead')}:</span>
        <span className="text-sky-400 font-mono">{formatIops(results.rand_read_iops)} IOPS</span>
      </div>
      <div className="flex justify-between">
        <span className="text-slate-500">{t('benchmark.randWrite')}:</span>
        <span className="text-rose-400 font-mono">{formatIops(results.rand_write_iops)} IOPS</span>
      </div>
    </div>
  );
}
