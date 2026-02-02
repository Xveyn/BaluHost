import React, { useState, useRef, useCallback, useEffect } from 'react';
import { useTranslation } from 'react-i18next';
import {
  ComposedChart,
  Line,
  Scatter,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
  ReferenceLine,
} from 'recharts';
import type { FanCurvePoint } from '../../api/fan-control';

interface FanCurveChartProps {
  points: FanCurvePoint[];
  onPointsChange: (points: FanCurvePoint[]) => void;
  currentTemp: number | null;
  currentPWM: number;
  minPWM: number;
  maxPWM: number;
  emergencyTemp: number;
  isEditing?: boolean; // Kept for API compatibility, not used (FanControl-style always editable)
  isReadOnly: boolean;
  minPoints?: number; // Minimum number of points allowed (default: 2)
  maxPoints?: number; // Maximum number of points allowed (default: 10)
}

interface ChartDataPoint extends FanCurvePoint {
  isCurrentPoint?: boolean;
  originalIndex?: number;
}

export default function FanCurveChart({
  points,
  onPointsChange,
  currentTemp,
  currentPWM,
  minPWM,
  maxPWM,
  emergencyTemp,
  // isEditing - Kept in interface for API compatibility, but not used (FanControl-style always editable)
  isReadOnly,
  minPoints = 2,
  maxPoints = 10,
}: FanCurveChartProps) {
  const { t } = useTranslation(['system', 'common']);
  const [draggingIndex, setDraggingIndex] = useState<number | null>(null);
  const [localPoints, setLocalPoints] = useState<FanCurvePoint[]>(points);
  const chartRef = useRef<HTMLDivElement>(null);
  const localPointsRef = useRef<FanCurvePoint[]>(localPoints);

  // Editing is always enabled when not read-only (FanControl-style behavior)
  const canEdit = !isReadOnly;

  // Update local points when external points change (but not while dragging)
  useEffect(() => {
    if (draggingIndex === null) {
      setLocalPoints(points);
    }
  }, [points, draggingIndex]);

  // Keep ref in sync with state
  useEffect(() => {
    localPointsRef.current = localPoints;
  }, [localPoints]);

  // Add original indices to points before sorting
  const pointsWithIndices = localPoints.map((point, index) => ({
    ...point,
    originalIndex: index,
  }));

  // Sort points for display
  const sortedPoints = [...pointsWithIndices].sort((a, b) => a.temp - b.temp);

  // Prepare chart data - ONLY curve points, NOT the current operating point
  // The current operating point should be rendered separately, not as part of the line
  const chartData: ChartDataPoint[] = sortedPoints.map(point => ({
    ...point,
    isCurrentPoint: false,
  }));

  // Handle right-click to remove a point
  const handleRemovePoint = useCallback((index: number) => {
    if (!canEdit || localPoints.length <= minPoints) return;

    // Get the original index from sorted points
    const originalIndex = sortedPoints[index]?.originalIndex;
    if (originalIndex === undefined) return;

    const updatedPoints = localPoints.filter((_, i) => i !== originalIndex);
    setLocalPoints(updatedPoints);
    onPointsChange(updatedPoints);
  }, [canEdit, localPoints, minPoints, onPointsChange, sortedPoints]);

  // Custom dot component - events are handled by the overlay
  const CustomDot = (props: any) => {
    const { cx, cy, payload, index } = props;

    // Guard clauses - früh returnen wenn Props fehlen
    if (cx === undefined || cy === undefined) return null;
    if (!payload) return null;
    if (payload.isCurrentPoint) return null;

    const isHovered = draggingIndex === index;
    const radius = isHovered ? 10 : 7;
    const fill = isHovered ? '#38bdf8' : '#0ea5e9'; // sky-400 / sky-500

    return (
      <circle
        cx={cx}
        cy={cy}
        r={radius}
        fill={fill}
        stroke="#1e293b"
        strokeWidth={2}
        style={{
          cursor: canEdit ? 'grab' : 'default',
          transition: 'r 0.15s ease',
          pointerEvents: 'none', // Events handled by overlay
        }}
      />
    );
  };

  const updatePointPosition = useCallback((clientX: number, clientY: number, index: number) => {
    if (!chartRef.current) return;

    // Find the actual plot area (cartesian grid)
    const cartesianGrid = chartRef.current.querySelector('.recharts-cartesian-grid');
    if (!cartesianGrid) return;

    const rect = cartesianGrid.getBoundingClientRect();

    // Calculate relative position within the plot area
    const x = clientX - rect.left;
    const y = clientY - rect.top;

    // The plot area rect gives us the exact dimensions
    const chartWidth = rect.width;
    const chartHeight = rect.height;

    // Calculate temperature and PWM from position
    const tempRange = emergencyTemp + 10 - 0; // 0 to emergencyTemp + 10
    const pwmRange = 100 - 0; // 0 to 100

    const newTemp = Math.round((x / chartWidth) * tempRange);
    const newPWM = Math.round(100 - (y / chartHeight) * pwmRange);

    // Clamp values
    const clampedTemp = Math.max(0, Math.min(emergencyTemp + 10, newTemp));
    const clampedPWM = Math.max(minPWM, Math.min(maxPWM, newPWM));

    // Get the original index from the sorted point
    const originalIndex = sortedPoints[index].originalIndex;
    if (originalIndex === undefined) return;

    // Update the point in the ORIGINAL array order
    const updatedPoints = [...localPoints];
    updatedPoints[originalIndex] = {
      temp: clampedTemp,
      pwm: clampedPWM,
    };

    // Update local state for smooth dragging
    setLocalPoints(updatedPoints);
  }, [sortedPoints, localPoints, minPWM, maxPWM, emergencyTemp]);

  // Custom tooltip
  const CustomTooltip = ({ active, payload }: any) => {
    if (!active || !payload || payload.length === 0) return null;

    const data = payload[0].payload as ChartDataPoint;

    return (
      <div className="bg-slate-900 border border-slate-700 rounded-lg px-3 py-2 shadow-xl">
        <p className="text-xs text-slate-400">
          {data.isCurrentPoint ? t('system:fanControl.curve.current') : t('system:fanControl.curve.curvePoint')}
        </p>
        <p className="text-sm font-semibold text-white">
          {data.temp.toFixed(1)}°C → {data.pwm}%
        </p>
      </div>
    );
  };

  // Data for the current operating point (separate from curve)
  // Use different key name to avoid Recharts interpreting it as part of the Line
  const currentPointData = currentTemp !== null ? [{ temp: currentTemp, currentPwm: currentPWM }] : [];

  // Ref for the overlay to capture events
  const overlayRef = useRef<HTMLDivElement>(null);

  // Get chart area bounds for coordinate calculations
  const getChartBounds = useCallback(() => {
    if (!chartRef.current) return null;
    const cartesianGrid = chartRef.current.querySelector('.recharts-cartesian-grid');
    if (!cartesianGrid) return null;
    return cartesianGrid.getBoundingClientRect();
  }, []);

  // Convert pixel coordinates to chart values
  const pixelToValue = useCallback((clientX: number, clientY: number) => {
    const bounds = getChartBounds();
    if (!bounds) return null;

    const x = clientX - bounds.left;
    const y = clientY - bounds.top;
    const tempRange = emergencyTemp + 10;

    const temp = Math.round((x / bounds.width) * tempRange);
    const pwm = Math.round(100 - (y / bounds.height) * 100);

    return {
      temp: Math.max(0, Math.min(emergencyTemp + 10, temp)),
      pwm: Math.max(minPWM, Math.min(maxPWM, pwm)),
      inBounds: x >= -5 && x <= bounds.width + 5 && y >= -5 && y <= bounds.height + 5,
    };
  }, [emergencyTemp, minPWM, maxPWM, getChartBounds]);

  // Find point near coordinates (for drag/delete)
  const findPointNear = useCallback((clientX: number, clientY: number): number | null => {
    const bounds = getChartBounds();
    if (!bounds) return null;

    const x = clientX - bounds.left;
    const y = clientY - bounds.top;
    const tempRange = emergencyTemp + 10;
    const hitRadius = 15;

    let nearestIndex: number | null = null;
    let nearestDist = Infinity;

    sortedPoints.forEach((point, index) => {
      const pointX = (point.temp / tempRange) * bounds.width;
      const pointY = ((100 - point.pwm) / 100) * bounds.height;
      const dist = Math.sqrt(Math.pow(x - pointX, 2) + Math.pow(y - pointY, 2));

      if (dist < hitRadius && dist < nearestDist) {
        nearestDist = dist;
        nearestIndex = index;
      }
    });

    return nearestIndex;
  }, [sortedPoints, emergencyTemp, getChartBounds]);

  // Overlay mouse down handler
  const handleOverlayMouseDown = useCallback((e: React.MouseEvent) => {
    if (!canEdit) return;

    const pointIndex = findPointNear(e.clientX, e.clientY);
    if (pointIndex !== null) {
      // Start dragging
      e.preventDefault();
      setDraggingIndex(pointIndex);

      const handleMouseMove = (moveEvent: MouseEvent) => {
        updatePointPosition(moveEvent.clientX, moveEvent.clientY, pointIndex);
      };

      const handleMouseUp = () => {
        setDraggingIndex(null);
        onPointsChange(localPointsRef.current);
        document.removeEventListener('mousemove', handleMouseMove);
        document.removeEventListener('mouseup', handleMouseUp);
      };

      document.addEventListener('mousemove', handleMouseMove);
      document.addEventListener('mouseup', handleMouseUp);
    }
  }, [canEdit, findPointNear, updatePointPosition, onPointsChange]);

  // Overlay click handler (for adding points)
  const handleOverlayClick = useCallback((e: React.MouseEvent) => {
    if (!canEdit || localPoints.length >= maxPoints) return;

    // Don't add if we clicked on a point
    const pointIndex = findPointNear(e.clientX, e.clientY);
    if (pointIndex !== null) return;

    const values = pixelToValue(e.clientX, e.clientY);
    if (!values || !values.inBounds) return;

    const newPoint: FanCurvePoint = { temp: values.temp, pwm: values.pwm };
    const updatedPoints = [...localPoints, newPoint];
    setLocalPoints(updatedPoints);
    onPointsChange(updatedPoints);
  }, [canEdit, localPoints, maxPoints, findPointNear, pixelToValue, onPointsChange]);

  // Overlay context menu handler (for removing points)
  const handleOverlayContextMenu = useCallback((e: React.MouseEvent) => {
    e.preventDefault();
    if (!canEdit) return;

    const pointIndex = findPointNear(e.clientX, e.clientY);
    if (pointIndex !== null) {
      handleRemovePoint(pointIndex);
    }
  }, [canEdit, findPointNear, handleRemovePoint]);

  // Overlay touch handler
  const handleOverlayTouchStart = useCallback((e: React.TouchEvent) => {
    if (!canEdit) return;

    const touch = e.touches[0];
    const pointIndex = findPointNear(touch.clientX, touch.clientY);

    if (pointIndex !== null) {
      e.preventDefault();
      setDraggingIndex(pointIndex);

      const handleTouchMove = (moveEvent: TouchEvent) => {
        const moveTouch = moveEvent.touches[0];
        updatePointPosition(moveTouch.clientX, moveTouch.clientY, pointIndex);
      };

      const handleTouchEnd = () => {
        setDraggingIndex(null);
        onPointsChange(localPointsRef.current);
        document.removeEventListener('touchmove', handleTouchMove);
        document.removeEventListener('touchend', handleTouchEnd);
      };

      document.addEventListener('touchmove', handleTouchMove);
      document.addEventListener('touchend', handleTouchEnd);
    }
  }, [canEdit, findPointNear, updatePointPosition, onPointsChange]);

  return (
    <div
      ref={chartRef}
      className="w-full relative"
      style={{ cursor: canEdit ? 'crosshair' : 'default' }}
    >
      <ResponsiveContainer width="100%" height={400}>
        <ComposedChart
          data={chartData}
          margin={{ top: 5, right: 20, left: 0, bottom: 55 }}
        >
          {/* Grid */}
          <CartesianGrid
            strokeDasharray="3 3"
            stroke="#334155"
            opacity={0.3}
          />

          {/* X Axis - Temperature */}
          <XAxis
            dataKey="temp"
            type="number"
            domain={[0, emergencyTemp + 10]}
            label={{
              value: 'Temperature (°C)',
              position: 'bottom',
              offset: 35,
              style: { fill: '#94a3b8', fontSize: 12 }
            }}
            tick={{ fill: '#94a3b8', fontSize: 11 }}
            stroke="#475569"
            allowDuplicatedCategory={false}
          />

          {/* Y Axis - PWM */}
          <YAxis
            dataKey="pwm"
            type="number"
            domain={[0, 100]}
            label={{
              value: 'PWM (%)',
              angle: -90,
              position: 'insideLeft',
              style: { fill: '#94a3b8', fontSize: 12 }
            }}
            tick={{ fill: '#94a3b8', fontSize: 11 }}
            stroke="#475569"
          />

          <Tooltip content={<CustomTooltip />} />

          {/* Emergency temperature line */}
          <ReferenceLine
            x={emergencyTemp}
            stroke="#f43f5e"
            strokeDasharray="5 5"
            strokeWidth={2}
            label={{
              value: 'Emergency',
              position: 'top',
              fill: '#f43f5e',
              fontSize: 11
            }}
          />

          {/* Current temperature line */}
          {currentTemp !== null && (
            <ReferenceLine
              x={currentTemp}
              stroke="#34d399"
              strokeDasharray="3 3"
              strokeWidth={1.5}
              label={{
                value: `Now: ${currentTemp.toFixed(1)}°C`,
                position: 'top',
                fill: '#34d399',
                fontSize: 11
              }}
            />
          )}

          {/* Fan curve line */}
          <Line
            type="linear"
            dataKey="pwm"
            stroke="#0ea5e9"
            strokeWidth={3}
            dot={<CustomDot />}
            activeDot={false}
            isAnimationActive={false}
          />

          {/* Current operating point - rendered as separate scatter */}
          {currentTemp !== null && (
            <Scatter
              data={currentPointData}
              dataKey="currentPwm"
              fill="#34d399"
              shape={(props: any) => (
                <circle
                  cx={props.cx}
                  cy={props.cy}
                  r={7}
                  fill="#34d399"
                  stroke="#1e293b"
                  strokeWidth={2}
                />
              )}
              isAnimationActive={false}
            />
          )}
        </ComposedChart>
      </ResponsiveContainer>

      {/* Transparent overlay for event handling - positioned over the chart area */}
      {canEdit && (
        <div
          ref={overlayRef}
          className="absolute inset-0"
          style={{ cursor: draggingIndex !== null ? 'grabbing' : 'crosshair' }}
          onMouseDown={handleOverlayMouseDown}
          onClick={handleOverlayClick}
          onContextMenu={handleOverlayContextMenu}
          onTouchStart={handleOverlayTouchStart}
        />
      )}

      {/* Legend */}
      <div className="mt-4 flex flex-wrap gap-4 text-xs text-slate-400">
        <div className="flex items-center gap-2">
          <div className="w-3 h-3 rounded-full bg-sky-500 border-2 border-slate-900" />
          <span>Curve Points</span>
        </div>
        {currentTemp !== null && (
          <div className="flex items-center gap-2">
            <div className="w-3 h-3 rounded-full bg-emerald-400 border-2 border-slate-900" />
            <span>Current Operating Point</span>
          </div>
        )}
        <div className="flex items-center gap-2">
          <div className="w-8 h-0.5 bg-rose-500" style={{ borderTop: '2px dashed' }} />
          <span>Emergency Temp ({emergencyTemp}°C)</span>
        </div>
      </div>

      {canEdit && (
        <p className="mt-3 text-xs text-slate-400 italic">
          <strong>Left-click</strong> on graph to add point • <strong>Drag</strong> points to move • <strong>Right-click</strong> point to remove
          {localPoints.length <= minPoints && ' (min 2 points)'}
          {localPoints.length >= maxPoints && ` (max ${maxPoints} points)`}
        </p>
      )}
    </div>
  );
}
