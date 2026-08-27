/**
 * API-Client der Audiosteuerung (bundled Plugin `audio_control`).
 *
 * Alle Routen liegen hinter dem Recht `can_control_audio` — auch die lesende,
 * weil die Stream-Titel verraten, was auf dem Desktop gerade laeuft.
 */

import { apiClient } from '../lib/api';

const BASE = '/api/plugins/audio_control';

export interface AudioSink {
  id: number;
  name: string;
  description: string;
  volume_percent: number;
  muted: boolean;
  is_default: boolean;
}

export interface AudioStream {
  id: number;
  sink_id: number;
  application: string;
  binary: string | null;
  /** media.name — nur als Tooltip anzeigen, nie als Beschriftung. */
  title: string | null;
  volume_percent: number;
  muted: boolean;
  corked: boolean;
}

export interface AudioState {
  sinks: AudioSink[];
  streams: AudioStream[];
  available: boolean;
  detail: string | null;
}

/** Liest Geraete, Streams und Standardgeraet in einem Rundlauf. */
export async function getAudioState(): Promise<AudioState> {
  const { data } = await apiClient.get<AudioState>(`${BASE}/state`);
  return data;
}

/** Setzt den Pegel eines Ausgabegeraets (0-150). */
export async function setSinkVolume(sinkId: number, percent: number): Promise<void> {
  await apiClient.put(`${BASE}/sinks/${sinkId}/volume`, { percent });
}

/** Schaltet ein Ausgabegeraet stumm oder wieder laut. */
export async function setSinkMute(sinkId: number, muted: boolean): Promise<void> {
  await apiClient.put(`${BASE}/sinks/${sinkId}/mute`, { muted });
}

/** Macht ein Geraet zum Standardausgang. */
export async function setDefaultSink(name: string): Promise<void> {
  await apiClient.put(`${BASE}/default-sink`, { name });
}

/** Setzt den Pegel eines einzelnen Streams (0-150). */
export async function setStreamVolume(streamId: number, percent: number): Promise<void> {
  await apiClient.put(`${BASE}/streams/${streamId}/volume`, { percent });
}

/** Schaltet einen einzelnen Stream stumm oder wieder laut. */
export async function setStreamMute(streamId: number, muted: boolean): Promise<void> {
  await apiClient.put(`${BASE}/streams/${streamId}/mute`, { muted });
}
