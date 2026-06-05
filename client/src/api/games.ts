import { apiClient } from '../lib/api';

export interface GameEntry {
  app_id: string;
  name: string;
  size_bytes: number;
}

export interface GameLibrary {
  provider: string;
  provider_name: string;
  path: string;
  device_id: number | null;
  total_bytes: number;
  game_count: number;
  games: GameEntry[];
}

export interface GameLibrariesResponse {
  libraries: GameLibrary[];
  total_bytes: number;
  available: boolean;
}

export const getGameLibraries = async (): Promise<GameLibrariesResponse> => {
  const response = await apiClient.get('/api/games/libraries');
  return response.data;
};
