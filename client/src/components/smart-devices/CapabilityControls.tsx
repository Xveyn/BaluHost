/**
 * Capability-specific UI controls for smart devices.
 *
 * Renders different controls based on what a device can do:
 * switch, power_monitor, sensor, dimmer, color.
 */

import { useState } from 'react';
import { Zap, Thermometer, ToggleLeft, ToggleRight, Sun } from 'lucide-react';

// --- Switch ---

interface SwitchControlProps {
  isOn: boolean;
  loading: boolean;
  onToggle: () => void;
}

export function SwitchControl({ isOn, loading, onToggle }: SwitchControlProps) {
  return (
    <button
      onClick={onToggle}
      disabled={loading}
      className={`flex items-center gap-2 rounded-lg border px-3 py-1.5 text-sm font-medium transition-all touch-manipulation active:scale-95 disabled:opacity-50 disabled:cursor-not-allowed ${
        isOn
          ? 'border-emerald-500/40 bg-emerald-500/15 text-emerald-300 hover:bg-emerald-500/25'
          : 'border-slate-700 bg-slate-800/60 text-slate-400 hover:border-slate-600 hover:text-slate-300'
      }`}
      title={isOn ? 'Turn off' : 'Turn on'}
    >
      {isOn ? (
        <ToggleRight className="h-4 w-4" />
      ) : (
        <ToggleLeft className="h-4 w-4" />
      )}
      <span>{isOn ? 'On' : 'Off'}</span>
    </button>
  );
}

// --- Power Monitor ---

interface PowerMonitorDisplayProps {
  watts: number | null;
  voltage?: number | null;
  current?: number | null;
}

export function PowerMonitorDisplay({ watts, voltage, current }: PowerMonitorDisplayProps) {
  return (
    <div className="flex flex-wrap items-center gap-3 text-sm">
      <div className="flex items-center gap-1 text-amber-400">
        <Zap className="h-4 w-4" />
        <span className="font-mono font-medium">
          {watts != null ? `${watts.toFixed(1)} W` : '— W'}
        </span>
      </div>
      {voltage != null && (
        <span className="text-slate-400 font-mono text-xs">{voltage.toFixed(1)} V</span>
      )}
      {current != null && (
        <span className="text-slate-400 font-mono text-xs">{current.toFixed(2)} A</span>
      )}
    </div>
  );
}

// --- Sensor ---

interface SensorDisplayProps {
  sensorName: string;
  value: number | string | null;
  unit?: string;
}

export function SensorDisplay({ sensorName, value, unit }: SensorDisplayProps) {
  return (
    <div className="flex items-center gap-2 text-sm">
      <Thermometer className="h-4 w-4 text-sky-400" />
      <span className="text-slate-400 text-xs">{sensorName}:</span>
      <span className="font-mono font-medium text-slate-200">
        {value != null ? `${value}${unit ? ` ${unit}` : ''}` : '—'}
      </span>
    </div>
  );
}

// --- Dimmer ---

interface DimmerControlProps {
  brightness: number; // 0–100
  loading: boolean;
  onChange: (value: number) => void;
}

export function DimmerControl({ brightness, loading, onChange }: DimmerControlProps) {
  const [localValue, setLocalValue] = useState(brightness);

  const handleChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    setLocalValue(Number(e.target.value));
  };

  const handleRelease = () => {
    onChange(localValue);
  };

  return (
    <div className="flex items-center gap-2 text-sm w-full">
      <Sun className="h-4 w-4 text-amber-400 flex-shrink-0" />
      <input
        type="range"
        min={0}
        max={100}
        value={localValue}
        disabled={loading}
        onChange={handleChange}
        onMouseUp={handleRelease}
        onTouchEnd={handleRelease}
        className="flex-1 h-1.5 accent-amber-400 cursor-pointer disabled:opacity-50"
      />
      <span className="text-slate-400 font-mono text-xs w-10 text-right">
        {localValue}%
      </span>
    </div>
  );
}

// --- Color ---

interface ColorState {
  hue: number;       // 0–360
  saturation: number; // 0–100
  brightness: number; // 0–100
}

interface ColorControlProps {
  color: ColorState;
  loading: boolean;
  onChange: (color: ColorState) => void;
}

export function ColorControl({ color, loading, onChange }: ColorControlProps) {
  const [local, setLocal] = useState(color);

  const commit = (updated: ColorState) => {
    onChange(updated);
  };

  const makeHandler =
    (field: keyof ColorState) => (e: React.ChangeEvent<HTMLInputElement>) => {
      const updated = { ...local, [field]: Number(e.target.value) };
      setLocal(updated);
      return updated;
    };

  return (
    <div className="space-y-2 w-full text-xs text-slate-400">
      {/* Hue slider */}
      <div className="flex items-center gap-2">
        <span className="w-14">Hue</span>
        <input
          type="range"
          min={0}
          max={360}
          value={local.hue}
          disabled={loading}
          onChange={makeHandler('hue')}
          onMouseUp={() => commit(local)}
          onTouchEnd={() => commit(local)}
          className="flex-1 h-1.5 cursor-pointer disabled:opacity-50"
          style={{
            background: `linear-gradient(to right, hsl(0,100%,50%), hsl(60,100%,50%), hsl(120,100%,50%), hsl(180,100%,50%), hsl(240,100%,50%), hsl(300,100%,50%), hsl(360,100%,50%))`,
          }}
        />
        <span className="font-mono w-8 text-right">{local.hue}</span>
      </div>

      {/* Saturation */}
      <div className="flex items-center gap-2">
        <span className="w-14">Sat</span>
        <input
          type="range"
          min={0}
          max={100}
          value={local.saturation}
          disabled={loading}
          onChange={makeHandler('saturation')}
          onMouseUp={() => commit(local)}
          onTouchEnd={() => commit(local)}
          className="flex-1 h-1.5 accent-sky-400 cursor-pointer disabled:opacity-50"
        />
        <span className="font-mono w-8 text-right">{local.saturation}%</span>
      </div>

      {/* Brightness */}
      <div className="flex items-center gap-2">
        <span className="w-14">Bright</span>
        <input
          type="range"
          min={0}
          max={100}
          value={local.brightness}
          disabled={loading}
          onChange={makeHandler('brightness')}
          onMouseUp={() => commit(local)}
          onTouchEnd={() => commit(local)}
          className="flex-1 h-1.5 accent-amber-400 cursor-pointer disabled:opacity-50"
        />
        <span className="font-mono w-8 text-right">{local.brightness}%</span>
      </div>

      {/* Color swatch */}
      <div
        className="h-5 w-full rounded border border-slate-700"
        style={{
          background: `hsl(${local.hue}, ${local.saturation}%, ${local.brightness / 2 + 25}%)`,
        }}
      />
    </div>
  );
}
