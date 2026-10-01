// SPDX-License-Identifier: GPL-3.0-or-later
import {test,expect} from 'bun:test';
import fs from 'node:fs';import path from 'node:path';import os from 'node:os';
import {buildUi} from '../astra-plugin-ui/build.mjs';
import {verifyUiBundle} from '../astra-plugin-cli/resources/ui/verify-bundle.mjs';
import contract from '../astra-plugin-ui/contract.json' with {type:'json'};
test('TSX resolves React and UI to installed host modules; actual bundle contains no React copy',async()=>{
  const dir=fs.mkdtempSync(path.join(os.tmpdir(),'astra-ui-kit-'));
  try {
    const entry=path.join(dir,'App.tsx');
    fs.writeFileSync(entry,"import {useState} from 'react';import {Button} from '@astra/plugin-ui';import {createRoot} from 'react-dom/client';export const renderer=createRoot;export const App=()=>{const [n,set]=useState(0);return <Button onClick={()=>set(n+1)}>{n}</Button>};");
    const first=await buildUi(entry,path.join(dir,'out'));
    expect(verifyUiBundle(path.join(dir,'out'),contract)).toBe(1);
    const text=await first.outputs.find(file=>file.path.endsWith('.js')).text();
    expect(text).toContain(contract.moduleBase+'react.js');
    expect(text).toContain(contract.moduleBase+'jsx-runtime.js');
    expect(text).toContain(contract.moduleBase+'index.js');
    const stubs={
      'react.js':'export function useState(value){return [value,()=>{}]} export default {useState};',
      'react-dom-client.js':'export function createRoot(){}',
      'index.js':'export function Button(props){return props}',
      'jsx-runtime.js':'export function jsx(type,props){return {type,props}};export {jsx as jsxs};',
      'jsx-dev-runtime.js':'export function jsxDEV(type,props){return {type,props}};',
    };
    let executable=text;
    for(const [file,source] of Object.entries(stubs))executable=executable.replaceAll(contract.moduleBase+file,'data:text/javascript,'+encodeURIComponent(source));
    const module=await import('data:text/javascript,'+encodeURIComponent(executable));
    expect(module.App().props.children).toBe(0);
    expect(typeof module.renderer).toBe('function');
    fs.writeFileSync(path.join(dir,'out','chunk.js'),'import x from "https://example.com/react.js";console.log(x);');
    fs.appendFileSync(path.join(dir,'out','App.js'),'\nimport "./chunk.js";');
    expect(()=>verifyUiBundle(path.join(dir,'out'),contract)).toThrow('unsupported browser import');
    fs.unlinkSync(path.join(dir,'out','chunk.js'));
    fs.writeFileSync(path.join(dir,'out','App.js'),text);
    fs.writeFileSync(path.join(dir,'out','malicious.js'),'import x from '+JSON.stringify(contract.moduleBase+'index.js')+';import y from "https://example.com/react.js";console.log(x,y);');
    expect(()=>verifyUiBundle(path.join(dir,'out'),contract)).toThrow('unsupported browser import');
    fs.unlinkSync(path.join(dir,'out','malicious.js'));
    fs.mkdirSync(path.join(dir,'out','real'));
    fs.writeFileSync(path.join(dir,'out','real','chunk.js'),'import x from "https://example.com/react.js";console.log(x);');
    fs.symlinkSync(path.join(dir,'out','real'),path.join(dir,'out','linked'),process.platform==='win32'?'junction':'dir');
    fs.appendFileSync(path.join(dir,'out','App.js'),'\nimport "./linked/chunk.js";');
    expect(()=>verifyUiBundle(path.join(dir,'out'),contract)).toThrow();
  }finally{fs.rmSync(dir,{recursive:true,force:true});}
});
