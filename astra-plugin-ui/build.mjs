// SPDX-License-Identifier: MPL-2.0
import contract from "./contract.json" with { type: "json" };
export const astraUiPlugin = { name: "astra-ui-host", setup(build) {
  build.onResolve({ filter: /^(?:@astra\/plugin-ui|react(?:-dom)?(?:\/.*)?)$/ }, ({path}) => {
    const module = contract.modules[path];
    if (!module) throw new Error("Unsupported Astra UI import: " + path);
    return { path: module, namespace: "astra-ui-host" };
  });
  // Bun 1.3.4 retains bare specifiers with external:true remapping and emits
  // undefined namespace bindings for virtual export-star shims. Explicit
  // named exports are generated from the actual host modules instead.
  build.onLoad({filter: /.*/, namespace: "astra-ui-host"}, ({path}) => ({
    loader: "js", contents: "export {" + contract.moduleExports[path].join(",") + "} from " + JSON.stringify(contract.moduleBase + path) + ";\n",
  }));
} };
export async function buildUi(entrypoint, outdir) {
  const result = await Bun.build({entrypoints:[entrypoint], outdir, target:"browser", format:"esm", minify:true,
    jsx: {runtime:"automatic", development:false}, plugins:[astraUiPlugin]});
  if (!result.success) throw new Error(result.logs.join("\n"));
  return result;
}
