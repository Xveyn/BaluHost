/**
 * Fan Control Page
 *
 * Manages PWM fan control with manual and automatic modes
 */
import React, { useState, useEffect } from 'react';
import { Fan, Activity, Settings, TrendingUp, AlertTriangle } from 'lucide-react';
import toast from 'react-hot-toast';
import {
  getFanStatus,
  setFanMode,
  setFanPWM,
  updateFanCurve,
  switchBackend,
  getPermissionStatus,
  FanInfo,
  FanMode,
  FanCurvePoint,
  FanStatusResponse,
  PermissionStatusResponse,
} from '../api/fan-control';

export default function FanControl() {
  const [status, setStatus] = useState<FanStatusResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [permissionStatus, setPermissionStatus] = useState<PermissionStatusResponse | null>(null);
  const [selectedFan, setSelectedFan] = useState<string | null>(null);

  useEffect(() => {
    loadStatus();
    loadPermissions();

    // Refresh every 5 seconds
    const interval = setInterval(loadStatus, 5000);
    return () => clearInterval(interval);
  }, []);

  const loadStatus = async () => {
    try {
      const data = await getFanStatus();
      console.log('Fan status response:', data);

      if (!data || !data.fans) {
        console.error('Invalid fan status response:', data);
        toast.error('Invalid response from server');
        return;
      }

      setStatus(data);

      // Auto-select first fan if none selected
      if (!selectedFan && data.fans.length > 0) {
        setSelectedFan(data.fans[0].fan_id);
      }
    } catch (error: any) {
      console.error('Failed to load fan status:', error);
      console.error('Error details:', error.response?.data);
      toast.error(error.response?.data?.detail || 'Failed to load fan status');
    } finally {
      setLoading(false);
    }
  };

  const loadPermissions = async () => {
    try {
      const perms = await getPermissionStatus();
      setPermissionStatus(perms);
    } catch (error) {
      console.error('Failed to load permissions:', error);
    }
  };

  const handleModeChange = async (fanId: string, mode: FanMode) => {
    try {
      await setFanMode(fanId, mode);
      toast.success(`Fan mode changed to ${mode}`);
      loadStatus();
    } catch (error: any) {
      toast.error(error.response?.data?.detail || 'Failed to change fan mode');
    }
  };

  const handlePWMChange = async (fanId: string, pwm: number) => {
    try {
      await setFanPWM(fanId, pwm);
      // Don't show toast for every slider change
      loadStatus();
    } catch (error: any) {
      toast.error(error.response?.data?.detail || 'Failed to set PWM');
    }
  };

  const handleCurveUpdate = async (fanId: string, points: FanCurvePoint[]) => {
    try {
      await updateFanCurve(fanId, points);
      toast.success('Fan curve updated');
      loadStatus();
    } catch (error: any) {
      toast.error(error.response?.data?.detail || 'Failed to update curve');
    }
  };

  const handleBackendSwitch = async (useLinux: boolean) => {
    try {
      const result = await switchBackend(useLinux);
      if (result.success) {
        toast.success(result.message || 'Backend switched');
        loadStatus();
      } else {
        toast.error(result.message || 'Failed to switch backend');
      }
    } catch (error: any) {
      toast.error(error.response?.data?.detail || 'Failed to switch backend');
    }
  };

  if (loading) {
    return (
      <div className="flex items-center justify-center h-screen">
        <div className="animate-spin rounded-full h-32 w-32 border-b-2 border-blue-600"></div>
      </div>
    );
  }

  if (!status || !status.fans) {
    return (
      <div className="flex items-center justify-center h-screen">
        <div className="text-red-500">Failed to load fan control - check console for details</div>
      </div>
    );
  }

  const selectedFanData = status.fans.find(f => f.fan_id === selectedFan);

  return (
    <div className="p-6 max-w-7xl mx-auto">
      {/* Header */}
      <div className="mb-6">
        <h1 className="text-3xl font-bold text-gray-800 dark:text-white flex items-center gap-2">
          <Fan className="w-8 h-8" />
          Fan Control
        </h1>
        <p className="text-gray-600 dark:text-gray-400 mt-2">
          PWM fan management with automatic temperature curves
        </p>
      </div>

      {/* Status Badges */}
      <div className="mb-6 flex flex-wrap gap-3">
        {status.is_dev_mode && (
          <span className="px-3 py-1 bg-yellow-100 text-yellow-800 rounded-full text-sm font-medium">
            Dev Mode (Simulated)
          </span>
        )}
        {status.is_using_linux_backend ? (
          <span className="px-3 py-1 bg-green-100 text-green-800 rounded-full text-sm font-medium">
            Linux Backend (Hardware)
          </span>
        ) : (
          <span className="px-3 py-1 bg-blue-100 text-blue-800 rounded-full text-sm font-medium">
            Simulation Backend
          </span>
        )}
        {permissionStatus?.status === 'readonly' && (
          <span className="px-3 py-1 bg-orange-100 text-orange-800 rounded-full text-sm font-medium flex items-center gap-1">
            <AlertTriangle className="w-4 h-4" />
            Read-Only Mode
          </span>
        )}
      </div>

      {/* Permission Warning */}
      {permissionStatus?.status === 'readonly' && (
        <div className="mb-6 p-4 bg-orange-50 border border-orange-200 rounded-lg">
          <h3 className="font-semibold text-orange-800 mb-2">Limited Permissions</h3>
          <p className="text-sm text-orange-700 mb-3">{permissionStatus.message}</p>
          {permissionStatus.suggestions.length > 0 && (
            <div className="text-sm text-orange-700">
              <p className="font-medium mb-1">Suggestions:</p>
              <ul className="list-disc list-inside space-y-1">
                {permissionStatus.suggestions.map((s, i) => (
                  <li key={i} className="font-mono text-xs">{s}</li>
                ))}
              </ul>
            </div>
          )}
        </div>
      )}

      {/* Backend Switch (Always visible) */}
      <div className="mb-6 p-4 bg-gray-50 dark:bg-gray-800 rounded-lg">
        <h3 className="font-semibold mb-3 flex items-center gap-2">
          <Settings className="w-5 h-5" />
          Backend Configuration
        </h3>
        <p className="text-sm text-gray-600 dark:text-gray-400 mb-3">
          Switch between simulated fans and real hardware control
        </p>
        <div className="flex gap-3">
          <button
            onClick={() => handleBackendSwitch(false)}
            disabled={!status.is_using_linux_backend}
            className={`px-4 py-2 rounded-lg font-medium transition-colors ${
              !status.is_using_linux_backend
                ? 'bg-blue-500 text-white'
                : 'bg-gray-200 text-gray-700 hover:bg-gray-300'
            } disabled:opacity-50 disabled:cursor-not-allowed`}
          >
            Use Simulation
          </button>
          <button
            onClick={() => handleBackendSwitch(true)}
            disabled={status.is_using_linux_backend}
            className={`px-4 py-2 rounded-lg font-medium transition-colors ${
              status.is_using_linux_backend
                ? 'bg-green-500 text-white'
                : 'bg-gray-200 text-gray-700 hover:bg-gray-300'
            } disabled:opacity-50 disabled:cursor-not-allowed`}
          >
            Use Linux Hardware
          </button>
        </div>
      </div>

      {/* Fan Cards Grid */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4 mb-6">
        {status.fans.map((fan) => (
          <FanCard
            key={fan.fan_id}
            fan={fan}
            isSelected={fan.fan_id === selectedFan}
            onSelect={() => setSelectedFan(fan.fan_id)}
            onModeChange={handleModeChange}
            onPWMChange={handlePWMChange}
            isReadOnly={permissionStatus?.status === 'readonly'}
          />
        ))}
      </div>

      {/* Fan Details (if fan selected) */}
      {selectedFanData && (
        <div className="mt-6">
          <FanDetails
            fan={selectedFanData}
            onCurveUpdate={handleCurveUpdate}
            isReadOnly={permissionStatus?.status === 'readonly'}
          />
        </div>
      )}

      {/* No Fans Available */}
      {status.fans.length === 0 && (
        <div className="text-center py-12 bg-gray-50 dark:bg-gray-800 rounded-lg">
          <Fan className="w-16 h-16 mx-auto text-gray-400 mb-4" />
          <p className="text-gray-600 dark:text-gray-400">No PWM fans detected</p>
          <p className="text-sm text-gray-500 mt-2">
            Ensure lm-sensors is installed and PWM fans are connected
          </p>
        </div>
      )}
    </div>
  );
}

// Fan Card Component
interface FanCardProps {
  fan: FanInfo;
  isSelected: boolean;
  onSelect: () => void;
  onModeChange: (fanId: string, mode: FanMode) => void;
  onPWMChange: (fanId: string, pwm: number) => void;
  isReadOnly: boolean;
}

function FanCard({ fan, isSelected, onSelect, onModeChange, onPWMChange, isReadOnly }: FanCardProps) {
  const [localPWM, setLocalPWM] = useState(fan.pwm_percent);

  useEffect(() => {
    setLocalPWM(fan.pwm_percent);
  }, [fan.pwm_percent]);

  const handlePWMSliderChange = (value: number) => {
    setLocalPWM(value);
  };

  const handlePWMSliderRelease = () => {
    if (fan.mode === FanMode.MANUAL) {
      onPWMChange(fan.fan_id, localPWM);
    }
  };

  const getModeColor = (mode: FanMode): string => {
    switch (mode) {
      case FanMode.AUTO:
        return 'bg-blue-100 text-blue-800';
      case FanMode.MANUAL:
        return 'bg-purple-100 text-purple-800';
      case FanMode.EMERGENCY:
        return 'bg-red-100 text-red-800';
      default:
        return 'bg-gray-100 text-gray-800';
    }
  };

  return (
    <div
      onClick={onSelect}
      className={`p-4 rounded-lg border-2 transition-all cursor-pointer ${
        isSelected
          ? 'border-blue-500 bg-blue-50 dark:bg-blue-900/20'
          : 'border-gray-200 dark:border-gray-700 hover:border-gray-300'
      }`}
    >
      {/* Fan Name & Mode */}
      <div className="flex items-start justify-between mb-3">
        <div>
          <h3 className="font-semibold text-gray-800 dark:text-white">{fan.name}</h3>
          <p className="text-xs text-gray-500 dark:text-gray-400 mt-1">{fan.fan_id}</p>
        </div>
        <span className={`px-2 py-1 rounded text-xs font-medium ${getModeColor(fan.mode)}`}>
          {fan.mode.toUpperCase()}
        </span>
      </div>

      {/* RPM & PWM */}
      <div className="grid grid-cols-2 gap-3 mb-3">
        <div>
          <p className="text-xs text-gray-500 dark:text-gray-400">RPM</p>
          <p className="text-lg font-bold text-gray-800 dark:text-white">
            {fan.rpm !== null ? fan.rpm.toLocaleString() : '—'}
          </p>
        </div>
        <div>
          <p className="text-xs text-gray-500 dark:text-gray-400">PWM</p>
          <p className="text-lg font-bold text-gray-800 dark:text-white">
            {fan.pwm_percent}%
          </p>
        </div>
      </div>

      {/* Temperature */}
      {fan.temperature_celsius !== null && (
        <div className="mb-3">
          <p className="text-xs text-gray-500 dark:text-gray-400">Temperature</p>
          <p className="text-lg font-bold text-gray-800 dark:text-white">
            {fan.temperature_celsius.toFixed(1)}°C
          </p>
        </div>
      )}

      {/* Mode Toggle */}
      <div className="flex gap-2 mb-3">
        <button
          onClick={(e) => {
            e.stopPropagation();
            onModeChange(fan.fan_id, FanMode.AUTO);
          }}
          disabled={fan.mode === FanMode.AUTO || isReadOnly}
          className={`flex-1 px-3 py-1 text-xs rounded transition-colors ${
            fan.mode === FanMode.AUTO
              ? 'bg-blue-500 text-white'
              : 'bg-gray-200 text-gray-700 hover:bg-gray-300'
          } disabled:opacity-50 disabled:cursor-not-allowed`}
        >
          Auto
        </button>
        <button
          onClick={(e) => {
            e.stopPropagation();
            onModeChange(fan.fan_id, FanMode.MANUAL);
          }}
          disabled={fan.mode === FanMode.MANUAL || isReadOnly}
          className={`flex-1 px-3 py-1 text-xs rounded transition-colors ${
            fan.mode === FanMode.MANUAL
              ? 'bg-purple-500 text-white'
              : 'bg-gray-200 text-gray-700 hover:bg-gray-300'
          } disabled:opacity-50 disabled:cursor-not-allowed`}
        >
          Manual
        </button>
      </div>

      {/* Manual PWM Slider */}
      {fan.mode === FanMode.MANUAL && (
        <div onClick={(e) => e.stopPropagation()}>
          <label className="text-xs text-gray-600 dark:text-gray-400 block mb-1">
            Manual PWM: {localPWM}%
          </label>
          <input
            type="range"
            min={fan.min_pwm_percent}
            max={fan.max_pwm_percent}
            value={localPWM}
            onChange={(e) => handlePWMSliderChange(parseInt(e.target.value))}
            onMouseUp={handlePWMSliderRelease}
            onTouchEnd={handlePWMSliderRelease}
            disabled={isReadOnly}
            className="w-full h-2 bg-gray-200 rounded-lg appearance-none cursor-pointer disabled:opacity-50 disabled:cursor-not-allowed"
          />
        </div>
      )}
    </div>
  );
}

// Fan Details Component
interface FanDetailsProps {
  fan: FanInfo;
  onCurveUpdate: (fanId: string, points: FanCurvePoint[]) => void;
  isReadOnly: boolean;
}

function FanDetails({ fan, onCurveUpdate, isReadOnly }: FanDetailsProps) {
  const [curvePoints, setCurvePoints] = useState<FanCurvePoint[]>(fan.curve_points);
  const [editingCurve, setEditingCurve] = useState(false);

  useEffect(() => {
    setCurvePoints(fan.curve_points);
  }, [fan.curve_points]);

  const handleSaveCurve = () => {
    onCurveUpdate(fan.fan_id, curvePoints);
    setEditingCurve(false);
  };

  const handleAddPoint = () => {
    const lastPoint = curvePoints[curvePoints.length - 1];
    const newTemp = lastPoint ? lastPoint.temp + 10 : 40;
    const newPWM = lastPoint ? Math.min(lastPoint.pwm + 10, 100) : 50;
    setCurvePoints([...curvePoints, { temp: newTemp, pwm: newPWM }]);
  };

  const handleRemovePoint = (index: number) => {
    if (curvePoints.length > 2) {
      setCurvePoints(curvePoints.filter((_, i) => i !== index));
    }
  };

  const handleUpdatePoint = (index: number, field: 'temp' | 'pwm', value: number) => {
    const updated = [...curvePoints];
    updated[index] = { ...updated[index], [field]: value };
    setCurvePoints(updated);
  };

  return (
    <div className="bg-white dark:bg-gray-800 rounded-lg shadow-lg p-6">
      <h2 className="text-xl font-bold mb-4 flex items-center gap-2">
        <TrendingUp className="w-6 h-6" />
        {fan.name} - Temperature Curve
      </h2>

      {/* Curve Editor */}
      <div className="mb-4">
        <div className="flex justify-between items-center mb-3">
          <p className="text-sm text-gray-600 dark:text-gray-400">
            Configure temperature-based PWM curve (active in Auto mode)
          </p>
          {!editingCurve ? (
            <button
              onClick={() => setEditingCurve(true)}
              disabled={isReadOnly}
              className="px-4 py-2 bg-blue-500 text-white rounded hover:bg-blue-600 disabled:opacity-50 disabled:cursor-not-allowed"
            >
              Edit Curve
            </button>
          ) : (
            <div className="flex gap-2">
              <button
                onClick={() => {
                  setCurvePoints(fan.curve_points);
                  setEditingCurve(false);
                }}
                className="px-4 py-2 bg-gray-300 text-gray-700 rounded hover:bg-gray-400"
              >
                Cancel
              </button>
              <button
                onClick={handleSaveCurve}
                className="px-4 py-2 bg-green-500 text-white rounded hover:bg-green-600"
              >
                Save
              </button>
            </div>
          )}
        </div>

        {/* Curve Points Table */}
        <div className="overflow-x-auto">
          <table className="w-full border border-gray-200 dark:border-gray-700">
            <thead className="bg-gray-50 dark:bg-gray-700">
              <tr>
                <th className="px-4 py-2 text-left text-sm font-medium">Temperature (°C)</th>
                <th className="px-4 py-2 text-left text-sm font-medium">PWM (%)</th>
                {editingCurve && <th className="px-4 py-2 text-left text-sm font-medium">Actions</th>}
              </tr>
            </thead>
            <tbody>
              {curvePoints
                .sort((a, b) => a.temp - b.temp)
                .map((point, index) => (
                  <tr key={index} className="border-t border-gray-200 dark:border-gray-700">
                    <td className="px-4 py-2">
                      {editingCurve ? (
                        <input
                          type="number"
                          value={point.temp}
                          onChange={(e) => handleUpdatePoint(index, 'temp', parseFloat(e.target.value))}
                          className="w-20 px-2 py-1 border rounded"
                          min={0}
                          max={150}
                        />
                      ) : (
                        <span>{point.temp}°C</span>
                      )}
                    </td>
                    <td className="px-4 py-2">
                      {editingCurve ? (
                        <input
                          type="number"
                          value={point.pwm}
                          onChange={(e) => handleUpdatePoint(index, 'pwm', parseInt(e.target.value))}
                          className="w-20 px-2 py-1 border rounded"
                          min={fan.min_pwm_percent}
                          max={fan.max_pwm_percent}
                        />
                      ) : (
                        <span>{point.pwm}%</span>
                      )}
                    </td>
                    {editingCurve && (
                      <td className="px-4 py-2">
                        <button
                          onClick={() => handleRemovePoint(index)}
                          disabled={curvePoints.length <= 2}
                          className="text-red-500 hover:text-red-700 disabled:opacity-50 disabled:cursor-not-allowed text-sm"
                        >
                          Remove
                        </button>
                      </td>
                    )}
                  </tr>
                ))}
            </tbody>
          </table>
        </div>

        {editingCurve && curvePoints.length < 10 && (
          <button
            onClick={handleAddPoint}
            className="mt-3 px-4 py-2 bg-blue-500 text-white rounded hover:bg-blue-600 text-sm"
          >
            Add Point
          </button>
        )}
      </div>

      {/* Fan Stats */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4 pt-4 border-t border-gray-200 dark:border-gray-700">
        <div>
          <p className="text-xs text-gray-500 dark:text-gray-400">Min PWM</p>
          <p className="text-lg font-bold">{fan.min_pwm_percent}%</p>
        </div>
        <div>
          <p className="text-xs text-gray-500 dark:text-gray-400">Max PWM</p>
          <p className="text-lg font-bold">{fan.max_pwm_percent}%</p>
        </div>
        <div>
          <p className="text-xs text-gray-500 dark:text-gray-400">Emergency Temp</p>
          <p className="text-lg font-bold">{fan.emergency_temp_celsius}°C</p>
        </div>
        <div>
          <p className="text-xs text-gray-500 dark:text-gray-400">Sensor ID</p>
          <p className="text-sm font-mono">{fan.temp_sensor_id || '—'}</p>
        </div>
      </div>
    </div>
  );
}
