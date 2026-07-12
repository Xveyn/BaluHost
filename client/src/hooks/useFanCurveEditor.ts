import { useState, useEffect, useMemo, useRef, useCallback } from 'react';
import toast from 'react-hot-toast';
import { useTranslation } from 'react-i18next';
import type { FanInfo, FanCurvePoint, FanCurveProfile } from '../api/fan-control';
import { CURVE_PRESETS, updateFanConfig } from '../api/fan-control';
import { handleApiError } from '../lib/errorHandling';
import type { CurveType } from '../components/fan-control/CurveTypeSelector';
import { validateCurvePoints } from '../components/fan-control/fanCurveValidation';

export interface UseFanCurveEditorOptions {
  isReadOnly: boolean;
  onCurveUpdate: (fanId: string, points: FanCurvePoint[]) => void;
  onConfigUpdate?: () => void;
  onEditingChange?: (isEditing: boolean) => void;
  onApplyProfile?: (profile: FanCurveProfile) => void;
  profiles?: FanCurveProfile[];
}

export function useFanCurveEditor(fan: FanInfo, opts: UseFanCurveEditorOptions) {
  const { isReadOnly, onCurveUpdate, onConfigUpdate, onEditingChange, onApplyProfile, profiles } = opts;
  const { t } = useTranslation(['system', 'common']);

  const [curvePoints, setCurvePoints] = useState<FanCurvePoint[]>(fan.curve_points);
  const [viewMode, setViewMode] = useState<'chart' | 'table'>('chart');
  const [hysteresis, setHysteresis] = useState<number>(fan.hysteresis_celsius ?? 3.0);
  const [isUpdatingHysteresis, setIsUpdatingHysteresis] = useState(false);
  const [curveType, setCurveType] = useState<CurveType>((fan.curve_type as CurveType) ?? 'graph');
  const [localGpuManualEnabled, setLocalGpuManualEnabled] = useState(false);
  const [showMoreProfiles, setShowMoreProfiles] = useState(false);

  // Tracks whether the user has manually edited the curve (prevents auto-refresh overwrites)
  const userEditedRef = useRef(false);

  // Editing is always enabled when not read-only (FanControl-style)
  const canEdit = !isReadOnly;

  // Sync curveType from server when fan changes
  useEffect(() => {
    setCurveType((fan.curve_type as CurveType) ?? 'graph');
  }, [fan.fan_id, fan.curve_type]);

  // Check if curve has been modified (compare with original)
  const hasUnsavedChanges = useMemo(() => {
    if (curvePoints.length !== fan.curve_points.length) return true;
    const sortedCurrent = [...curvePoints].sort((a, b) => a.temp - b.temp);
    const sortedOriginal = [...fan.curve_points].sort((a, b) => a.temp - b.temp);
    return sortedCurrent.some((p, i) =>
      p.temp !== sortedOriginal[i].temp || p.pwm !== sortedOriginal[i].pwm
    );
  }, [curvePoints, fan.curve_points]);

  // Sync curve points from server — but only when user hasn't manually edited
  useEffect(() => {
    if (!userEditedRef.current) {
      setCurvePoints(fan.curve_points);
    }
  }, [fan.fan_id, fan.curve_points]);

  // Reset userEditedRef when switching to a different fan
  useEffect(() => {
    userEditedRef.current = false;
    setCurvePoints(fan.curve_points);
  }, [fan.fan_id]); // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => {
    setHysteresis(fan.hysteresis_celsius ?? 3.0);
  }, [fan.fan_id, fan.hysteresis_celsius]);

  // Notify parent when there are unsaved changes (to pause auto-refresh)
  useEffect(() => {
    onEditingChange?.(hasUnsavedChanges);
  }, [hasUnsavedChanges, onEditingChange]);

  const handleCurveTypeChange = async (v: CurveType) => {
    if (isReadOnly) return;
    setCurveType(v);
    try {
      await updateFanConfig(fan.fan_id, { curve_type: v });
      onConfigUpdate?.();
    } catch (error: unknown) {
      handleApiError(error, t('system:fanControl.messages.curveFailed'));
      setCurveType((fan.curve_type as CurveType) ?? 'graph');
    }
  };

  const handleFlatChange = async (v: number) => {
    if (isReadOnly) return;
    try {
      await updateFanConfig(fan.fan_id, { flat_pwm_percent: v });
      onConfigUpdate?.();
    } catch (error: unknown) {
      handleApiError(error, t('system:fanControl.messages.curveFailed'));
    }
  };

  const handleTargetChange = async ({ targetTemp, targetPwm }: { targetTemp: number; targetPwm: number }) => {
    if (isReadOnly) return;
    try {
      await updateFanConfig(fan.fan_id, { target_temp_celsius: targetTemp, target_pwm_percent: targetPwm });
      onConfigUpdate?.();
    } catch (error: unknown) {
      handleApiError(error, t('system:fanControl.messages.curveFailed'));
    }
  };

  const handleMixChange = async ({ curveAId, curveBId, fn }: { curveAId: number | null; curveBId: number | null; fn: 'max' | 'sum' }) => {
    if (isReadOnly) return;
    try {
      await updateFanConfig(fan.fan_id, { mix_curve_a_id: curveAId, mix_curve_b_id: curveBId, mix_function: fn });
      onConfigUpdate?.();
    } catch (error: unknown) {
      handleApiError(error, t('system:fanControl.messages.curveFailed'));
    }
  };

  const handleSyncChange = async (v: string | null) => {
    if (isReadOnly) return;
    try {
      await updateFanConfig(fan.fan_id, { sync_fan_id: v });
      onConfigUpdate?.();
    } catch (error: unknown) {
      handleApiError(error, t('system:fanControl.messages.curveFailed'));
    }
  };

  const handleSaveCurve = () => {
    const validation = validateCurvePoints(
      curvePoints,
      { minPwm: fan.min_pwm_percent, maxPwm: fan.max_pwm_percent },
      t,
    );
    if (!validation.valid) {
      toast.error(validation.error || t('system:fanControl.validation.invalidCurve'));
      return;
    }

    userEditedRef.current = false;
    onCurveUpdate(fan.fan_id, curvePoints);
  };

  const handleDiscardChanges = () => {
    userEditedRef.current = false;
    setCurvePoints(fan.curve_points);
  };

  const handleAddPoint = () => {
    userEditedRef.current = true;
    const lastPoint = curvePoints[curvePoints.length - 1];
    const newTemp = lastPoint ? lastPoint.temp + 10 : 40;
    const newPWM = lastPoint ? Math.min(lastPoint.pwm + 10, 100) : 50;
    setCurvePoints([...curvePoints, { temp: newTemp, pwm: newPWM }]);
  };

  const handleRemovePoint = (index: number) => {
    if (curvePoints.length > 2) {
      userEditedRef.current = true;
      setCurvePoints(curvePoints.filter((_, i) => i !== index));
    }
  };

  const handleUpdatePoint = (index: number, field: 'temp' | 'pwm', value: number) => {
    userEditedRef.current = true;
    const updated = [...curvePoints];
    updated[index] = { ...updated[index], [field]: value };
    setCurvePoints(updated);
  };

  const handleApplyPreset = (preset: string) => {
    const presetPoints = CURVE_PRESETS[preset];
    if (presetPoints) {
      userEditedRef.current = true;
      setCurvePoints([...presetPoints]);
      toast.success(t('system:fanControl.curve.presetApplied', { preset }));
    }
  };

  const handleApplyProfileCurve = (profile: FanCurveProfile) => {
    if (onApplyProfile) {
      onApplyProfile(profile);
    } else {
      userEditedRef.current = true;
      setCurvePoints([...profile.curve_points]);
      toast.success(t('system:fanControl.curve.presetApplied', { preset: profile.name }));
    }
    setShowMoreProfiles(false);
  };

  // Wrapper for FanCurveChart's onPointsChange — marks as user-edited
  const handleChartPointsChange = useCallback((points: FanCurvePoint[]) => {
    userEditedRef.current = true;
    setCurvePoints(points);
  }, []);

  const handleHysteresisChange = async (value: number) => {
    setHysteresis(value);
  };

  const handleHysteresisSave = async () => {
    if (isReadOnly) return;

    setIsUpdatingHysteresis(true);
    try {
      await updateFanConfig(fan.fan_id, { hysteresis_celsius: hysteresis });
      toast.success(t('system:fanControl.messages.hysteresisSet', { value: hysteresis }));
      onConfigUpdate?.();
    } catch {
      toast.error(t('system:fanControl.messages.hysteresisFailed'));
      setHysteresis(fan.hysteresis_celsius ?? 3.0);
    } finally {
      setIsUpdatingHysteresis(false);
    }
  };

  const handleAdvancedChange = async (patch: Partial<FanInfo>) => {
    if (isReadOnly) return;
    try {
      await updateFanConfig(fan.fan_id, patch as Parameters<typeof updateFanConfig>[1]);
      onConfigUpdate?.();
    } catch (error: unknown) {
      handleApiError(error, t('system:fanControl.messages.curveFailed'));
    }
  };

  const systemProfiles = profiles?.filter(p => p.is_system) ?? [];
  const userProfiles = profiles?.filter(p => !p.is_system) ?? [];
  const hysteresisChanged = hysteresis !== (fan.hysteresis_celsius ?? 3.0);

  return {
    curvePoints, viewMode, setViewMode, hysteresis, isUpdatingHysteresis, curveType,
    localGpuManualEnabled, setLocalGpuManualEnabled, showMoreProfiles, setShowMoreProfiles,
    canEdit, hasUnsavedChanges, hysteresisChanged, systemProfiles, userProfiles,
    handleCurveTypeChange, handleFlatChange, handleTargetChange, handleMixChange,
    handleSyncChange, handleSaveCurve, handleDiscardChanges, handleAddPoint,
    handleRemovePoint, handleUpdatePoint, handleApplyPreset, handleApplyProfileCurve,
    handleChartPointsChange, handleHysteresisChange, handleHysteresisSave, handleAdvancedChange,
  };
}
