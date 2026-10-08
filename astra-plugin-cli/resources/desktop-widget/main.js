// SPDX-License-Identifier: MPL-2.0
// One transparent entrypoint; Astra owns the shell, surfaces and settings draft.
const container = document.getElementById('app');
try {
  const ui = await astra.loadUi({apiVersion: 1}), {h} = ui;
  let context = await astra.widget.getContext();
  let count = context.preview ? 3 : Number(await astra.widget.getData('count') ?? 0);
  let hostConfig = {...context.config}, version = 0, acknowledged = 0;
  let error = '', result = '', root, disposed = false, busy = false;
  const pending = new Map();
  const colors = [{value: 'default', label: 'Default'}, {value: 'accent', label: 'Accent'}];
  function desired() {
    const merged = {...hostConfig};
    for (const [key, edit] of pending) merged[key] = edit.value;
    return merged;
  }
  async function perform(action) {
    if (context.preview || !context.active || disposed) return;
    error = '';
    try {await action();} catch (cause) {error = String(cause?.message ?? cause);}
    render();
  }
  function config(key, value) {
    if (context.preview || !context.active || disposed) return;
    if (key === 'limit' && (!Number.isFinite(value) || value < 1 || value > 1000)) {
      throw new Error('Count limit must be a finite number from 1 to 1000.');
    }
    const serial = ++version;
    pending.set(key, {value, serial});
    const next = desired(), sent = new Map(pending);
    context = {...context, config: next}; render();
    const failed = cause => {
      if (disposed) return;
      if (pending.get(key)?.serial === serial) pending.delete(key);
      context = {...context, config: desired()}; throw cause;
    };
    let request;
    // Send immediately: Save can close the custom editor in this input turn.
    try {request = astra.widget.setConfig(next);} catch (cause) {return failed(cause);}
    return Promise.resolve(request).then(() => {
      if (disposed) return;
      if (serial >= acknowledged) {hostConfig = {...next}; acknowledged = serial;}
      for (const [field, edit] of sent) {
        if (pending.get(field)?.serial === edit.serial) pending.delete(field);
      }
      context = {...context, config: desired()};
    }, failed);
  }
  async function increment() {
    if (busy || context.viewId) return;
    busy = true; render();
    try {
      // A single writer serializes this example's updates; get/set is not a transaction.
      const current = Number(await astra.widget.getData('count') ?? 0);
      if (!Number.isFinite(current) || current < 0) throw new Error('Stored count is invalid.');
      const limit = Number(context.config.limit ?? 100);
      if (current >= limit) {count = current; return;}
      const next = Math.min(current + 1, limit);
      await astra.widget.setData('count', String(next)); count = next;
    } finally {busy = false;}
  }
  function render() {
    if (disposed) return;
    const disabled = context.preview || !context.active;
    const change = key => value => void perform(() => config(key, value));
    const controls = context.viewId === 'settings'
      ? h(ui.Section, {title: 'Instance settings'},
          h(ui.SettingRow, {label: 'Title', htmlFor: 'title', control: h(ui.Input, {
            id: 'title', value: String(context.config.title ?? 'My counter'), disabled, onChange: change('title'),
          })}),
          h(ui.SettingRow, {label: 'Color', control: h(ui.Select, {
            value: String(context.config.color ?? 'default'), options: colors, disabled, onChange: change('color'),
          })}),
          h(ui.SettingRow, {label: 'Count limit', htmlFor: 'limit', control: h(ui.NumberInput, {
            id: 'limit', value: Number(context.config.limit ?? 100), min: 1, max: 1000, step: 1,
            disabled, onChange: change('limit'),
          })}),
          h('p', null, 'Astra’s Save applies this draft; Cancel discards it.'))
      : h('div', {style: {display: 'flex', flexDirection: 'column', gap: '12px'}},
          h('strong', null, String(context.config.title ?? 'My counter')),
          h('output', {'aria-live': 'polite', style: {fontSize: context.formatId === 'compact' ? '28px' : '40px',
            color: context.config.color === 'accent' ? 'var(--color-accent)' : undefined}}, String(count)),
          !context.viewId ? h(ui.Button, {disabled: disabled || busy || count >= Number(context.config.limit ?? 100), onClick: () => void perform(increment)}, 'Add one') : null,
          context.viewId === 'menu' ? h(ui.Select, {value: String(context.config.color ?? 'default'),
            options: colors, disabled, onChange: change('color')}) : null,
          context.viewId === 'details' || context.formatId === 'list'
            ? h('p', null, 'Instance ' + context.instanceId + ' · ' + context.width + ' × ' + context.height
              + ' · source: ' + (context.params?.source ?? 'card')) : null,
          h('div', {style: {display: 'flex', gap: '8px', flexWrap: 'wrap'}},
            h(ui.Button, {disabled, onClick: event => void perform(() => astra.widget.openSurface('menu', {
              anchor: event.currentTarget, params: {source: context.viewId || context.formatId},
            }))}, 'Menu'),
            h(ui.Button, {disabled, onClick: () => void perform(() => astra.widget.openSurface('details', {
              params: {source: context.viewId || context.formatId},
            }))}, 'Details'),
            h(ui.Button, {disabled, onClick: () => void perform(async () => {
              result = JSON.stringify(await astra.callBackend('ping', {}));
            })}, 'Backend'),
            context.viewId ? h(ui.Button, {disabled, onClick: () => void perform(() =>
              astra.widget.closeSurface(context.viewId))}, 'Close') : null),
          h('p', {'aria-live': 'polite'}, result));
    const tree = h('div', null, controls, h('p', {role: 'alert'}, error));
    if (root) root.render(tree); else root = ui.mount(container, tree);
  }
  const stopContext = astra.widget.onContextChange(next => {
    hostConfig = {...next.config}; context = {...next, config: desired()}; render();
  });
  const stopData = astra.widget.onDataChange(({key, value}) => {
    if (key === 'count' && !context.preview) {count = Number(value ?? 0); render();}
  });
  render();
  window.addEventListener('pagehide', () => {
    disposed = true; stopContext(); stopData(); root.unmount();
  }, {once: true});
} catch (error) {container.textContent = 'Update Astra to use desktop widgets. ' + String(error);}
