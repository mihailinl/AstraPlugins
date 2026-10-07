// SPDX-License-Identifier: MPL-2.0
import {useState} from 'react';
import {mount, Section, SettingRow, Select, Input, Toggle, Button} from '@astra/plugin-ui';
declare const astra: {loadUi(options:{apiVersion:1}):Promise<unknown>;callBackend(method:string,params:unknown):Promise<unknown>};
function App() {
  const [mode,setMode]=useState('default');
  const [name,setName]=useState('');
  const [enabled,setEnabled]=useState(true);
  const [result,setResult]=useState('');
  return <Section title="Plugin settings">
    <SettingRow label="Mode" control={<Select value={mode} onChange={setMode} options={[{value:'default',label:'Default'},{value:'compact',label:'Compact'}]}/>}/>
    <SettingRow label="Name" htmlFor="name" control={<Input id="name" value={name} onChange={setName}/>}/>
    <SettingRow label="Enabled" control={<Toggle ariaLabel="Enabled" checked={enabled} onChange={setEnabled}/>}/>
    <Button onClick={async()=>{try {setResult(JSON.stringify(await astra.callBackend('ping',{mode,name,enabled})));}catch(error){setResult(String(error));}}}>Call backend</Button>
    <p aria-live="polite">{result}</p>
  </Section>;
}
const container=document.getElementById('app')!;
try {await astra.loadUi({apiVersion:1});const root=mount(container,<App/>);window.addEventListener('pagehide',()=>root.unmount(),{once:true});}
catch(error) {container.textContent='Update Astra to use this interface. '+String(error);}
