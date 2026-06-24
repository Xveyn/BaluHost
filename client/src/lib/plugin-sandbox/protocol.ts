export const RPC_CHANNELS = ['api', 'toast', 'navigate', 'storage'] as const;
export type RpcChannel = (typeof RPC_CHANNELS)[number];

export const IFRAME_EVENTS = ['ready', 'resize', 'error'] as const;
export type IframeEventName = (typeof IFRAME_EVENTS)[number];

export const HOST_PUSHES = ['init', 'theme-changed', 'visibility'] as const;
export type HostPushName = (typeof HOST_PUSHES)[number];

export interface RpcRequest {
  kind: 'rpc';
  id: string;
  channel: RpcChannel;
  method: string;
  args: unknown[];
}
export interface RpcResult {
  kind: 'rpc-result';
  id: string;
  ok: boolean;
  value?: unknown;
  error?: { code: string; message: string };
}
export interface IframeEvent {
  kind: 'event';
  name: IframeEventName;
  payload: unknown;
}
export interface HostPush {
  kind: 'push';
  name: HostPushName;
  payload: unknown;
}

function isObj(m: unknown): m is Record<string, unknown> {
  return typeof m === 'object' && m !== null;
}
export function isRpcRequest(m: unknown): m is RpcRequest {
  return (
    isObj(m) && m.kind === 'rpc' && typeof m.id === 'string' &&
    typeof m.method === 'string' && Array.isArray(m.args) &&
    typeof m.channel === 'string' && (RPC_CHANNELS as readonly string[]).includes(m.channel)
  );
}
export function isIframeEvent(m: unknown): m is IframeEvent {
  return (
    isObj(m) && m.kind === 'event' && typeof m.name === 'string' &&
    (IFRAME_EVENTS as readonly string[]).includes(m.name)
  );
}
