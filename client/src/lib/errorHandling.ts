import toast from 'react-hot-toast';

/**
 * Extract a user-facing error message from an API error.
 *
 * Handles:
 * - Standard `Error` instances (from `throw new Error(...)`)
 * - Axios errors with `response.data.detail` (string or FastAPI validation array)
 * - Unknown error types (falls back to `fallbackMessage`)
 */
export function getApiErrorMessage(err: unknown, fallbackMessage: string): string {
  // Axios / fetch error with response body
  const resp = (err as { response?: { data?: { detail?: unknown } } })?.response;
  if (resp?.data?.detail) {
    const detail = resp.data.detail;
    if (typeof detail === 'string') return detail;
    // FastAPI validation errors: [{msg: "...", ...}, ...]
    if (Array.isArray(detail) && detail.length > 0 && typeof detail[0]?.msg === 'string') {
      return detail[0].msg;
    }
  }

  if (err instanceof Error) return err.message;

  return fallbackMessage;
}

/**
 * Show a toast.error with the extracted API error message.
 */
export function handleApiError(err: unknown, fallbackMessage: string): void {
  toast.error(getApiErrorMessage(err, fallbackMessage));
}
