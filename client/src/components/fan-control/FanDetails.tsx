import React, { useState, useEffect } from 'react';
import { TrendingUp, Table, LineChart as LineChartIcon } from 'lucide-react';
import toast from 'react-hot-toast';
import { FanInfo, FanCurvePoint } from '../../api/fan-control';
import FanCurveChart from './FanCurveChart';

interface FanDetailsProps {
  fan: FanInfo;
  onCurveUpdate: (fanId: string, points: FanCurvePoint[]) => void;
  isReadOnly: boolean;
  onEditingChange?: (isEditing: boolean) => void;
}

export default function FanDetails({ fan, onCurveUpdate, isReadOnly, onEditingChange }: FanDetailsProps) {
  const [curvePoints, setCurvePoints] = useState<FanCurvePoint[]>(fan.curve_points);
  const [editingCurve, setEditingCurve] = useState(false);
  const [viewMode, setViewMode] = useState<'chart' | 'table'>('chart');

  useEffect(() => {
    setCurvePoints(fan.curve_points);
    setEditingCurve(false); // Reset editing state on fan change
  }, [fan.fan_id, fan.curve_points]);

  // Notify parent when editing state changes
  useEffect(() => {
    onEditingChange?.(editingCurve);
  }, [editingCurve, onEditingChange]);

  const validateCurvePoints = (points: FanCurvePoint[]): { valid: boolean; error?: string } => {
    if (points.length < 2) {
      return { valid: false, error: 'Curve must have at least 2 points' };
    }

    // Check ascending temperatures
    const sorted = [...points].sort((a, b) => a.temp - b.temp);
    for (let i = 0; i < sorted.length - 1; i++) {
      if (sorted[i].temp >= sorted[i + 1].temp) {
        return { valid: false, error: 'Temperature values must be strictly ascending' };
      }
    }

    // Check PWM range
    for (const point of points) {
      if (point.pwm < fan.min_pwm_percent || point.pwm > fan.max_pwm_percent) {
        return {
          valid: false,
          error: `PWM must be between ${fan.min_pwm_percent}% and ${fan.max_pwm_percent}%`
        };
      }
    }

    return { valid: true };
  };

  const handleSaveCurve = () => {
    const validation = validateCurvePoints(curvePoints);
    if (!validation.valid) {
      toast.error(validation.error);
      return;
    }

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
    <div className="card">
      <h2 className="text-xl font-bold text-white mb-4 flex items-center gap-2">
        <TrendingUp className="w-6 h-6 text-sky-400" />
        {fan.name} - Temperature Curve
      </h2>

      {/* Curve Editor */}
      <div className="mb-4">
        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 mb-4">
          <p className="text-sm text-slate-400">
            Configure temperature-based PWM curve (active in Auto mode)
          </p>
          <div className="flex gap-2 items-center">
            {/* View Mode Toggle */}
            <div className="flex gap-1 bg-slate-800 rounded-lg p-1">
              <button
                onClick={() => setViewMode('chart')}
                className={`px-3 py-1 text-xs rounded-md transition-colors flex items-center gap-1 ${
                  viewMode === 'chart'
                    ? 'bg-sky-500 text-white shadow-lg shadow-sky-500/30'
                    : 'text-slate-400 hover:text-slate-300'
                }`}
              >
                <LineChartIcon className="w-3 h-3" />
                Chart
              </button>
              <button
                onClick={() => setViewMode('table')}
                className={`px-3 py-1 text-xs rounded-md transition-colors flex items-center gap-1 ${
                  viewMode === 'table'
                    ? 'bg-sky-500 text-white shadow-lg shadow-sky-500/30'
                    : 'text-slate-400 hover:text-slate-300'
                }`}
              >
                <Table className="w-3 h-3" />
                Table
              </button>
            </div>

            {/* Edit/Save Buttons */}
            {!editingCurve ? (
              <button
                onClick={() => setEditingCurve(true)}
                disabled={isReadOnly}
                className="px-4 py-2 bg-sky-500 text-white rounded-lg hover:bg-sky-600 shadow-lg shadow-sky-500/30 disabled:opacity-50 disabled:cursor-not-allowed text-sm"
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
                  className="px-4 py-2 bg-slate-700 text-slate-300 rounded-lg hover:bg-slate-600 text-sm"
                >
                  Cancel
                </button>
                <button
                  onClick={handleSaveCurve}
                  className="px-4 py-2 bg-emerald-500 text-white rounded-lg hover:bg-emerald-600 shadow-lg shadow-emerald-500/30 text-sm"
                >
                  Save
                </button>
              </div>
            )}
          </div>
        </div>

        {/* Chart View */}
        {viewMode === 'chart' && (
          <div className="mt-4">
            <FanCurveChart
              points={curvePoints}
              onPointsChange={setCurvePoints}
              currentTemp={fan.temperature_celsius}
              currentPWM={fan.pwm_percent}
              minPWM={fan.min_pwm_percent}
              maxPWM={fan.max_pwm_percent}
              emergencyTemp={fan.emergency_temp_celsius}
              isEditing={editingCurve}
              isReadOnly={isReadOnly}
            />
          </div>
        )}

        {/* Table View */}
        {viewMode === 'table' && (
          <>
            <div className="overflow-x-auto">
              <table className="w-full border border-slate-700">
                <thead className="bg-slate-800">
                  <tr>
                    <th className="px-4 py-2 text-left text-sm font-medium text-slate-300">Temperature (°C)</th>
                    <th className="px-4 py-2 text-left text-sm font-medium text-slate-300">PWM (%)</th>
                    {editingCurve && <th className="px-4 py-2 text-left text-sm font-medium text-slate-300">Actions</th>}
                  </tr>
                </thead>
                <tbody>
                  {curvePoints
                    .sort((a, b) => a.temp - b.temp)
                    .map((point, index) => (
                      <tr key={index} className="border-t border-slate-700">
                        <td className="px-4 py-2">
                          {editingCurve ? (
                            <input
                              type="number"
                              value={point.temp}
                              onChange={(e) => handleUpdatePoint(index, 'temp', parseFloat(e.target.value))}
                              className="w-20 px-2 py-1 border border-slate-600 rounded bg-slate-800 text-white"
                              min={0}
                              max={150}
                            />
                          ) : (
                            <span className="text-slate-300">{point.temp}°C</span>
                          )}
                        </td>
                        <td className="px-4 py-2">
                          {editingCurve ? (
                            <input
                              type="number"
                              value={point.pwm}
                              onChange={(e) => handleUpdatePoint(index, 'pwm', parseInt(e.target.value))}
                              className="w-20 px-2 py-1 border border-slate-600 rounded bg-slate-800 text-white"
                              min={fan.min_pwm_percent}
                              max={fan.max_pwm_percent}
                            />
                          ) : (
                            <span className="text-slate-300">{point.pwm}%</span>
                          )}
                        </td>
                        {editingCurve && (
                          <td className="px-4 py-2">
                            <button
                              onClick={() => handleRemovePoint(index)}
                              disabled={curvePoints.length <= 2}
                              className="text-rose-400 hover:text-rose-300 disabled:opacity-50 disabled:cursor-not-allowed text-sm"
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
                className="mt-3 px-4 py-2 bg-sky-500 text-white rounded-lg hover:bg-sky-600 shadow-lg shadow-sky-500/30 text-sm"
              >
                Add Point
              </button>
            )}
          </>
        )}
      </div>

      {/* Fan Stats */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4 pt-4 border-t border-slate-700">
        <div>
          <p className="text-xs text-slate-400">Min PWM</p>
          <p className="text-lg font-bold text-white">{fan.min_pwm_percent}%</p>
        </div>
        <div>
          <p className="text-xs text-slate-400">Max PWM</p>
          <p className="text-lg font-bold text-white">{fan.max_pwm_percent}%</p>
        </div>
        <div>
          <p className="text-xs text-slate-400">Emergency Temp</p>
          <p className="text-lg font-bold text-white">{fan.emergency_temp_celsius}°C</p>
        </div>
        <div>
          <p className="text-xs text-slate-400">Sensor ID</p>
          <p className="text-sm font-mono text-slate-300">{fan.temp_sensor_id || '—'}</p>
        </div>
      </div>
    </div>
  );
}
