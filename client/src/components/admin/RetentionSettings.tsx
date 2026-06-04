import { useCallback, useEffect, useMemo, useState } from 'react'
import { useTranslation } from 'react-i18next'
import toast from 'react-hot-toast'
import { RefreshCw, Save } from 'lucide-react'
import { getRetentionConfig, updateRetentionConfig } from '../../api/monitoring'
import type { RetentionConfig } from '../../api/monitoring'
import { METRIC_CONFIG, DEFAULT_METRIC_CONFIG } from './metricConfig'

const MIN_HOURS = 1
const MAX_HOURS = 8760
const PRESETS = [
  { days: 1, hours: 24 },
  { days: 7, hours: 168 },
  { days: 14, hours: 336 },
  { days: 30, hours: 720 },
  { days: 90, hours: 2160 },
]

const hoursToDays = (hours: number): number => Math.round((hours / 24) * 10) / 10
const isValid = (v: number): boolean => Number.isInteger(v) && v >= MIN_HOURS && v <= MAX_HOURS

export default function RetentionSettings() {
  const { t } = useTranslation('admin')
  const [configs, setConfigs] = useState<RetentionConfig[]>([])
  const [edited, setEdited] = useState<Record<string, number>>({})
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const load = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const data = await getRetentionConfig()
      setConfigs(data.configs)
      setEdited({})
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : 'Failed to load retention config')
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => { load() }, [load])

  const valueFor = (c: RetentionConfig): number =>
    c.metric_type in edited ? edited[c.metric_type] : c.retention_hours

  const setValue = (metric: string, hours: number) =>
    setEdited(prev => ({ ...prev, [metric]: hours }))

  const dirty = useMemo(
    () => configs.filter(c => c.metric_type in edited && edited[c.metric_type] !== c.retention_hours),
    [configs, edited],
  )
  const hasInvalid = useMemo(() => dirty.some(c => !isValid(edited[c.metric_type])), [dirty, edited])

  const handleSave = async () => {
    if (dirty.length === 0 || hasInvalid) return
    setSaving(true)
    try {
      await Promise.all(dirty.map(c => updateRetentionConfig(c.metric_type, edited[c.metric_type])))
      toast.success(t('retentionSettings.saved'))
      await load()
    } catch {
      toast.error(t('retentionSettings.saveFailed'))
    } finally {
      setSaving(false)
    }
  }

  if (loading) {
    return (
      <div className="flex items-center justify-center py-16 gap-3">
        <RefreshCw className="w-5 h-5 text-blue-400 animate-spin" />
        <span className="text-slate-400 text-sm">{t('retentionSettings.loading')}</span>
      </div>
    )
  }

  if (error) {
    return <div className="bg-red-500/10 border border-red-500/30 rounded-lg px-4 py-3 text-red-400 text-sm">{error}</div>
  }

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between gap-3">
        <div>
          <h3 className="text-lg font-semibold text-white">{t('retentionSettings.title')}</h3>
          <p className="text-xs text-slate-400 mt-1">{t('retentionSettings.hint')}</p>
        </div>
        <button
          data-testid="retention-save"
          onClick={handleSave}
          disabled={saving || dirty.length === 0 || hasInvalid}
          className="inline-flex items-center gap-2 px-4 py-2 rounded-lg bg-blue-500/20 border border-blue-500/40 text-blue-300 hover:bg-blue-500/30 disabled:opacity-40 disabled:cursor-not-allowed transition-colors text-sm"
        >
          <Save className={`w-4 h-4 ${saving ? 'animate-pulse' : ''}`} />
          {t('retentionSettings.save')}
        </button>
      </div>

      <div className="space-y-3">
        {configs.map(c => {
          const cfg = METRIC_CONFIG[c.metric_type] || DEFAULT_METRIC_CONFIG
          const Icon = cfg.icon
          const value = valueFor(c)
          const invalid = !isValid(value)
          return (
            <div key={c.metric_type} className="card !p-4">
              <div className="flex flex-col sm:flex-row sm:items-center gap-3">
                <div className="flex items-center gap-2 sm:w-48">
                  <Icon className="w-4 h-4 text-slate-300" />
                  <span className="text-sm font-medium text-white">
                    {cfg.labelKey ? t(cfg.labelKey) : c.metric_type}
                  </span>
                </div>
                <div className="flex items-center gap-2">
                  <input
                    data-testid={`retention-input-${c.metric_type}`}
                    type="number"
                    min={MIN_HOURS}
                    max={MAX_HOURS}
                    value={value}
                    onChange={e => setValue(c.metric_type, Number(e.target.value))}
                    className={`w-28 bg-slate-800/60 border rounded-lg px-3 py-2 text-sm text-slate-200 focus:outline-none ${invalid ? 'border-red-500/60' : 'border-slate-700/50 focus:border-blue-500/50'}`}
                  />
                  <span className="text-xs text-slate-400">{t('retentionSettings.hours')}</span>
                  <span className="text-xs text-sky-400">
                    {t('retentionSettings.approxDays', { count: hoursToDays(value) })}
                  </span>
                </div>
                <div className="flex flex-wrap gap-1.5">
                  {PRESETS.map(p => (
                    <button
                      key={p.days}
                      data-testid={`retention-preset-${c.metric_type}-${p.hours}`}
                      onClick={() => setValue(c.metric_type, p.hours)}
                      className={`px-2 py-1 rounded-md text-xs border transition-colors ${value === p.hours ? 'bg-blue-500/20 border-blue-500/40 text-blue-300' : 'bg-slate-800/60 border-slate-700/50 text-slate-300 hover:bg-slate-700/50'}`}
                    >
                      {t('retentionSettings.presetDays', { count: p.days })}
                    </button>
                  ))}
                </div>
              </div>
              {invalid && <p className="text-xs text-red-400 mt-2">{t('retentionSettings.validation')}</p>}
            </div>
          )
        })}
      </div>
    </div>
  )
}
