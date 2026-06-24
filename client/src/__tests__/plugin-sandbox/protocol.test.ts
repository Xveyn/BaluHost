import { describe, it, expect } from 'vitest';
import { isRpcRequest, isIframeEvent, RPC_CHANNELS } from '../../lib/plugin-sandbox/protocol';

describe('protocol validators', () => {
  it('accepts a well-formed rpc request on a known channel', () => {
    const msg = { kind: 'rpc', id: 'a1', channel: 'api', method: 'get', args: ['/api/plugins/x/y'] };
    expect(isRpcRequest(msg)).toBe(true);
  });
  it('rejects an rpc request on an unknown channel', () => {
    const msg = { kind: 'rpc', id: 'a1', channel: 'filesystem', method: 'read', args: [] };
    expect(isRpcRequest(msg)).toBe(false);
  });
  it('rejects rpc with non-string id or non-array args', () => {
    expect(isRpcRequest({ kind: 'rpc', id: 1, channel: 'api', method: 'get', args: [] })).toBe(false);
    expect(isRpcRequest({ kind: 'rpc', id: 'a', channel: 'api', method: 'get', args: 'x' })).toBe(false);
  });
  it('recognises iframe events', () => {
    expect(isIframeEvent({ kind: 'event', name: 'ready', payload: null })).toBe(true);
    expect(isIframeEvent({ kind: 'event', name: 'bogus', payload: null })).toBe(false);
  });
  it('exposes the fixed channel set', () => {
    expect([...RPC_CHANNELS].sort()).toEqual(['api', 'navigate', 'storage', 'toast']);
  });
});
