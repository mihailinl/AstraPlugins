// SPDX-License-Identifier: GPL-3.0-or-later
// Execute the shipped vanilla scaffold entrypoint against a controlled bridge.
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {test} from 'node:test';
const source = readFileSync(new URL('../astra-plugin-cli/resources/desktop-widget/main.js', import.meta.url), 'utf8');
let run = 0;
const tick = async () => {await Promise.resolve(); await Promise.resolve(); await Promise.resolve();};
function find(tree, predicate) {
  if (!tree || typeof tree !== 'object') return;
  if (predicate(tree)) return tree;
  const control = find(tree.props?.control, predicate); if (control) return control;
  for (const child of tree.children ?? []) {const match = find(child, predicate); if (match) return match;}
}
async function session(viewId = 'settings', preview = false, config = {}) {
  const previous = {astra: globalThis.astra, document: globalThis.document, window: globalThis.window};
  let tree, onContext, teardown, renders = 0, unsubscribed = 0, unmounted = 0, reads = 0;
  const requests = [], operations = [];
  const context = {widgetId: 'counter', instanceId: 'one', formatId: 'compact', viewId,
    preview, active: !preview, width: 240, height: 180,
    config: {title: 'Original', color: 'default', limit: 100, extra: 'preserve', ...config}};
  const ui = {h: (component, props, ...children) => ({component, props: props ?? {}, children}),
    mount: (_container, initial) => {tree = initial; return {
      render: next => {tree = next; renders++;}, unmount: () => unmounted++,
    };}};
  for (const name of ['Section', 'SettingRow', 'Input', 'NumberInput', 'Select', 'Button']) ui[name] = name;
  globalThis.document = {getElementById: () => ({textContent: ''})};
  globalThis.window = {addEventListener: (_name, callback) => {teardown = callback;}};
  const record = name => (...args) => {operations.push({name, args}); return Promise.resolve(true);};
  globalThis.astra = {loadUi: async () => ui, callBackend: record('backend'), widget: {
    getContext: async () => context, getData: async () => {reads++; return '5';},
    setConfig: snapshot => new Promise((resolve, reject) => requests.push({snapshot, resolve, reject})),
    setData: record('data'), openSurface: record('open'), closeSurface: record('close'),
    onContextChange: callback => {onContext = callback; return () => unsubscribed++;},
    onDataChange: () => () => unsubscribed++,
  }};
  await import('data:text/javascript;base64,' + Buffer.from(source).toString('base64') + '#run=' + run++);
  let closed = false;
  return {requests, operations, reads: () => reads,
    control: id => find(tree, node => node.props.id === id),
    alert: () => find(tree, node => node.props.role === 'alert'),
    find: predicate => find(tree, predicate),
    context: config => onContext({...context, config}),
    stats: () => ({renders, unsubscribed, unmounted}),
    close: () => {if (!closed) {closed = true; teardown();}},
    cleanup: () => {if (!closed) teardown(); Object.assign(globalThis, previous);},
  };
}
test('custom settings sends immediately and rebases pending fields across stale acknowledgements', async () => {
  const current = await session();
  try {
    current.control('title').props.onChange('Changed');
    assert.equal(current.requests.length, 1, 'Save can happen before any promise settles');
    current.control('limit').props.onChange(250);
    assert.equal(current.requests.length, 2, 'draft writes are not queued');
    current.context({...current.requests[0].snapshot, color: 'accent'});
    assert.equal(current.control('limit').props.value, 250);
    current.control('title').props.onChange('Latest');
    assert.deepEqual(current.requests[2].snapshot, {title: 'Latest', color: 'accent', limit: 250, extra: 'preserve'});
    current.requests[0].reject(new Error('Earlier write failed')); await tick();
    assert.equal(current.control('title').props.value, 'Latest');
    assert.match(current.alert().children[0], /Earlier write failed/);
    current.close(); const before = current.stats().renders;
    for (const request of current.requests.slice(1)) request.resolve(true);
    await tick(); assert.equal(current.stats().renders, before);
    assert.equal(current.stats().unsubscribed, 2); assert.equal(current.stats().unmounted, 1);
  } finally {current.cleanup();}
});
test('custom settings rejects nonfinite/out-of-range values without sending a replacement', async () => {
  const current = await session();
  try {
    for (const value of [NaN, Infinity, -1, 0, 1001]) {
      current.control('limit').props.onChange(value); await tick();
      assert.equal(current.requests.length, 0);
      assert.match(current.alert().children[0], /finite number from 1 to 1000/);
    }
  } finally {current.cleanup();}
});
test('preview never reads instance data, writes config/data, opens surfaces or calls backend', async () => {
  for (const viewId of ['', 'menu', 'details', 'settings']) {
    const current = await session(viewId, true);
    try {
      const visit = async node => {
        if (!node || typeof node !== 'object') return;
        if (node.component === 'Button') {assert.equal(node.props.disabled, true); await node.props.onClick?.({currentTarget: {}});}
        if (node.props.onChange) {assert.equal(node.props.disabled, true); await node.props.onChange('sample');}
        await visit(node.props.control);
        for (const child of node.children ?? []) await visit(child);
      };
      await visit(current.find(() => true)); await tick();
      assert.equal(current.reads(), 0); assert.equal(current.requests.length, 0);
      assert.deepEqual(current.operations, []);
    } finally {current.cleanup();}
  }
});
test('only the placed card offers count mutation; surfaces share reads', async () => {
  for (const viewId of ['', 'menu', 'details', 'settings']) {
    const current = await session(viewId);
    try {
      const add = current.find(node => node.component === 'Button' && node.children[0] === 'Add one');
      assert.equal(Boolean(add), viewId === '');
      assert.equal(current.reads(), 1);
    } finally {current.cleanup();}
  }
});

test('lowering a limit preserves existing count, even when a disabled Add callback is forced', async () => {
  const current = await session('', false, {limit: 1});
  try {
    const add = current.find(node => node.component === 'Button' && node.children[0] === 'Add one');
    assert.equal(add.props.disabled, true);
    await add.props.onClick(); await tick();
    assert.equal(current.reads(), 2, 'callback rechecks the actual persisted count');
    assert.deepEqual(current.operations.filter(operation => operation.name === 'data'), [], 'stored count 5 is retained');
    assert.equal(current.find(node => node.component === 'output').children[0], '5');
  } finally {current.cleanup();}
});
