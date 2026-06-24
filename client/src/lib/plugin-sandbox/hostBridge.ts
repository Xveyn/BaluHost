// client/src/lib/plugin-sandbox/hostBridge.ts
import { apiClient } from '../api';
import { isRpcRequest, isIframeEvent, type RpcResult, type HostPush, type ThemePayload } from './protocol';
import { isCallAllowed } from './scopeCatalog';

interface User { id: number; username: string; role: string }

export interface PluginBridgeOpts {
  iframe: HTMLIFrameElement;
  pluginName: string;
  grantedScopes: string[];
  user: User;
  theme: ThemePayload;
  minRuntimeAbi?: number;
  onResize?: (height: number) => void;
  onNavigate?: (path: string) => void;
  onError?: (code: string) => void;
  timeoutMs?: number;
}

export class PluginBridge {
  private listener = (ev: MessageEvent) => this.handleMessage(ev);
  private opts: PluginBridgeOpts;
  private theme: ThemePayload;
  private started = false;
  constructor(opts: PluginBridgeOpts) {
    this.opts = opts;
    this.theme = opts.theme;
  }

  start(): void {
    this.started = true;
    window.addEventListener('message', this.listener);
  }
  dispose(): void {
    this.started = false;
    window.removeEventListener('message', this.listener);
  }

  /** Update the active theme; if the frame is live, push it so the plugin restyles. */
  setTheme(theme: ThemePayload): void {
    this.theme = theme;
    if (this.started) {
      this.post({ kind: 'push', name: 'theme-changed', payload: theme });
    }
  }

  private post(msg: RpcResult | HostPush): void {
    this.opts.iframe.contentWindow?.postMessage(msg, '*');
  }

  private async handleMessage(ev: MessageEvent): Promise<void> {
    // Opaque-origin frames post origin "null" — trust the window reference only.
    if (ev.source !== this.opts.iframe.contentWindow) return;
    const data = ev.data;

    if (isIframeEvent(data)) {
      if (data.name === 'ready') {
        const runtimeAbi = (data.payload as { runtime_abi?: unknown })?.runtime_abi;
        const abi = typeof runtimeAbi === 'number' ? runtimeAbi : 1;
        if (this.opts.minRuntimeAbi !== undefined && abi < this.opts.minRuntimeAbi) {
          this.opts.onError?.('abi_mismatch');
          return;
        }
        this.post({
          kind: 'push', name: 'init',
          payload: { user: this.opts.user, pluginName: this.opts.pluginName, theme: this.theme },
        });
      } else if (data.name === 'resize') {
        const h = (data.payload as { height?: unknown })?.height;
        if (typeof h === 'number') this.opts.onResize?.(h);
      } else if (data.name === 'error') {
        this.opts.onError?.('plugin_error');
      }
      return;
    }

    if (!isRpcRequest(data)) return;
    try {
      const value = await this.dispatch(data.channel, data.method, data.args);
      this.post({ kind: 'rpc-result', id: data.id, ok: true, value });
    } catch (err) {
      const e = err as { code?: string; message?: string };
      this.post({
        kind: 'rpc-result', id: data.id, ok: false,
        error: { code: e.code ?? 'error', message: e.message ?? 'Plugin call failed' },
      });
    }
  }

  private async dispatch(channel: string, method: string, args: unknown[]): Promise<unknown> {
    if (channel === 'api') return this.apiCall(method, args);
    if (channel === 'navigate') {
      const path = String(args[0] ?? '');
      const prefix = `/plugins/${this.opts.pluginName}`;
      if (path !== prefix && !path.startsWith(prefix + '/')) throw { code: 'navigate_denied', message: 'Out-of-plugin navigation blocked' };
      this.opts.onNavigate?.(path);
      return null;
    }
    throw { code: 'unknown_channel', message: `Unknown channel ${channel}` };
  }

  private async apiCall(method: string, args: unknown[]): Promise<unknown> {
    const url = String(args[0] ?? '');
    const body = args[1];
    if (!isCallAllowed({ pluginName: this.opts.pluginName, method, url, grantedScopes: this.opts.grantedScopes })) {
      console.warn('[plugin:' + this.opts.pluginName + '] scope_denied', method, url);
      apiClient.post('/api/plugins/' + this.opts.pluginName + '/_audit/scope-denied', { method, url }).catch(() => {});
      throw { code: 'scope_denied', message: `Plugin not permitted to call ${method.toUpperCase()} ${url}` };
    }
    const res = await apiClient.request({ url, method, data: body });
    return res.data;
  }
}
