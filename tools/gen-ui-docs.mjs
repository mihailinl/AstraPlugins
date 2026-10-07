// SPDX-License-Identifier: GPL-3.0-or-later
import fs from 'node:fs';import path from 'node:path';import {fileURLToPath} from 'node:url';
const root=path.resolve(path.dirname(fileURLToPath(import.meta.url)),'..');
const contract=JSON.parse(fs.readFileSync(path.join(root,'astra-plugin-ui/contract.json')));
const source=fs.readFileSync(path.join(root,'docs/tools/locales.py'),'utf8');
const codes=source.match(/LOCALES = \(([^)]+)\)/)[1].match(/[a-z]{2}/g);
for(const code of codes) {
  const text=fs.readFileSync(path.join(root,'tools/ui-docs',code+'.md'),'utf8').replaceAll('{{API_VERSION}}',String(contract.apiVersion)).replaceAll('{{MIN_ASTRA_VERSION}}',contract.minimumAstraVersion).replaceAll('{{COMPONENTS}}',contract.components.map(name=>'\x60'+name+'\x60').join(', '));
  const target=path.join(root,'docs',code,'4-sdk/ui-kit.md');
  if(process.argv.includes('--check')) {if(fs.readFileSync(target,'utf8')!==text)throw new Error('UI documentation drift '+code);} else fs.writeFileSync(target,text);
}
console.log('Generated UI contract docs: '+codes.join(', '));
