import { useEffect, useState } from 'react';
import { listDevices, listSchedules, createSchedule, getPlanForDevice, type Device, type Schedule } from '../lib/mockSyncApi';

export default function SyncPrototype() {
  const [devices, setDevices] = useState<Device[]>([]);
  const [schedules, setSchedules] = useState<Schedule[]>([]);
  const [selectedDevice, setSelectedDevice] = useState('');
  const [time, setTime] = useState('02:00');
  const [plan, setPlan] = useState<any | null>(null);

  useEffect(() => {
    (async () => {
      setDevices(await listDevices());
      setSchedules(await listSchedules());
    })();
  }, []);

  async function handleCreate() {
    if (!selectedDevice) return;
    const s = await createSchedule({ device_id: selectedDevice, schedule_type: 'daily', time_of_day: time });
    setSchedules((p) => [...p, s]);
  }

  async function fetchPlan(deviceId: string) {
    const p = await getPlanForDevice(deviceId);
    setPlan(p);
  }

  return (
    <div className="p-6">
      <h2 className="text-2xl font-bold mb-4">Sync Prototype (Mock)</h2>
      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        <div className="p-4 bg-slate-800 rounded">
          <h3 className="font-semibold mb-2">Devices</h3>
          <ul className="space-y-2">
            {devices.map(d => (
              <li key={d.device_id} className="flex items-center justify-between">
                <div>
                  <div className="font-medium">{d.device_name}</div>
                  <div className="text-sm text-slate-400">{d.device_id} • last sync: {d.last_sync ?? 'never'}</div>
                </div>
                <div className="flex gap-2">
                  <button className="px-2 py-1 bg-sky-600 rounded text-white" onClick={() => { setSelectedDevice(d.device_id); fetchPlan(d.device_id); }}>Get Plan</button>
                </div>
              </li>
            ))}
          </ul>
        </div>

        <div className="p-4 bg-slate-800 rounded">
          <h3 className="font-semibold mb-2">Create Schedule</h3>
          <div className="flex gap-2">
            <select value={selectedDevice} onChange={e => setSelectedDevice(e.target.value)} className="p-2 bg-slate-700 rounded">
              <option value="">Select device</option>
              {devices.map(d => <option value={d.device_id} key={d.device_id}>{d.device_name}</option>)}
            </select>
            <input type="time" value={time} onChange={e => setTime(e.target.value)} className="p-2 bg-slate-700 rounded" />
            <button onClick={handleCreate} className="px-3 py-2 bg-emerald-500 rounded text-white">Create</button>
          </div>

          <h4 className="mt-4 font-semibold">Schedules</h4>
          <ul className="mt-2 space-y-2">
            {schedules.map(s => (
              <li key={s.schedule_id} className="text-sm">{s.device_id} — {s.schedule_type} @ {s.time_of_day} (next: {s.next_run_at ?? 'N/A'})</li>
            ))}
          </ul>
        </div>
      </div>

      <div className="mt-6 p-4 bg-slate-800 rounded">
        <h3 className="font-semibold mb-2">Plan</h3>
        <pre className="text-sm whitespace-pre-wrap text-slate-200">{plan ? JSON.stringify(plan, null, 2) : 'No plan loaded'}</pre>
      </div>
    </div>
  );
}
