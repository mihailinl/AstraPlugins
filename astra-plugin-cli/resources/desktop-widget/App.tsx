// SPDX-License-Identifier: MPL-2.0
import {useEffect, useRef, useState} from 'react';
import {mount, Section, SettingRow, Input, NumberInput, Select, Button} from '@astra/plugin-ui';
type Context = {
  widgetId: string; instanceId: string; formatId: string; viewId: string;
  preview: boolean; active: boolean; width: number; height: number;
  config: Record<string, unknown>; params?: unknown;
};
declare const astra: {
  loadUi(options: {apiVersion: 1}): Promise<unknown>;
  callBackend(method: string, params: unknown): Promise<unknown>;
  widget: {
    getContext(): Promise<Context>;
    getConfig(): Promise<Record<string, unknown>>;
    setConfig(config: Record<string, unknown>): Promise<boolean>;
    getData(key: string): Promise<string | null>;
    setData(key: string, value: string): Promise<boolean>;
    openSurface(id: string, options?: {anchor?: HTMLElement; params?: unknown}): Promise<string>;
    closeSurface(tokenOrId?: string): Promise<boolean>;
    onContextChange(callback: (context: Context) => void): () => void;
    onDataChange(callback: (event: {key: string; value: string | null}) => void): () => void;
  };
};
const initial = await astra.widget.getContext();
const initialCount = initial.preview ? 3 : Number(await astra.widget.getData('count') ?? 0);
const colors = [{value: 'default', label: 'Default'}, {value: 'accent', label: 'Accent'}];
function App() {
  const [context, setContext] = useState(initial), [count, setCount] = useState(initialCount);
  const [result, setResult] = useState(''), [error, setError] = useState(''), [busy, setBusy] = useState(false);
  const state = useRef({context: initial, host: {...initial.config}, version: 0, acknowledged: 0,
    pending: new Map<string, {value: unknown; serial: number}>(), disposed: false, busy: false});
  function desired() {
    const merged = {...state.current.host};
    for (const [key, edit] of state.current.pending) merged[key] = edit.value;
    return merged;
  }
  function refresh(next = state.current.context) {
    state.current.context = {...next, config: desired()};
    if (!state.current.disposed) setContext(state.current.context);
  }
  useEffect(() => {
    state.current.disposed = false;
    const stopContext = astra.widget.onContextChange(next => {
      state.current.host = {...next.config}; refresh(next);
    });
    const stopData = astra.widget.onDataChange(({key, value}) => {
      if (key === 'count' && !state.current.context.preview && !state.current.disposed) setCount(Number(value ?? 0));
    });
    return () => {state.current.disposed = true; stopContext(); stopData();};
  }, []);
  async function perform(action: () => unknown) {
    if (state.current.context.preview || !state.current.context.active || state.current.disposed) return;
    setError('');
    try {await action();} catch (cause) {if (!state.current.disposed) setError(String(cause));}
  }
  function config(key: string, value: unknown) {
    if (key === 'limit' && (typeof value !== 'number' || !Number.isFinite(value) || value < 1 || value > 1000)) {
      throw new Error('Count limit must be a finite number from 1 to 1000.');
    }
    const current = state.current, serial = ++current.version;
    current.pending.set(key, {value, serial});
    const next = desired(), sent = new Map(current.pending); refresh();
    function failed(cause: unknown) {
      if (current.disposed) return;
      if (current.pending.get(key)?.serial === serial) current.pending.delete(key);
      refresh(); throw cause;
    }
    let request: Promise<boolean>;
    // No queue or awaited read: host Save may close the iframe immediately.
    try {request = astra.widget.setConfig(next);} catch (cause) {return failed(cause);}
    return request.then(() => {
      if (current.disposed) return;
      if (serial >= current.acknowledged) {current.host = {...next}; current.acknowledged = serial;}
      for (const [field, edit] of sent) {
        if (current.pending.get(field)?.serial === edit.serial) current.pending.delete(field);
      }
      refresh();
    }, failed);
  }
  async function increment() {
    if (state.current.busy || state.current.context.viewId) return;
    state.current.busy = true; setBusy(true);
    try {
      // Single-writer updates; get/set itself is not an atomic transaction.
      const current = Number(await astra.widget.getData('count') ?? 0);
      if (!Number.isFinite(current) || current < 0) throw new Error('Stored count is invalid.');
      const limit = Number(state.current.context.config.limit ?? 100);
      if (current >= limit) {if (!state.current.disposed) setCount(current); return;}
      const next = Math.min(current + 1, limit);
      await astra.widget.setData('count', String(next));
      if (!state.current.disposed) setCount(next);
    } finally {state.current.busy = false; if (!state.current.disposed) setBusy(false);}
  }
  const disabled = context.preview || !context.active;
  const feedback = <p role="alert">{error}</p>;
  if (context.viewId === 'settings') return <Section title="Instance settings">
    <SettingRow label="Title" htmlFor="title" control={<Input id="title"
      value={String(context.config.title ?? 'My counter')} disabled={disabled}
      onChange={value => void perform(() => config('title', value))} />} />
    <SettingRow label="Color" control={<Select value={String(context.config.color ?? 'default')}
      options={colors} disabled={disabled} onChange={value => void perform(() => config('color', value))} />} />
    <SettingRow label="Count limit" htmlFor="limit" control={<NumberInput id="limit"
      value={Number(context.config.limit ?? 100)} min={1} max={1000} step={1} disabled={disabled}
      onChange={value => void perform(() => config('limit', value))} />} />
    <p>Astra’s Save applies this draft; Cancel discards it.</p>{feedback}
  </Section>;
  return <div style={{display: 'flex', flexDirection: 'column', gap: 12}}>
    <strong>{String(context.config.title ?? 'My counter')}</strong>
    <output aria-live="polite" style={{fontSize: context.formatId === 'compact' ? 28 : 40,
      color: context.config.color === 'accent' ? 'var(--color-accent)' : undefined}}>{count}</output>
    {!context.viewId && <Button disabled={disabled || busy || count >= Number(context.config.limit ?? 100)} onClick={() => void perform(increment)}>Add one</Button>}
    {context.viewId === 'menu' && <Select value={String(context.config.color ?? 'default')}
      options={colors} disabled={disabled} onChange={value => void perform(() => config('color', value))} />}
    {(context.viewId === 'details' || context.formatId === 'list') && <p>
      Instance {context.instanceId} · {context.width} × {context.height} · params: {JSON.stringify(context.params ?? {})}
    </p>}
    <div style={{display: 'flex', gap: 8, flexWrap: 'wrap'}}>
      <Button disabled={disabled} onClick={event => void perform(() => astra.widget.openSurface('menu', {
        anchor: event.currentTarget, params: {source: context.viewId || context.formatId},
      }))}>Menu</Button>
      <Button disabled={disabled} onClick={() => void perform(() => astra.widget.openSurface('details', {
        params: {source: context.viewId || context.formatId},
      }))}>Details</Button>
      <Button disabled={disabled} onClick={() => void perform(async () => {
        const value = await astra.callBackend('ping', {});
        if (!state.current.disposed) setResult(JSON.stringify(value));
      })}>Backend</Button>
      {context.viewId && <Button disabled={disabled} onClick={() => void perform(() =>
        astra.widget.closeSurface(context.viewId))}>Close</Button>}
    </div><p aria-live="polite">{result}</p>{feedback}
  </div>;
}
const container = document.getElementById('app')!;
try {
  await astra.loadUi({apiVersion: 1});
  const root = mount(container, <App />);
  window.addEventListener('pagehide', () => root.unmount(), {once: true});
} catch (error) {container.textContent = 'Update Astra to use desktop widgets. ' + String(error);}
