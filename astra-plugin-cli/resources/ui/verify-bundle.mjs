// SPDX-License-Identifier: GPL-3.0-or-later
import fs from 'node:fs';
import path from 'node:path';
export function verifyUiBundle(directory,contract) {
  if(!fs.existsSync(directory)) return 0;
  directory=path.resolve(directory);
  const allowed=new Set(Object.values(contract.modules).map(file=>contract.moduleBase+file));
  const parser=new Bun.Transpiler({loader:'js'});
  const modules=new Map();
  function walk(dir) {
    for(const entry of fs.readdirSync(dir,{withFileTypes:true})) {
      const file=path.join(dir,entry.name);
      if(entry.isDirectory()) {walk(file);continue;}
      if(!entry.isFile() || !/.(?:m?js)$/.test(entry.name)) continue;
      const source=fs.readFileSync(file,'utf8');
      modules.set(file,{source,imports:parser.scanImports(source),edges:new Set()});
    }
  }
  walk(directory);
  const active=new Set();
  for(const [file,module] of modules) {
    if(module.imports.some(item=>item.path.startsWith(contract.moduleBase) || Object.hasOwn(contract.modules,item.path))) active.add(file);
    for(const item of module.imports) {
      if(item.path.startsWith('.')) {
        const dependency=path.resolve(path.dirname(file),item.path);
        module.edges.add(dependency);
        modules.get(dependency)?.edges.add(file);
      }
    }
  }
  // Check the complete connected import graph, including parents of Kit helpers.
  const pending=[...active];
  while(pending.length) {
    for(const edge of modules.get(pending.pop())?.edges || []) {
      if(modules.has(edge) && !active.has(edge)) {active.add(edge);pending.push(edge);}
    }
  }
  for(const file of active) {
    const module=modules.get(file);
    for(const item of module.imports) {
      if(item.path.startsWith('./') || item.path.startsWith('../')) {
        const dependency=path.resolve(path.dirname(file),item.path);
        let ancestor=dependency;
        while(ancestor!==directory && ancestor.startsWith(directory+path.sep)) {
          if(fs.existsSync(ancestor) && fs.lstatSync(ancestor).isSymbolicLink()) throw new Error(file+': UI import symlink is not packaged');
          ancestor=path.dirname(ancestor);
        }
        if(/\.(?:m?js)$/.test(dependency) && !modules.has(dependency)) throw new Error(file+': imported JavaScript was not inspected or packaged: '+item.path);
        if(!dependency.startsWith(directory+path.sep) || !fs.existsSync(dependency) || !fs.realpathSync(dependency).startsWith(fs.realpathSync(directory)+path.sep)) throw new Error(file+': relative UI import escapes or is missing: '+item.path);
      } else if(!allowed.has(item.path)) throw new Error(file+': unsupported browser import '+item.path);
    }
    const executable=parser.transformSync(module.source);
    if(/__CLIENT_INTERNALS_DO_NOT_USE_OR_WARN_USERS_THEY_CANNOT_UPGRADE|react.transitional.element/.test(executable)) throw new Error(file+': contains a second React runtime');
  }
  return active.size;
}
