const rawBaseUrl = (import.meta.env.VITE_API_BASE_URL ?? '').trim()
const normalisedBase = rawBaseUrl.endsWith('/') ? rawBaseUrl.slice(0, -1) : rawBaseUrl

export const API_BASE_URL = normalisedBase

export const buildApiUrl = (path: string): string => {
  if (!path.startsWith('/')) {
    return `${API_BASE_URL}/${path}`
  }
  return `${API_BASE_URL}${path}`
}
