import { useCallback } from 'react';
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
import { formatNumber } from '../../lib/formatters';
import { useFanCurveInteraction, type ChartDataPoint } from '../../hooks/useFanCurveInteraction';
import { FanCurveTooltip, FanChartLegend, FanChartHint } from './fan-curve-chart';

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
  const {
    chartRef,
    overlayRef,
    draggingIndex,
    canEdit,
    localPoints,
    chartData,
    handleOverlayMouseDown,
    handleOverlayClick,
    handleOverlayContextMenu,
    handleOverlayTouchStart,
  } = useFanCurveInteraction(points, onPointsChange, {
    minPWM, maxPWM, emergencyTemp, isReadOnly, minPoints, maxPoints,
  });

  // Stable render function for dot prop (useCallback keeps reference identity across renders)
  const renderDot = useCallback((props: { cx?: number; cy?: number; payload?: ChartDataPoint; index?: number }) => {
    const { cx, cy, payload, index } = props;

    if (cx === undefined || cy === undefined) return null;
    if (!payload) return null;
    if (payload.isCurrentPoint) return null;

    const isHovered = draggingIndex === index;
    const radius = isHovered ? 10 : 7;
    const fill = isHovered ? '#38bdf8' : '#0ea5e9'; // sky-400 / sky-500

    return (
      <g>
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
        {isHovered && (
          <text x={cx} y={cy - 16} textAnchor="middle" fill="#e2e8f0"
            fontSize={12} fontWeight={600} style={{ pointerEvents: 'none' }}>
            {payload.temp.toFixed(1)}°C / {payload.pwm.toFixed(1)}%
          </text>
        )}
      </g>
    );
  }, [draggingIndex, canEdit]);

  // Data for the current operating point (separate from curve)
  const currentPointData = currentTemp !== null ? [{ temp: currentTemp, currentPwm: currentPWM }] : [];

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
          />

          {/* Y Axis - PWM */}
          <YAxis
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

          <Tooltip content={<FanCurveTooltip />} />

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
                value: `Now: ${formatNumber(currentTemp, 1)}°C`,
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
            data={chartData}
            stroke="#0ea5e9"
            strokeWidth={3}
            dot={renderDot}
            activeDot={false}
            isAnimationActive={false}
          />

          {/* Current operating point - rendered as separate scatter */}
          {currentTemp !== null && (
            <Scatter
              data={currentPointData}
              dataKey="currentPwm"
              fill="#34d399"
              shape={(props: { cx?: number; cy?: number }) => (
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

      {/* Transparent overlay for event handling - always rendered, disabled via pointerEvents */}
      <div
        ref={overlayRef}
        className="absolute inset-0"
        style={{
          zIndex: 10,
          cursor: canEdit ? (draggingIndex !== null ? 'grabbing' : 'crosshair') : 'default',
          background: 'rgba(0,0,0,0.001)', // Force browser hit-testing
          pointerEvents: canEdit ? 'auto' : 'none',
        }}
        onMouseDown={handleOverlayMouseDown}
        onClick={handleOverlayClick}
        onContextMenu={handleOverlayContextMenu}
        onTouchStart={handleOverlayTouchStart}
      />

      <FanChartLegend currentTemp={currentTemp} emergencyTemp={emergencyTemp} />

      {canEdit && (
        <FanChartHint pointCount={localPoints.length} minPoints={minPoints} maxPoints={maxPoints} />
      )}
    </div>
  );
}
