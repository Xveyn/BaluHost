import { describe, it, expect, vi } from 'vitest';
import { getApiErrorMessage } from '../../lib/errorHandling';

// handleApiError calls toast.error internally — tested indirectly via getApiErrorMessage

describe('getApiErrorMessage', () => {
  it('extracts string detail from axios-style error', () => {
    const err = { response: { data: { detail: 'Not found' } } };
    expect(getApiErrorMessage(err, 'fallback')).toBe('Not found');
  });

  it('extracts first msg from FastAPI validation array', () => {
    const err = {
      response: {
        data: {
          detail: [{ msg: 'Field required', loc: ['body', 'name'] }],
        },
      },
    };
    expect(getApiErrorMessage(err, 'fallback')).toBe('Field required');
  });

  it('ignores empty validation array and falls through to Error', () => {
    const err = Object.assign(new Error('oops'), {
      response: { data: { detail: [] } },
    });
    expect(getApiErrorMessage(err, 'fallback')).toBe('oops');
  });

  it('returns Error.message for plain Error', () => {
    expect(getApiErrorMessage(new Error('boom'), 'fallback')).toBe('boom');
  });

  it('returns fallback for unknown error type', () => {
    expect(getApiErrorMessage(42, 'fallback')).toBe('fallback');
    expect(getApiErrorMessage(null, 'fallback')).toBe('fallback');
    expect(getApiErrorMessage(undefined, 'fallback')).toBe('fallback');
  });

  it('returns fallback when response has no detail', () => {
    const err = { response: { data: {} } };
    expect(getApiErrorMessage(err, 'fallback')).toBe('fallback');
  });

  it('returns fallback when response.data is undefined', () => {
    const err = { response: {} };
    expect(getApiErrorMessage(err, 'fallback')).toBe('fallback');
  });
});
