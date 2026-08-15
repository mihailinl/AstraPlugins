> **Traducción.** Esta es una traducción. Si hay alguna discrepancia, [`docs/en`](../../en/reference/README.md) es la referencia autorizada. La página en inglés está GENERADA por `tools/docgen/gen.py` — esta traducción es una instantánea mantenida a mano, no otra copia generada.

# Referencia

Generada. Cada página de este directorio es una función del código
fuente de este repositorio, vuelta a renderizar por
`python3 tools/docgen/gen.py` y comprobada contra desviaciones en la CI
con el mismo comando más `--check`. Editar una a mano hace fallar el
build.

Ese es el punto: el nivel de referencia es la parte de la documentación
que nadie vuelve a leer contra la fuente, así que es la parte que no
debe depender de que alguien lo haga.

| Página | Qué responde | Derivada de |
|---|---|---|
| [`cli.md`](./cli.md) | `astra-plugin`: cada comando, argumento y flag | las definiciones `clap` del binario de la CLI |
| [`manifest.md`](./manifest.md) | `plugin.toml`: cada sección y campo | `astra-plugin-cli/vendor/astra-plugin-manifest` |
| [`protocol.md`](./protocol.md) | la superficie gRPC: servicios, RPC, streaming, permisos | `proto/plugin.proto` + `spec/hooks.yaml` |
| [`errors.md`](./errors.md) | la taxonomía de errores, en los tres SDK | el enum del proto + el módulo de errores de cada SDK |
| [`parity.md`](./parity.md) | qué hook está vinculado en qué SDK | `spec/hooks.yaml` |

## Lo que no está aquí

**Prosa.** Cualquier cosa que explique *por qué*, o te guíe a través de
algo, está escrita a mano y vive fuera de este directorio. Un generador
no tiene opiniones.

**Cualquier cosa sin verificar.** Una página aquí solo declara lo que su
generador pudo leer del código fuente. Cuando un hecho vive en el
daemon de Astra en lugar de en este repositorio — el permiso al que
está condicionado cada RPC del host, por ejemplo — la página dice qué
archivo del repositorio lo lleva y qué regla de paridad ancla ese
archivo al daemon.
</content>
