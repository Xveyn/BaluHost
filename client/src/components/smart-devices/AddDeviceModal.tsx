/**
 * Two-step modal for adding a new smart device.
 *
 * Step 1: Select a device type from the available types.
 * Step 2: Fill in device details (name, address, config).
 */

import { useState, useEffect } from 'react';
import { ChevronRight, ChevronLeft, Loader2, Cpu } from 'lucide-react';
import { Modal } from '../ui/Modal';
import type { DeviceType, CreateDeviceRequest } from '../../api/smart-devices';
import { smartDevicesApi } from '../../api/smart-devices';
import toast from 'react-hot-toast';

interface AddDeviceModalProps {
  isOpen: boolean;
  onClose: () => void;
  onCreated: () => void;
}

type Step = 'select-type' | 'fill-details';

export function AddDeviceModal({ isOpen, onClose, onCreated }: AddDeviceModalProps) {
  const [step, setStep] = useState<Step>('select-type');
  const [deviceTypes, setDeviceTypes] = useState<DeviceType[]>([]);
  const [typesLoading, setTypesLoading] = useState(false);
  const [selectedType, setSelectedType] = useState<DeviceType | null>(null);

  // Form state
  const [name, setName] = useState('');
  const [address, setAddress] = useState('');
  const [macAddress, setMacAddress] = useState('');
  const [configValues, setConfigValues] = useState<Record<string, string>>({});
  const [submitting, setSubmitting] = useState(false);

  // Load device types when modal opens
  useEffect(() => {
    if (!isOpen) return;
    setTypesLoading(true);
    smartDevicesApi
      .getTypes()
      .then((res) => setDeviceTypes(res.data))
      .catch(() => toast.error('Failed to load device types'))
      .finally(() => setTypesLoading(false));
  }, [isOpen]);

  // Reset when closing
  const handleClose = () => {
    setStep('select-type');
    setSelectedType(null);
    setName('');
    setAddress('');
    setMacAddress('');
    setConfigValues({});
    onClose();
  };

  const handleSelectType = (dt: DeviceType) => {
    setSelectedType(dt);
    setStep('fill-details');
    // Pre-populate config fields with empty strings
    if (dt.config_schema?.properties) {
      const defaults: Record<string, string> = {};
      for (const key of Object.keys(dt.config_schema.properties)) {
        defaults[key] = '';
      }
      setConfigValues(defaults);
    }
  };

  const handleSubmit = async () => {
    if (!selectedType) return;
    if (!name.trim()) {
      toast.error('Device name is required');
      return;
    }
    if (!address.trim()) {
      toast.error('Device address / IP is required');
      return;
    }

    setSubmitting(true);
    try {
      // Build config: filter out empty optional values
      const config: Record<string, unknown> = {};
      for (const [k, v] of Object.entries(configValues)) {
        if (v !== '') config[k] = v;
      }

      const payload: CreateDeviceRequest = {
        name: name.trim(),
        plugin_name: selectedType.plugin_name,
        device_type_id: selectedType.type_id,
        address: address.trim(),
        config,
      };
      if (macAddress.trim()) {
        payload.mac_address = macAddress.trim();
      }

      await smartDevicesApi.create(payload);
      toast.success(`Device "${name.trim()}" added`);
      onCreated();
      handleClose();
    } catch (err: unknown) {
      const msg =
        (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail ??
        'Failed to create device';
      toast.error(msg);
    } finally {
      setSubmitting(false);
    }
  };

  // Extract config field labels from schema
  const configSchema = selectedType?.config_schema;
  const configFields: Array<{ key: string; label: string; required: boolean; description?: string }> =
    configSchema?.properties
      ? Object.entries(configSchema.properties as Record<string, { title?: string; description?: string }>).map(
          ([key, prop]) => ({
            key,
            label: prop.title ?? key,
            required: Array.isArray(configSchema.required)
              ? (configSchema.required as string[]).includes(key)
              : false,
            description: prop.description,
          })
        )
      : [];

  return (
    <Modal isOpen={isOpen} onClose={handleClose} title="Add Smart Device" size="lg">
      {/* Step indicator */}
      <div className="flex items-center gap-2 mb-5 text-xs text-slate-500">
        <span
          className={`px-2.5 py-1 rounded-full border transition-colors ${
            step === 'select-type'
              ? 'border-sky-500/50 bg-sky-500/10 text-sky-300'
              : 'border-slate-700 text-slate-500'
          }`}
        >
          1. Choose type
        </span>
        <ChevronRight className="h-4 w-4" />
        <span
          className={`px-2.5 py-1 rounded-full border transition-colors ${
            step === 'fill-details'
              ? 'border-sky-500/50 bg-sky-500/10 text-sky-300'
              : 'border-slate-700 text-slate-500'
          }`}
        >
          2. Device details
        </span>
      </div>

      {/* Step 1: Select type */}
      {step === 'select-type' && (
        <div className="space-y-3">
          {typesLoading ? (
            <div className="flex items-center justify-center py-10">
              <Loader2 className="h-6 w-6 animate-spin text-sky-400" />
            </div>
          ) : deviceTypes.length === 0 ? (
            <div className="py-10 text-center">
              <Cpu className="h-10 w-10 mx-auto text-slate-600 mb-3" />
              <p className="text-sm text-slate-500">No device types available.</p>
              <p className="text-xs text-slate-600 mt-1">
                Enable a smart device plugin first (e.g. Tapo).
              </p>
            </div>
          ) : (
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-2 max-h-72 overflow-y-auto pr-1">
              {deviceTypes.map((dt) => (
                <button
                  key={dt.type_id}
                  onClick={() => handleSelectType(dt)}
                  className="flex items-center gap-3 rounded-xl border border-slate-700 bg-slate-800/40 px-4 py-3 text-left hover:border-sky-500/50 hover:bg-slate-800/70 transition touch-manipulation active:scale-[0.98]"
                >
                  <div className="flex h-10 w-10 flex-shrink-0 items-center justify-center rounded-lg bg-slate-900 border border-slate-700 text-2xl">
                    {dt.icon || '🔌'}
                  </div>
                  <div className="min-w-0">
                    <p className="text-sm font-medium text-white truncate">{dt.display_name}</p>
                    <p className="text-xs text-slate-500 truncate">{dt.manufacturer}</p>
                    <p className="text-xs text-slate-600 truncate">
                      {dt.capabilities.join(' · ')}
                    </p>
                  </div>
                </button>
              ))}
            </div>
          )}
        </div>
      )}

      {/* Step 2: Fill details */}
      {step === 'fill-details' && selectedType && (
        <div className="space-y-4">
          {/* Selected type summary */}
          <div className="flex items-center gap-3 rounded-lg border border-slate-700 bg-slate-800/30 px-4 py-2">
            <span className="text-2xl">{selectedType.icon || '🔌'}</span>
            <div>
              <p className="text-sm font-medium text-white">{selectedType.display_name}</p>
              <p className="text-xs text-slate-500">{selectedType.manufacturer}</p>
            </div>
            <button
              onClick={() => setStep('select-type')}
              className="ml-auto flex items-center gap-1 text-xs text-sky-400 hover:text-sky-300 transition"
            >
              <ChevronLeft className="h-3.5 w-3.5" />
              Change
            </button>
          </div>

          {/* Name */}
          <div>
            <label className="block text-xs font-medium text-slate-400 mb-1">
              Device name <span className="text-rose-400">*</span>
            </label>
            <input
              type="text"
              value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder="e.g. Living Room Lamp"
              className="w-full rounded-lg border border-slate-700 bg-slate-900/70 px-3 py-2 text-sm text-slate-200 placeholder-slate-600 focus:border-sky-500 focus:outline-none focus:ring-1 focus:ring-sky-500"
            />
          </div>

          {/* Address */}
          <div>
            <label className="block text-xs font-medium text-slate-400 mb-1">
              IP address / hostname <span className="text-rose-400">*</span>
            </label>
            <input
              type="text"
              value={address}
              onChange={(e) => setAddress(e.target.value)}
              placeholder="192.168.1.x"
              className="w-full rounded-lg border border-slate-700 bg-slate-900/70 px-3 py-2 text-sm text-slate-200 placeholder-slate-600 focus:border-sky-500 focus:outline-none focus:ring-1 focus:ring-sky-500"
            />
          </div>

          {/* MAC address (optional) */}
          <div>
            <label className="block text-xs font-medium text-slate-400 mb-1">
              MAC address <span className="text-slate-600">(optional)</span>
            </label>
            <input
              type="text"
              value={macAddress}
              onChange={(e) => setMacAddress(e.target.value)}
              placeholder="AA:BB:CC:DD:EE:FF"
              className="w-full rounded-lg border border-slate-700 bg-slate-900/70 px-3 py-2 text-sm text-slate-200 placeholder-slate-600 focus:border-sky-500 focus:outline-none focus:ring-1 focus:ring-sky-500"
            />
          </div>

          {/* Dynamic config fields from schema */}
          {configFields.length > 0 && (
            <div className="space-y-3">
              <p className="text-xs font-semibold uppercase tracking-wider text-slate-500">
                Plugin configuration
              </p>
              {configFields.map((field) => (
                <div key={field.key}>
                  <label className="block text-xs font-medium text-slate-400 mb-1">
                    {field.label}
                    {field.required && <span className="text-rose-400 ml-1">*</span>}
                  </label>
                  <input
                    type="text"
                    value={configValues[field.key] ?? ''}
                    onChange={(e) =>
                      setConfigValues((prev) => ({ ...prev, [field.key]: e.target.value }))
                    }
                    placeholder={field.description ?? field.key}
                    className="w-full rounded-lg border border-slate-700 bg-slate-900/70 px-3 py-2 text-sm text-slate-200 placeholder-slate-600 focus:border-sky-500 focus:outline-none focus:ring-1 focus:ring-sky-500"
                  />
                  {field.description && (
                    <p className="text-xs text-slate-600 mt-0.5">{field.description}</p>
                  )}
                </div>
              ))}
            </div>
          )}

          {/* Actions */}
          <div className="flex gap-2 pt-1">
            <button
              onClick={handleClose}
              className="flex-1 rounded-lg border border-slate-700 bg-slate-900/70 px-4 py-2 text-sm font-medium text-slate-300 hover:bg-slate-800 transition touch-manipulation active:scale-95"
            >
              Cancel
            </button>
            <button
              onClick={handleSubmit}
              disabled={submitting}
              className="flex-1 flex items-center justify-center gap-2 rounded-lg border border-sky-500/30 bg-sky-500/10 px-4 py-2 text-sm font-medium text-sky-200 hover:border-sky-500/50 hover:bg-sky-500/20 disabled:opacity-50 disabled:cursor-not-allowed transition touch-manipulation active:scale-95"
            >
              {submitting ? (
                <>
                  <Loader2 className="h-4 w-4 animate-spin" />
                  Adding…
                </>
              ) : (
                'Add Device'
              )}
            </button>
          </div>
        </div>
      )}
    </Modal>
  );
}
