export interface Device {
  device_id: string;
  device_name: string;
  last_sync?: string | null;
  pending_changes?: number;
}

export interface Schedule {
  schedule_id: number;
  device_id: string;
  schedule_type: string;
  time_of_day: string;
  next_run_at?: string | null;
}

let nextScheduleId = 1000;

const devices: Device[] = [
  { device_id: 'desktop-SVEN-PC', device_name: 'Desktop - SVEN-PC', last_sync: '2025-12-07T20:10:47Z', pending_changes: 1 },
  { device_id: 'laptop-anna', device_name: 'Laptop - Anna', last_sync: null, pending_changes: 0 }
];

const schedules: Schedule[] = [];

export async function listDevices(): Promise<Device[]> {
  await new Promise((r) => setTimeout(r, 150));
  return devices;
}

export async function listSchedules(): Promise<Schedule[]> {
  await new Promise((r) => setTimeout(r, 120));
  return schedules;
}

export async function createSchedule(payload: Omit<Schedule, 'schedule_id' | 'next_run_at'>): Promise<Schedule> {
  await new Promise((r) => setTimeout(r, 200));
  const s: Schedule = {
    schedule_id: nextScheduleId++,
    device_id: payload.device_id,
    schedule_type: payload.schedule_type,
    time_of_day: payload.time_of_day,
    next_run_at: new Date(Date.now() + 60 * 60 * 1000).toISOString()
  };
  schedules.push(s);
  return s;
}

export async function getPlanForDevice(device_id: string) {
  await new Promise((r) => setTimeout(r, 180));
  // Return a simple mock plan
  return {
    device_id,
    to_download: [
      { path: '/docs/readme.md', size: 1024, content_hash: 'deadbeef' }
    ],
    to_delete: [],
    conflicts: []
  };
}
