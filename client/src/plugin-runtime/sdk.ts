import { type RpcChannel } from '../lib/plugin-sandbox/protocol';

interface Pending { resolve: (v: unknown) => void; reject: (e: unknown) => void; timer: ReturnType<typeof setTimeout> }

export function createSandboxSdk(post: (msg: unknown) => void, opts: { timeoutMs?: number } = {}) {
  const timeoutMs = opts.timeoutMs ?? 30000;
  const pending = new Map<string, Pending>();
  let counter = 0;

  function call(channel: RpcChannel, method: string, args: unknown[]): Promise<unknown> {
    const id = `rpc-${++counter}`;
    return new Promise((resolve, reject) => {
      const timer = setTimeout(() => {
        pending.delete(id);
        reject({ code: 'timeout', message: `RPC ${channel}.${method} timed out` });
      }, timeoutMs);
      pending.set(id, { resolve, reject, timer });
      post({ kind: 'rpc', id, channel, method, args });
    });
  }

  function _receive(msg: { kind?: string; id?: string; ok?: boolean; value?: unknown; error?: unknown }): void {
    if (msg.kind !== 'rpc-result' || typeof msg.id !== 'string') return;
    const p = pending.get(msg.id);
    if (!p) return;
    clearTimeout(p.timer);
    pending.delete(msg.id);
    if (msg.ok) p.resolve(msg.value);
    else p.reject(msg.error ?? { code: 'error', message: 'failed' });
  }

  const api = {
    get: (url: string) => call('api', 'get', [url]),
    post: (url: string, data?: unknown) => call('api', 'post', [url, data]),
    put: (url: string, data?: unknown) => call('api', 'put', [url, data]),
    patch: (url: string, data?: unknown) => call('api', 'patch', [url, data]),
    delete: (url: string) => call('api', 'delete', [url]),
  };
  const toast = {
    success: (m: string) => post({ kind: 'rpc', id: `t-${++counter}`, channel: 'toast', method: 'success', args: [m] }),
    error: (m: string) => post({ kind: 'rpc', id: `t-${++counter}`, channel: 'toast', method: 'error', args: [m] }),
  };
  const navigate = (path: string) => call('navigate', 'go', [path]);

  return { api, toast, navigate, _receive };
}
