/**
 * API-Client der Displaysteuerung (bundled Plugin `display_output`).
 *
 * Alle Routen liegen hinter dem Recht `can_manage_displays` — auch die
 * lesende, weil die Ausgangsliste die angeschlossene Hardware verrät.
 *
 * Modi werden über `id` adressiert, nie über `name`: KWin bildet den Namen mit
 * gerundeter Bildwiederholrate, weshalb 119,88 und 120,00 Hz beide
 * „3840x2160@120" heißen. `mode_name` reist nur als Gegenprobe mit.
 */

import { apiClient } from '../lib/api';

const BASE = '/api/plugins/display_output';

export interface DisplayMode {
  /** Lebende KWin-Mode-ID. Nie speichern — sie gilt nur für diesen Abruf. */
  id: string;
  /** "3840x2160@120" — NICHT eindeutig. */
  name: string;
  width: number;
  height: number;
  /** Ungerundet, z. B. 119.87999725341797. */
  refresh_rate: number;
}

export interface DisplayOutput {
  name: string;
  connected: boolean;
  /** KWin-Ebene: ist dieser Ausgang gewählt? */
  selected: boolean;
  /** DRM-Ebene: werden Pixel getrieben? null = nicht zuordenbar. */
  lit: boolean | null;
  current_mode_id: string | null;
  preferred_mode_id: string | null;
  scale: number;
  priority: number;
  modes: DisplayMode[];
}

export interface DisplayLayout {
  outputs: DisplayOutput[];
  displays_powered: boolean;
  available: boolean;
  detail: string | null;
}

export interface DisplayOutputWish {
  name: string;
  selected: boolean;
  mode_id?: string;
  /** Pflicht, sobald mode_id gesetzt ist. */
  mode_name?: string;
}

/** Liest Ausgänge, Modi und den globalen DPMS-Zustand in einem Rundlauf. */
export async function getDisplayLayout(): Promise<DisplayLayout> {
  const { data } = await apiClient.get<DisplayLayout>(`${BASE}/state`);
  return data;
}

/** Setzt Auswahl und Modus — ein Aufruf, den das Backend atomar anwendet. */
export async function applyDisplayLayout(outputs: DisplayOutputWish[]): Promise<void> {
  await apiClient.post(`${BASE}/apply`, { outputs });
}

/**
 * Beschriftet einen Modus für das Auswahlfeld.
 *
 * Zwei Nachkommastellen sind nicht Kosmetik: sie sind das Einzige, woran ein
 * Mensch die beiden 4K-Modi von DP-3 auseinanderhält. Formatiert wird hier und
 * nicht im Backend, weil das Dezimaltrennzeichen sprachabhängig ist.
 */
export function formatMode(mode: DisplayMode, locale: string): string {
  const hz = new Intl.NumberFormat(locale, {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  }).format(mode.refresh_rate);
  return `${mode.width} × ${mode.height} @ ${hz} Hz`;
}
