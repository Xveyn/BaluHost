import { useState, useEffect, useRef } from 'react';
import { getUnitConfig, type ByteUnitMode } from '../../lib/byteUnits';
import { useByteUnitMode } from '../../hooks/useByteUnitMode';

export interface ByteSizeInputProps {
  value: number;
  onChange: (bytes: number) => void;
  label?: string;
  min?: number;
  disabled?: boolean;
  className?: string;
  id?: string;
}

/** Pick the largest unit where the display value is >= 1 (or fall back to bytes). */
function bytesToDisplay(bytes: number, mode: ByteUnitMode): { displayValue: string; unit: string } {
  if (bytes === 0) return { displayValue: '0', unit: 'B' };

  const { divisor, units } = getUnitConfig(mode);
  let idx = 0;
  let val = bytes;

  while (idx < units.length - 1 && val >= divisor) {
    val /= divisor;
    idx++;
  }

  // Avoid floating-point noise: round to 4 decimal places, strip trailing zeros
  const rounded = parseFloat(val.toFixed(4));
  return { displayValue: String(rounded), unit: units[idx] };
}

function displayToBytes(displayValue: string, unit: string, mode: ByteUnitMode): number {
  const num = parseFloat(displayValue);
  if (isNaN(num) || num < 0) return 0;

  const { divisor, units } = getUnitConfig(mode);
  const idx = units.indexOf(unit);
  if (idx < 0) return 0;

  return Math.round(num * Math.pow(divisor, idx));
}

export function ByteSizeInput({
  value,
  onChange,
  label,
  min = 0,
  disabled = false,
  className = '',
  id,
}: ByteSizeInputProps) {
  const [mode] = useByteUnitMode();
  const { units } = getUnitConfig(mode);

  const [displayValue, setDisplayValue] = useState('0');
  const [selectedUnit, setSelectedUnit] = useState('B');

  // Track the last value we reported via onChange so we don't re-sync from
  // props while the user is editing (which would cause jumpy behaviour).
  const lastReportedBytes = useRef(value);

  // Sync from external value / mode change — but only when the external
  // value actually differs from what we last reported.
  useEffect(() => {
    if (value !== lastReportedBytes.current) {
      const { displayValue: dv, unit } = bytesToDisplay(value, mode);
      setDisplayValue(dv);
      setSelectedUnit(unit);
      lastReportedBytes.current = value;
    }
  }, [value, mode]);

  // When mode (binary ↔ decimal) changes, re-derive display from current bytes.
  const prevMode = useRef(mode);
  useEffect(() => {
    if (prevMode.current !== mode) {
      prevMode.current = mode;
      const bytes = lastReportedBytes.current;
      const { displayValue: dv, unit } = bytesToDisplay(bytes, mode);
      setDisplayValue(dv);
      setSelectedUnit(unit);
    }
  }, [mode]);

  function reportChange(dv: string, unit: string) {
    const bytes = displayToBytes(dv, unit, mode);
    const clamped = Math.max(bytes, min);
    lastReportedBytes.current = clamped;
    onChange(clamped);
  }

  function handleInputChange(raw: string) {
    setDisplayValue(raw);
    // Only report valid numbers
    if (raw !== '' && !isNaN(parseFloat(raw))) {
      reportChange(raw, selectedUnit);
    }
  }

  function handleUnitChange(newUnit: string) {
    setSelectedUnit(newUnit);
    reportChange(displayValue, newUnit);
  }

  // On blur, re-normalise the display (e.g. empty → "0")
  function handleBlur() {
    if (displayValue === '' || isNaN(parseFloat(displayValue))) {
      setDisplayValue('0');
      reportChange('0', selectedUnit);
    }
  }

  const inputId = id || label?.toLowerCase().replace(/\s+/g, '-');

  return (
    <div className={`w-full ${className}`}>
      {label && (
        <label
          htmlFor={inputId}
          className="block text-sm text-slate-400 mb-1"
        >
          {label}
        </label>
      )}
      <div className="flex">
        <input
          id={inputId}
          type="number"
          value={displayValue}
          onChange={(e) => handleInputChange(e.target.value)}
          onBlur={handleBlur}
          disabled={disabled}
          min={0}
          step="any"
          className="flex-1 min-w-0 px-3 py-1.5 bg-slate-800 border border-slate-700 rounded-l-lg text-white text-sm focus:ring-1 focus:ring-sky-500 focus:border-sky-500 outline-none disabled:opacity-50 [appearance:textfield] [&::-webkit-outer-spin-button]:appearance-none [&::-webkit-inner-spin-button]:appearance-none"
        />
        <select
          value={selectedUnit}
          onChange={(e) => handleUnitChange(e.target.value)}
          disabled={disabled}
          className="px-2 py-1.5 bg-slate-800 border border-slate-700 border-l-0 rounded-r-lg text-slate-300 text-sm focus:ring-1 focus:ring-sky-500 focus:border-sky-500 outline-none disabled:opacity-50 cursor-pointer"
        >
          {units.map((u) => (
            <option key={u} value={u}>{u}</option>
          ))}
        </select>
      </div>
    </div>
  );
}
