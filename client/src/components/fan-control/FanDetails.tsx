import { TrendingUp } from 'lucide-react';
import type { FanInfo, FanCurvePoint, FanCurveProfile } from '../../api/fan-control';
import CurveTypeSelector from './CurveTypeSelector';
import CurveEditorFlat from './CurveEditorFlat';
import CurveEditorTarget from './CurveEditorTarget';
import CurveEditorMix from './CurveEditorMix';
import CurveEditorSync from './CurveEditorSync';
import AdvancedFanSettings from './AdvancedFanSettings';
import GpuManualModeToggle from './GpuManualModeToggle';
import FanCurveChart from './FanCurveChart';
import { useTranslation } from 'react-i18next';
import { useFanCurveEditor } from '../../hooks/useFanCurveEditor';
import {
  FanPresetProfileButtons,
  FanCurveGraphControls,
  FanCurveTableEditor,
  FanStatsGrid,
} from './fan-details';

interface FanDetailsProps {
  fan: FanInfo;
  onCurveUpdate: (fanId: string, points: FanCurvePoint[]) => void;
  isReadOnly: boolean;
  onEditingChange?: (isEditing: boolean) => void;
  onConfigUpdate?: () => void;
  profiles?: FanCurveProfile[];
  onApplyProfile?: (profile: FanCurveProfile) => void;
  allFans?: FanInfo[];
}

export default function FanDetails({ fan, onCurveUpdate, isReadOnly, onEditingChange, onConfigUpdate, profiles, onApplyProfile, allFans }: FanDetailsProps) {
  const { t } = useTranslation(['system', 'common']);
  const editor = useFanCurveEditor(fan, {
    isReadOnly, onCurveUpdate, onConfigUpdate, onEditingChange, onApplyProfile, profiles,
  });

  return (
    <div className="card">
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 mb-4">
        <h2 className="text-xl font-bold text-white flex items-center gap-2">
          <TrendingUp className="w-6 h-6 text-sky-400" />
          {fan.name} - {t('system:fanControl.curve.title')}
        </h2>

        <FanPresetProfileButtons
          isReadOnly={isReadOnly}
          systemProfiles={editor.systemProfiles}
          userProfiles={editor.userProfiles}
          showMoreProfiles={editor.showMoreProfiles}
          onToggleMore={() => editor.setShowMoreProfiles(!editor.showMoreProfiles)}
          onApplyPreset={editor.handleApplyPreset}
          onApplyProfile={editor.handleApplyProfileCurve}
        />
      </div>

      {/* Curve Editor */}
      <div className="mb-4">
        <div className="mb-4">
          <CurveTypeSelector value={editor.curveType} onChange={editor.handleCurveTypeChange} disabled={isReadOnly} />
        </div>

        {/* Graph curve: original chart + table editor */}
        {editor.curveType === 'graph' && (
          <>
            <FanCurveGraphControls
              viewMode={editor.viewMode}
              onViewModeChange={editor.setViewMode}
              hasUnsavedChanges={editor.hasUnsavedChanges}
              isReadOnly={isReadOnly}
              onSave={editor.handleSaveCurve}
              onDiscard={editor.handleDiscardChanges}
            />

            {editor.viewMode === 'chart' && (
              <div className="mt-4">
                <FanCurveChart
                  points={editor.curvePoints}
                  onPointsChange={editor.handleChartPointsChange}
                  currentTemp={fan.temperature_celsius}
                  currentPWM={fan.pwm_percent}
                  minPWM={fan.min_pwm_percent}
                  maxPWM={fan.max_pwm_percent}
                  emergencyTemp={fan.emergency_temp_celsius}
                  isEditing={editor.canEdit}
                  isReadOnly={isReadOnly}
                />
              </div>
            )}

            {editor.viewMode === 'table' && (
              <FanCurveTableEditor
                curvePoints={editor.curvePoints}
                canEdit={editor.canEdit}
                minPwm={fan.min_pwm_percent}
                maxPwm={fan.max_pwm_percent}
                onUpdatePoint={editor.handleUpdatePoint}
                onRemovePoint={editor.handleRemovePoint}
                onAddPoint={editor.handleAddPoint}
              />
            )}
          </>
        )}

        {editor.curveType === 'flat' && (
          <CurveEditorFlat
            value={fan.flat_pwm_percent ?? 50}
            onChange={editor.handleFlatChange}
            disabled={isReadOnly}
          />
        )}

        {editor.curveType === 'target' && (
          <CurveEditorTarget
            targetTemp={fan.target_temp_celsius ?? 65}
            targetPwm={fan.target_pwm_percent ?? 80}
            onChange={editor.handleTargetChange}
            disabled={isReadOnly}
          />
        )}

        {editor.curveType === 'mix' && (
          <CurveEditorMix
            profiles={profiles ?? []}
            curveAId={fan.mix_curve_a_id ?? null}
            curveBId={fan.mix_curve_b_id ?? null}
            fn={(fan.mix_function as 'max' | 'sum') ?? 'max'}
            onChange={editor.handleMixChange}
            disabled={isReadOnly}
          />
        )}

        {editor.curveType === 'sync' && (
          <CurveEditorSync
            allFans={allFans ?? []}
            currentFanId={fan.fan_id}
            syncFanId={fan.sync_fan_id ?? null}
            onChange={editor.handleSyncChange}
            disabled={isReadOnly}
          />
        )}
      </div>

      {/* Advanced Settings */}
      <div className="mt-4">
        <AdvancedFanSettings fan={fan} onChange={editor.handleAdvancedChange} disabled={isReadOnly} />
      </div>

      {/* GPU Manual Mode Toggle (AMD GPU fans only) */}
      {fan.is_gpu_fan && fan.gpu_vendor === 'amd' && (
        <div className="mt-4">
          <GpuManualModeToggle
            fanId={fan.fan_id}
            enabled={editor.localGpuManualEnabled}
            onChange={editor.setLocalGpuManualEnabled}
          />
        </div>
      )}

      {/* Fan Stats */}
      <FanStatsGrid
        fan={fan}
        canEdit={editor.canEdit}
        hysteresis={editor.hysteresis}
        isUpdatingHysteresis={editor.isUpdatingHysteresis}
        hysteresisChanged={editor.hysteresisChanged}
        onHysteresisChange={editor.handleHysteresisChange}
        onHysteresisSave={editor.handleHysteresisSave}
      />
    </div>
  );
}
