// SPDX-License-Identifier: MPL-2.0
import {useState} from 'react';
import {mount, Section, SettingRow, Select, Input, Toggle, Button, Modal, Popover, Tooltip, Icon} from '@astra/plugin-ui';
declare const astra: {loadUi(options:{apiVersion:1}):Promise<unknown>;callBackend(method:string,params:unknown):Promise<unknown>};
function App() {
  const [mode,setMode]=useState('default');
  const [name,setName]=useState('');
  const [enabled,setEnabled]=useState(true);
  const [result,setResult]=useState('');
  const [dialog,setDialog]=useState(false);
  const [popover,setPopover]=useState(false);
  return <Section title="Plugin settings">
    <SettingRow label="Mode" control={<Select value={mode} onChange={setMode} options={[{value:'default',label:'Default'},{value:'compact',label:'Compact'}]}/>}/>
    <SettingRow label="Name" htmlFor="name" control={<Input id="name" value={name} onChange={setName}/>}/>
    <SettingRow label="Enabled" control={<Toggle ariaLabel="Enabled" checked={enabled} onChange={setEnabled}/>}/>
    <Button onClick={async()=>{try {setResult(JSON.stringify(await astra.callBackend('ping',{mode,name,enabled})));}catch(error){setResult(String(error));}}}>Call backend</Button>
    <p aria-live="polite">{result}</p>
    <Tooltip content="Shared iframe tooltip"><Button onClick={()=>setDialog(true)}>Open dialog</Button></Tooltip>
    <Popover open={popover} onOpenChange={setPopover} trigger={<Button onClick={()=>setPopover(!popover)}>Open popover</Button>}><Icon name="info"/> Shared popover</Popover>
    <Modal open={dialog} onClose={()=>setDialog(false)} title="Nested controls">
      <SettingRow label="Dialog mode" control={<Select value={mode} onChange={setMode} options={[{value:'default',label:'Default'},{value:'compact',label:'Compact'}]}/>}/>
      <Input value={name} onChange={setName}/>
      <Button onClick={()=>setDialog(false)}>Close dialog</Button>
    </Modal>
  </Section>;
}
const container=document.getElementById('app')!;
try {await astra.loadUi({apiVersion:1});const root=mount(container,<App/>);window.addEventListener('pagehide',()=>root.unmount(),{once:true});}
catch(error) {container.textContent='Update Astra to use this interface. '+String(error);}
