/**
 * Card component for a single smart device.
 *
 * Shows device status, capability controls, last-seen time, and errors.
 */

import { useState } from 'react';
import { AlertTriangle, Trash2, WifiOff } from 'lucide-react';
import type { SmartDevice, CommandResponse } from '../../api/smart-devices';
import { smartDevicesApi } from '../../api/smart-devices';
import {
  SwitchControl,
  PowerMonitorDisplay,
  SensorDisplay,
  DimmerControl,
  ColorControl,
} from './CapabilityControls';
import toast from 'react-hot-toast';

interface SmartDeviceCardProps {
  device: SmartDevice;
  isAdmin: boolean;
  onDelete: (id: number) => void;
  onStateChange: (id: number, state: Record<string, unknown>) => void;
}

function formatLastSeen(lastSeen: string | null): string {
  if (!lastSeen) return 'Never';
  const date = new Date(lastSeen);
  const now = Date.now();
  const diff = Math.floor((now - date.getTime()) / 1000);
  if (diff < 60) return `${diff}s ago`;
  if (diff < 3600) return `${Math.floor(diff / 60)}m ago`;
  if (diff < 86400) return `${Math.floor(diff / 3600)}h ago`;
  return date.toLocaleDateString();
}

export function SmartDeviceCard({
  device,
  isAdmin,
  onDelete,
  onStateChange,
}: SmartDeviceCardProps) {
  const [cmdLoading, setCmdLoading] = useState(false);

  const sendCommand = async (
    capability: string,
    command: string,
    params: Record<string, unknown> = {}
  ): Promise<CommandResponse | null> => {
    setCmdLoading(true);
    try {
      const res = await smartDevicesApi.command(device.id, { capability, command, params });
      if (res.data.success && res.data.state) {
        // Merge the command result into the correct capability key
        const mergedState = {
          ...(device.state ?? {}),
          [capability]: res.data.state,
        };
        onStateChange(device.id, mergedState);
      } else if (!res.data.success) {
        toast.error(res.data.error ?? 'Command failed');
      }
      return res.data;
    } catch {
      toast.error('Failed to send command');
      return null;
    } finally {
      setCmdLoading(false);
    }
  };

  // State is nested by capability: { switch: {...}, power_monitor: {...}, ... }
  const fullState = (device.state ?? {}) as Record<string, Record<string, unknown>>;

  // --- Capability renderers ---

  const renderSwitch = () => {
    const switchState = fullState.switch ?? {};
    const isOn = Boolean(switchState.is_on ?? false);
    return (
      <SwitchControl
        isOn={isOn}
        loading={cmdLoading}
        onToggle={() => sendCommand('switch', isOn ? 'turn_off' : 'turn_on')}
      />
    );
  };

  const renderPowerMonitor = () => {
    const pm = fullState.power_monitor ?? {};
    return (
      <PowerMonitorDisplay
        watts={(pm.watts as number | null) ?? null}
        voltage={(pm.voltage as number | null) ?? null}
        current={(pm.current as number | null) ?? null}
      />
    );
  };

  const renderSensor = () => {
    const sensor = fullState.sensor ?? {};
    return (
      <SensorDisplay
        sensorName={(sensor.sensor_name as string) ?? 'Sensor'}
        value={(sensor.value as number | string | null) ?? null}
        unit={(sensor.unit as string | undefined)}
      />
    );
  };

  const renderDimmer = () => {
    const dimmer = fullState.dimmer ?? {};
    const brightness = (dimmer.brightness as number) ?? 0;
    return (
      <DimmerControl
        brightness={brightness}
        loading={cmdLoading}
        onChange={(val) => sendCommand('dimmer', 'set_brightness', { brightness: val })}
      />
    );
  };

  const renderColor = () => {
    const color = fullState.color ?? {};
    const colorState = {
      hue: (color.hue as number) ?? 0,
      saturation: (color.saturation as number) ?? 100,
      brightness: (color.brightness as number) ?? 100,
    };
    return (
      <ColorControl
        color={colorState}
        loading={cmdLoading}
        onChange={(c) =>
          sendCommand('color', 'set_color', {
            hue: c.hue,
            saturation: c.saturation,
            brightness: c.brightness,
          })
        }
      />
    );
  };

  const capabilityRenderers: Record<string, () => React.ReactNode> = {
    switch: renderSwitch,
    power_monitor: renderPowerMonitor,
    sensor: renderSensor,
    dimmer: renderDimmer,
    color: renderColor,
  };

  return (
    <div
      className={`rounded-xl border bg-slate-900/55 p-4 flex flex-col gap-3 transition-all ${
        device.is_online
          ? 'border-slate-800/60'
          : 'border-slate-800/30 opacity-75'
      }`}
    >
      {/* Header row */}
      <div className="flex items-start justify-between gap-2">
        <div className="min-w-0">
          <div className="flex items-center gap-2">
            {/* Online/Offline dot */}
            <span
              className={`inline-block h-2.5 w-2.5 rounded-full flex-shrink-0 ${
                device.is_online ? 'bg-emerald-400' : 'bg-rose-500'
              }`}
              title={device.is_online ? 'Online' : 'Offline'}
            />
            <h3 className="font-medium text-white truncate text-sm">{device.name}</h3>
          </div>
          <p className="text-xs text-slate-500 truncate mt-0.5">
            {device.plugin_name} · {device.device_type_id}
          </p>
          {!device.is_online && (
            <p className="flex items-center gap-1 text-xs text-rose-400 mt-0.5">
              <WifiOff className="h-3 w-3" />
              Offline
            </p>
          )}
        </div>

        {/* Admin actions */}
        {isAdmin && (
          <button
            onClick={() => onDelete(device.id)}
            className="flex-shrink-0 rounded-lg border border-rose-500/20 bg-rose-500/5 p-1.5 text-rose-400 hover:border-rose-500/40 hover:bg-rose-500/10 transition touch-manipulation active:scale-95"
            title="Delete device"
          >
            <Trash2 className="h-4 w-4" />
          </button>
        )}
      </div>

      {/* Capability controls */}
      {device.is_active && device.capabilities.length > 0 && (
        <div className="flex flex-col gap-2">
          {device.capabilities.map((cap) => {
            const render = capabilityRenderers[cap];
            if (!render) return null;
            return (
              <div key={cap} className="flex flex-col gap-1">
                <span className="text-[10px] uppercase tracking-wider text-slate-500">{cap}</span>
                {render()}
              </div>
            );
          })}
        </div>
      )}

      {/* Inactive device notice */}
      {!device.is_active && (
        <p className="text-xs text-slate-500 italic">Device is disabled</p>
      )}

      {/* Footer: last seen + error */}
      <div className="flex items-center justify-between pt-1 border-t border-slate-800/50 mt-auto">
        <span className="text-xs text-slate-600">
          {device.is_online ? 'Last seen' : 'Went offline'}: {formatLastSeen(device.last_seen)}
        </span>
        {device.last_error && (
          <span
            className="flex items-center gap-1 text-xs text-amber-400 max-w-[60%] truncate"
            title={device.last_error}
          >
            <AlertTriangle className="h-3 w-3 flex-shrink-0" />
            <span className="truncate">{device.last_error}</span>
          </span>
        )}
      </div>
    </div>
  );
}
