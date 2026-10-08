// SPDX-License-Identifier: MPL-2.0
import assert from 'node:assert/strict';
import {createRequire} from 'node:module';
import {test} from 'node:test';
const require=createRequire(import.meta.url);
const {plugin,Plugin,UiContrib,Field}=require('../dist/index.js');
const {Harness}=require('../dist/testing/index.js');
const {service}=require('../dist/proto-loader.js');
test('desktop descriptor survives the capability handler and protobuf serialization',async()=>{
  const desktopWidget={repeatable:true,formats:[{id:'list',label:'List',url:'index.html',defaultW:4,defaultH:3,minW:3,minH:2,maxW:8,maxH:6,minPixelWidth:220}],surfaces:[{id:'settings',url:'index.html',kind:'modal',width:480}],configFields:[Field.text('title','Title',{default:'Counter'})],settingsSurface:'settings'};
  const h=await Harness.create(plugin({ui:{contributions:[UiContrib.widget('counter','Counter',desktopWidget)]}})).start();
  const contribution=(await h.uiContributions())[0];assert.deepEqual(contribution.desktopWidget,desktopWidget);
  const response={contributions:[contribution]},method=service('PluginCapabilityService').service.GetUiContributions;
  const wire=method.responseDeserialize(method.responseSerialize(response));
  assert.equal(wire.contributions[0].desktopWidget.formats[0].maxW,8);
  assert.equal(wire.contributions[0].desktopWidget.configFields[0].defaultValue,'Counter');
});
test('contextual UI handlers receive each instance and fall back to legacy methods',async()=>{
  const h=await Harness.create(plugin({ui:{contributions:[],onCall:{legacy:()=>({legacy:true})},onWidgetCall:{ping:(_params,widget)=>({instance:widget?.instanceId,config:widget?.configJson})}}})).start();
  assert.deepEqual(JSON.parse((await h.callFromUi('legacy')).resultJson),{legacy:true});
  for(const instanceId of ['first','second']){
    const widget={widgetId:'counter',instanceId,formatId:'list',viewId:'',preview:false,active:true,width:400,height:300,configJson:JSON.stringify({title:instanceId})};
    const result=await h.callFromUi('ping',{},widget);
    assert.deepEqual(JSON.parse(result.resultJson),{instance:instanceId,config:widget.configJson});
  }
});
test('existing class handleUiCall overrides still dispatch',async()=>{
  class Legacy extends Plugin{async handleUiCall(method){return {method};}}
  const h=await Harness.create(new Legacy()).start();assert.equal(JSON.parse((await h.callFromUi('ping')).resultJson).method,'ping');
});
