// SPDX-License-Identifier: MPL-2.0
const container = document.getElementById('app');
try {
  const ui = await astra.loadUi({apiVersion: 1});
  const {h} = ui;
  const state = {mode:'default', name:'', enabled:true, result:'', dialog:false, popover:false};
  let root;
  function render() {
    const tree=h(ui.Section,{title:'Plugin settings'},
      h(ui.SettingRow,{label:'Mode',control:h(ui.Select,{value:state.mode,options:[{value:'default',label:'Default'},{value:'compact',label:'Compact'}],onChange:value=>{state.mode=value;render();}})}),
      h(ui.SettingRow,{label:'Name',htmlFor:'name',control:h(ui.Input,{id:'name',value:state.name,onChange:value=>{state.name=value;render();}})}),
      h(ui.SettingRow,{label:'Enabled',control:h(ui.Toggle,{ariaLabel:'Enabled',checked:state.enabled,onChange:value=>{state.enabled=value;render();}})}),
      h(ui.Button,{onClick:async()=>{try {state.result=JSON.stringify(await astra.callBackend('ping',state));}catch(error){state.result=error.message;}render();}},'Call backend'),
      h('p',{'aria-live':'polite'},state.result),
      h(ui.Tooltip,{content:'Shared iframe tooltip'},h(ui.Button,{onClick:()=>{state.dialog=true;render();}},'Open dialog')),
      h(ui.Popover,{open:state.popover,onOpenChange:value=>{state.popover=value;render();},trigger:h(ui.Button,{onClick:()=>{state.popover=!state.popover;render();}},'Open popover')},h(ui.Icon,{name:'info'}),' Shared popover'),
      h(ui.Modal,{open:state.dialog,onClose:()=>{state.dialog=false;render();},title:'Nested controls'},
        h(ui.SettingRow,{label:'Dialog mode',control:h(ui.Select,{value:state.mode,options:[{value:'default',label:'Default'},{value:'compact',label:'Compact'}],onChange:value=>{state.mode=value;render();}})}),
        h(ui.Input,{value:state.name,onChange:value=>{state.name=value;render();}}),
        h(ui.Button,{onClick:()=>{state.dialog=false;render();}},'Close dialog')));

    if(root) root.render(tree); else root=ui.mount(container,tree);
  }
  render();
  window.addEventListener('pagehide',()=>root.unmount(),{once:true});
} catch(error) { container.textContent='Update Astra to use this interface. '+error.message; }
