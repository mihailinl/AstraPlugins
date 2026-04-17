# Publicación de plugins

Todo lo necesario para convertir el código fuente en un paquete firmado y distribuible que los usuarios puedan instalar manualmente en Astra.

## El paquete `.astraplugin`

`.astraplugin` es un **archivo ZIP** con un diseño específico. El daemon valida el manifiesto, (opcionalmente) verifica la firma, extrae el contenido en su directorio de plugins y lanza `entry.command` con las credenciales.

```
<plugin-id>-<version>.astraplugin
├── plugin.toml                # Manifiesto
├── bin/                       # Binario compilado (solo Rust)
│   └── my_plugin.exe
├── dist/                      # JS empaquetado (solo TypeScript)
│   └── index.js
├── src/                       # Fuentes Python (solo Python)
│   ├── plugin.py
│   └── __init__.py
├── requirements.txt           # Dependencias Python (solo Python)
├── requirements.lock          # Dependencias Python resueltas por uv (solo Python)
├── ui/                        # Archivos UI personalizados (opcional)
├── locales/                   # Archivos JSON de i18n (opcional)
├── icon.png | icon.svg        # Branding opcional
├── README.md                  # Opcional
├── LICENSE                    # Opcional
├── SIGNATURE                  # Firma Ed25519 (si el paquete está firmado)
└── PUBKEY                     # Clave pública Ed25519 (si el paquete está firmado)
```

Cuando `astra-plugin build` produce un archivo:

1. Ejecuta el paso de build específico del lenguaje.
2. Copia el artefacto compilado al directorio esperado.
3. Reescribe `entry.command` para apuntar a la ruta dentro del paquete (solo Rust — las rutas en Python/TS dentro del archivo son estables).
4. Añade `ui/`, `locales/`, icono y documentos si existen junto a `plugin.toml`.
5. Si existe `~/.astra/plugin-keys/private.key`, firma cada entrada con Ed25519 y añade `SIGNATURE` y `PUBKEY` al archivo.

## Firmar

### Generar un par de claves

```bash
astra-plugin keygen
```

Salida:

- `~/.astra/plugin-keys/private.key` — semilla Ed25519 codificada en base64. **Manténgala en secreto.** Cualquiera que posea este archivo podrá firmar nuevas versiones de su plugin y los usuarios confiarán en ellas.
- `~/.astra/plugin-keys/public.key` — puede publicarla sin problema.

Añada `--force` para sobrescribir un par de claves existente (útil para rotación — pero invalida las relaciones de confianza ya establecidas).

### Firmar durante el build

No hay un comando de firma separado: una vez que existe el par de claves, `astra-plugin build` firma automáticamente. El archivo contiene:

- `SIGNATURE` — un manifiesto firmado de todos los demás archivos del paquete.
- `PUBKEY` — la clave pública usada. Los usuarios pueden compararla con un valor conocido bueno (su sitio web, su política de key pinning) antes de instalar.

Para publicar un build **sin firmar**, elimine la clave privada o compile en una máquina que no la tenga.

### Verificación de firmas

La verificación de firmas ocurre en el lado del daemon durante la instalación manual. El daemon expone el `PUBKEY` del paquete en la UI de plugins para que los usuarios puedan comparar huellas antes de pulsar "Instalar".

## Distribución

### Descarga directa

Publique el archivo `.astraplugin` desde su sitio web, GitHub Releases o cualquier servicio de hosting. Los usuarios lo descargan y lo arrastran a la página de plugins de Astra.

### Git + artefactos de release

Flujo típico de release:

1. Incremente `plugin.version` en `plugin.toml`.
2. Haga commit, etiquete (`git tag v0.2.0`) y push.
3. `astra-plugin validate` → `astra-plugin build -o dist/plugin-0.2.0.astraplugin`.
4. Suba el `.astraplugin` al release de GitHub correspondiente al tag.

Es amigable con CI porque `astra-plugin` es un único binario.

### Registry

Un registry central de plugins está planificado. Hasta que llegue, comparta plugins mediante URLs directas.

## Instalación manual (sideloading)

El daemon expone dos RPCs para instalar un `.astraplugin`:

- `SideloadPlugin(bytes)` — acepta el paquete a través de gRPC. Lo usa el selector de archivos de la UI de Astra.
- `ImportPluginFile(path)` — indica al daemon que lea el archivo desde el disco. Se usa cuando el usuario arrastra el archivo a la UI.

Ambos verifican la firma (si existe), validan el manifiesto, extraen en `~/.astra/plugins/<id>/` y lanzan el proceso.

Desinstalar un plugin detiene el proceso, elimina el directorio extraído y limpia el estado del plugin.

## Estrategia de actualización

- Incremente `plugin.version` en cada release.
- El daemon almacena las versiones instaladas y muestra una etiqueta "Actualización disponible" cuando el nuevo paquete tiene una SemVer mayor.
- ¿Cambios de configuración que rompen compatibilidad? Añada campos nuevos con valores por defecto en lugar de renombrar los existentes — el daemon conserva la configuración antigua durante las actualizaciones.

## Localización

Incluya un directorio `locales/` dentro de su paquete:

```
locales/
├── en.json
├── ru.json
├── uk.json
├── de.json
├── es.json
├── zh-CN.json
└── ja.json
```

Cada SDK tiene un helper `I18n` que lee estos archivos y degrada con elegancia ante claves desconocidas. El manifiesto traduce etiquetas de campos (`ActionType.MyAction`, `FieldLabel.X`) — mantenga los IDs del código estables y el texto visible en los archivos JSON.

## Lista de verificación antes del release

- [ ] `astra-plugin validate` pasa sin errores.
- [ ] `astra-plugin build` tiene éxito y produce un archivo de tamaño razonable.
- [ ] `plugin.toml` contiene `description`, `author` y `license`.
- [ ] El schema de `[config]`, si existe, tiene defaults sensatos para cada campo.
- [ ] El paquete se probó mediante sideloading en una instancia limpia del daemon.
- [ ] La huella del `PUBKEY` está documentada en algún lugar que los usuarios puedan verificar.
- [ ] `locales/` cubre todas las cadenas que el plugin muestra a los usuarios.
- [ ] `README.md` documenta lo que hace el plugin y cualquier requisito de runtime.
- [ ] Tiene un canal para contactar a los usuarios si necesita revocar una release comprometida.
