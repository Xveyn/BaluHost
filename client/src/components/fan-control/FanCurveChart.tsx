import React, { useState, useRef, useCallback, useEffect } from 'react';
import {
  LineChart,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
  ReferenceLine,
  Dot,
} from 'recharts';
import { FanCurvePoint } from '../../api/fan-control';

interface FanCurveChartProps {
  points: FanCurvePoint[];
  onPointsChange: (points: FanCurvePoint[]) => void;
  currentTemp: number | null;
  currentPWM: number;
  minPWM: number;
  maxPWM: number;
  emergencyTemp: number;
  isEditing: boolean;
  isReadOnly: boolean;
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
  isEditing,
  isReadOnly,
}: FanCurveChartProps) {
  const [draggingIndex, setDraggingIndex] = useState<number | null>(null);
  const [localPoints, setLocalPoints] = useState<FanCurvePoint[]>(points);
  const chartRef = useRef<HTMLDivElement>(null);
  const localPointsRef = useRef<FanCurvePoint[]>(localPoints);

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

  // Prepare chart data with additional info
  const chartData: ChartDataPoint[] = sortedPoints.map(point => ({
    ...point,
    isCurrentPoint: false,
  }));

  // Add current operating point if available
  if (currentTemp !== null) {
    chartData.push({
      temp: currentTemp,
      pwm: currentPWM,
      isCurrentPoint: true,
    });
  }

  // Custom dot component for draggable points
  const CustomDot = (props: any) => {
    const { cx, cy, payload, index } = props;

    // Don't render dots for current operating point
    if (payload.isCurrentPoint) return null;

    const isHovered = draggingIndex === index;
    const radius = isHovered ? 8 : 6;
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
          cursor: isEditing && !isReadOnly ? 'grab' : 'default',
          transition: 'all 0.2s ease',
        }}
        onMouseDown={(e) => handleMouseDown(e, index)}
        onTouchStart={(e) => handleTouchStart(e, index)}
      />
    );
  };

  const updatePointPosition = useCallback((clientX: number, clientY: number, index: number) => {
    if (!chartRef.current) return;

    const chartElement = chartRef.current.querySelector('.recharts-wrapper');
    if (!chartElement) return;

    const rect = chartElement.getBoundingClientRect();

    // Calculate relative position
    const x = clientX - rect.left;
    const y = clientY - rect.top;

    // Get chart dimensions (accounting for margins)
    const chartWidth = rect.width - 70; // Left margin ~50px, right margin ~20px
    const chartHeight = rect.height - 60; // Top margin ~5px, bottom margin ~55px
    const offsetX = 50;
    const offsetY = 5;

    // Calculate temperature and PWM from position
    const tempRange = emergencyTemp + 10 - 0; // 0 to emergencyTemp + 10
    const pwmRange = 100 - 0; // 0 to 100

    const newTemp = Math.round(((x - offsetX) / chartWidth) * tempRange);
    const newPWM = Math.round(100 - ((y - offsetY) / chartHeight) * pwmRange);

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

  const handleMouseDown = (e: React.MouseEvent, index: number) => {
    if (!isEditing || isReadOnly) return;
    e.preventDefault();
    setDraggingIndex(index);

    const handleMouseMove = (moveEvent: MouseEvent) => {
      updatePointPosition(moveEvent.clientX, moveEvent.clientY, index);
    };

    const handleMouseUp = () => {
      setDraggingIndex(null);
      // Send final state to parent using ref to get latest value
      onPointsChange(localPointsRef.current);
      document.removeEventListener('mousemove', handleMouseMove);
      document.removeEventListener('mouseup', handleMouseUp);
    };

    document.addEventListener('mousemove', handleMouseMove);
    document.addEventListener('mouseup', handleMouseUp);
  };

  const handleTouchStart = (e: React.TouchEvent, index: number) => {
    if (!isEditing || isReadOnly) return;
    e.preventDefault();
    setDraggingIndex(index);

    const handleTouchMove = (moveEvent: TouchEvent) => {
      const touch = moveEvent.touches[0];
      updatePointPosition(touch.clientX, touch.clientY, index);
    };

    const handleTouchEnd = () => {
      setDraggingIndex(null);
      // Send final state to parent using ref to get latest value
      onPointsChange(localPointsRef.current);
      document.removeEventListener('touchmove', handleTouchMove);
      document.removeEventListener('touchend', handleTouchEnd);
    };

    document.addEventListener('touchmove', handleTouchMove);
    document.addEventListener('touchend', handleTouchEnd);
  };

  // Custom tooltip
  const CustomTooltip = ({ active, payload }: any) => {
    if (!active || !payload || payload.length === 0) return null;

    const data = payload[0].payload as ChartDataPoint;

    return (
      <div className="bg-slate-900 border border-slate-700 rounded-lg px-3 py-2 shadow-xl">
        <p className="text-xs text-slate-400">
          {data.isCurrentPoint ? 'Current' : 'Curve Point'}
        </p>
        <p className="text-sm font-semibold text-white">
          {data.temp.toFixed(1)}°C → {data.pwm}%
        </p>
      </div>
    );
  };

  return (
    <div ref={chartRef} className="w-full">
      <ResponsiveContainer width="100%" height={400}>
        <LineChart
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

          {/* Curve line */}
          <Line
            type="monotone"
            dataKey="pwm"
            stroke="#0ea5e9"
            strokeWidth={3}
            dot={<CustomDot />}
            activeDot={false}
            isAnimationActive={false}
          />

          {/* Current operating point */}
          {currentTemp !== null && (
            <Dot
              cx={0}
              cy={0}
              r={5}
              fill="#34d399"
              stroke="#1e293b"
              strokeWidth={2}
            />
          )}
        </LineChart>
      </ResponsiveContainer>

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

      {isEditing && !isReadOnly && (
        <p className="mt-3 text-xs text-slate-400 italic">
          Drag points to adjust the curve. Temperature and PWM values will update automatically.
        </p>
      )}
    </div>
  );
}
