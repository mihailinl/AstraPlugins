> **Traducción.** Esta es una traducción. Si hay alguna discrepancia, [`docs/en`](../../en/spec/bundle-v2.md) es la referencia autorizada.

# Formato de paquete `.astraplugin`, versión 2 — especificación normativa

**Estado:** normativo. Este documento define los bytes. Está escrito
para que un tercero que nunca haya visto este repositorio pueda
implementar un verificador solo a partir de él y obtener el mismo
veredicto que nosotros en cada archivo de
[`testdata/bundles/`](../../../testdata/bundles/README.md).

**String de schema:** `astra.bundle/2`
**Extensión de archivo:** `.astraplugin`
**Tipo de medio:** ninguno registrado; se sirve como
`application/octet-stream`.

Las palabras de requisito — **MUST**, **MUST NOT**, **SHOULD**,
**MAY** — siguen RFC 2119. "Rechazar" significa: rechazar el paquete
entero, no extraer, no recurrir a ningún formato anterior. No hay
aceptación parcial en este formato.

---

## 0. Qué es este formato y qué no es

Un paquete v2 es un archivo ZIP cuya **primera entrada es un manifiesto
que nombra y calcula el digest de cada otra entrada.** Esa es toda la
idea. Compra una cosa que un paquete v1 (un ZIP con un `plugin.toml`
dentro) no podía comprar: un lector se entera de lo que el archivo
*tiene permitido* contener antes de haber confiado en la propia
estructura del archivo, y cada archivo que termina en disco se
comprueba contra esa lista.

Tres cosas que este formato deliberadamente **no** hace, indicadas
aquí para que ningún lector las infiera de la presencia de digests:

* **No lleva ninguna autenticidad propia.** Nada dentro de un paquete
  v2 demuestra quién lo produjo. La autenticidad viene de fuera del
  archivo: una attestation de compilación de GitHub sobre
  `sha256(archivo completo)`, y un índice de registro firmado que fija
  el mismo número ([`registry-index.md`](registry-index.md)). El par
  heredado dentro del ZIP `SIGNATURE`/`PUBKEY` (§11) *no* es una
  excepción — está en retirada y nunca es una señal de confianza.
* **No dice nada sobre lo que el plugin puede hacer en tiempo de
  ejecución.** Eso es [`permissions.md`](permissions.md).
* **No es un límite de sandbox.** Un plugin instalado es un proceso
  nativo que se ejecuta con todos los privilegios del usuario.
  Verificar un paquete te dice que los bytes son los bytes que el
  autor publicó; no restringe lo que esos bytes hacen una vez que se
  ejecutan.

## 1. Conformidad, y qué implementación es normativa

Tres programas leen este formato:

| | implementación | rol |
|---|---|---|
| **CLI** | `astra-plugin-cli/src/bundle.rs` (`BundleBuilder`, `Bundle::open`) | escribe paquetes; `astra-plugin verify` los relee |
| **daemon** | `Astra/astra-rs/astra-daemon/src/plugins/bundle.rs` (`inspect`, `BundleManifest::check_structure`) + `ops/install_plugin.rs` (`extract_archive`) | decide si los bytes de un desconocido se extraen al disco de un usuario |
| **registro** | `astra-registry/bot/lib/bundle.mjs` (`inspectBundle`) | decide si se publica un listado |

**Este documento es normativo; ninguna implementación lo es.** Donde
una implementación discrepe de este texto, la implementación tiene un
bug. Donde dos implementaciones discrepen entre sí, la discrepancia se
registra como una divergencia con nombre en
`testdata/bundles/vectors.json` y se reproduce en el §14 — el campo
`verdict` ahí es la respuesta correcta y el campo `expect` es lo que
hace cada programa hoy.

Consecuencia para una cuarta implementación: **implementa el §13, no
ninguno de los tres programas.** Un verificador que reprodujera el
daemon exactamente heredaría la divergencia F2; uno que reprodujera el
registro heredaría la F3.

## 2. El contenedor

* Un paquete **DEBE** ser un archivo ZIP legible por un lector
  convencional: cabeceras de archivo local desde el offset 0, un
  directorio central, un registro de fin de directorio central.
* **ZIP64 NO DEBE usarse para la entrada cero.** Un `MANIFEST.json`
  cuya cabecera local declare el centinela de tamaño ZIP64
  `0xFFFFFFFF` se rechaza (§4). Ninguna otra entrada tiene una
  restricción ZIP64 explícita; un manifiesto tan grande no es un
  manifiesto.
* Las entradas son **solo archivos**. Una entrada de directorio se
  rechaza (§6.5): los directorios están implícitos en las rutas y no
  pueden llevar un digest.
* **La entrada cero DEBE ser `MANIFEST.json`, almacenada (método de
  compresión 0).** Cualquier otra entrada **PUEDE** usar el método 0
  (stored) o el método 8 (deflate). La CLI empaqueta todo salvo el
  manifiesto con deflate en nivel 6; los vectores en
  `testdata/bundles/` están todos stored. Ambos son conformes.
* Orden: `MANIFEST.json` primero; el par heredado `SIGNATURE`/`PUBKEY`,
  si está presente, al final y en ese orden (§11); todo lo demás en
  medio. Los productores **DEBERÍAN** escribir la parte central en
  orden byte-lexicográfico de la ruta — la CLI lo hace, porque sus
  entradas viven en un `BTreeMap` — pero un verificador **NO DEBE
  EXIGIRLO**. El array `files` *del manifiesto* está ordenado y ese
  requisito se aplica (§7.4); el propio orden del archivo no.
* Las marcas de tiempo no llevan significado. La CLI sella cada entrada
  con `1980-01-01T00:00:00` (lo más temprano que puede expresar una
  marca de tiempo DOS) para que dos compilaciones de las mismas
  entradas produzcan los mismos bytes. Un verificador **NO DEBE** leer
  una marca de tiempo.

## 3. Los dos digests

Existen exactamente dos construcciones de digest en este formato.
Ambas son SHA-256, ambas se renderizan como **64 caracteres hex en
minúsculas**, y ninguna se compara nunca sin distinguir mayúsculas.

### 3.1 Digest del artefacto

```
artifact_digest = SHA256(the entire .astraplugin file, byte for byte)
```

Sin canonicalización, sin recorrido de entradas, sin exclusiones. Este
es el número que aparece en exactamente tres lugares, y es el mismo
número en los tres:

1. el sujeto de la attestation de compilación de GitHub,
2. `artifacts.<platform>.sha256` en el índice de registro firmado,
3. lo que el daemon transmite y hashea antes siquiera de abrir el
   archivo.

Se escribe desnudo (sin prefijo `sha256:`), porque cada lugar donde
aparece ya está tipado.

### 3.2 Digest del manifiesto — y por qué está separado por dominio

```
manifest_digest = SHA256( "astra.bundle/2" ‖ 0x00 ‖ MANIFEST.json bytes )
```

El prefijo son los 14 bytes ASCII `astra.bundle/2` seguidos de un byte
`0x00` — 15 bytes en total — inmediatamente seguidos de los bytes
*almacenados* de la entrada cero, exactamente como están en el
archivo, sin reserialización, sin normalización de espacios en blanco
y sin ajuste de salto de línea final.

**Por qué existe el prefijo.** Sin él la construcción es
`SHA256(algunos bytes)` — que es precisamente la forma de cada
`files[].sha256` en el mismo documento. Los dos serían strings hex de
64 caracteres indistinguibles viajando por los mismos registros, y un
valor tomado de un contexto verificaría en el otro. El prefijo hace
que el digest del manifiesto sea una función distinta de los mismos
bytes.

**Ejemplo resuelto** (vector `ok-minimal`, reproducible con
`testdata/bundles/handcheck.sh ok-minimal`, que solo usa `dd`, `od`,
`printf`, `cat` y `sha256sum`):

```
sha256(manifest bytes)                    2e16024e4557332a2a404a89a94b124807e0b4741046e29fc3f6b94ea1b69682
sha256("astra.bundle/2\0" ‖ manifest)     8e88f82cc6dbb9c253e3a4409a03f763668ca1a46439f994e2a45a6da23ccaf4
sha256(whole file)                        ac3d49a2fc2b7408d5b3c805ec91541510c272547a16e3bc7a30f269ba801aed
```

Una implementación que produce el primer valor donde se espera el
segundo se ha olvidado del prefijo. `vectors.json` registra ambos
números (`manifest_sha256` y `manifest_digest`) para cada vector, así
que esto es una comprobación de una línea, y los dos **nunca** son
iguales en ningún manifiesto real.

### 3.3 La construcción retirada, y la colisión que la retiró

Antes de v2, un paquete se autenticaba mediante una `SIGNATURE` dentro
del ZIP sobre

```
legacy_digest = SHA256( name₀ ‖ content₀ ‖ name₁ ‖ content₁ ‖ … )
```

en orden de índice ZIP, saltándose `SIGNATURE` y `PUBKEY` mismos. Sin
delimitadores, sin prefijos de longitud, sin conteo de entradas, sin
separador de dominio. Esa construcción es **ambigua**, y la ambigüedad
está en este repositorio como dos archivos congelados:

| vector | el archivo contiene | aporta |
|---|---|---|
| `collision-a-bc` | entrada `a`, contenido `bc` | `a` ‖ `bc` = `abc` |
| `collision-ab-c` | entrada `ab`, contenido `c` | `ab` ‖ `c` = `abc` |

Los dos archivos llevan **`MANIFEST.json` idéntico byte a byte** y por
tanto el mismo `manifest_digest`; sus digests de artefacto difieren; y
sus digests heredados son un solo número:

```
legacy_concat_sha256   0c0e28712aad8b042598cfb95b52d201b955b4c4942e87680404aa446f96e817   (both)
```

Una sola `SIGNATURE` autentica ambos archivos, y un verificador que
use ese esquema no puede saber cuál de los dos tiene en las manos.

Bajo v2 están separados, y hacen falta **ambas direcciones** de la
comprobación de exhaustividad para lograrlo (§7.1): en
`collision-ab-c`, `ab` es una entrada del archivo que ninguna línea
del manifiesto cubre, *y* `a` es una línea del manifiesto que ninguna
entrada del archivo satisface. Un verificador que solo comprobara
"listado ⇒ presente" lo aceptaría.

`legacy_concat_sha256` está registrado en `vectors.json` solo para
este propósito. Nada en este proyecto debería calcularlo jamás para
otra cosa.

## 4. Entrada cero, byte a byte

Un lector conforme **DEBE** poder obtener `MANIFEST.json` de un
prefijo del archivo, sin inflar nada y sin leer el directorio central.
Esta es la propiedad que le permite a un lector conocer el contenido
permitido del archivo antes de haber confiado en estructura controlada
por un atacante. Las tres implementaciones hacen exactamente esto
(`manifest_from_local_header` en la CLI y el daemon,
`manifestBytesFromLocalHeader` en el registro).

Lee la cabecera de archivo local en el offset 0. Todos los campos
multi-byte son little-endian.

| offset | tamaño | campo | requisito |
|---|---|---|---|
| 0 | 4 | firma | **DEBE** ser `0x04034B50`, si no rechazar: no es un ZIP |
| 6 | 2 | flags de propósito general | el bit 0 (cifrado) **DEBE** ser 0; el bit 3 (data descriptor) **DEBE** ser 0 |
| 8 | 2 | método de compresión | **DEBE** ser 0 (stored) |
| 18 | 4 | tamaño comprimido | **NO DEBE** ser `0xFFFFFFFF` (centinela ZIP64); **DEBE** ser ≤ 4 MiB |
| 26 | 2 | longitud del nombre de archivo `n` | — |
| 28 | 2 | longitud del campo extra `e` | — |
| 30 | `n` | nombre de archivo | **DEBE** ser exactamente los 13 bytes `MANIFEST.json` |
| 30+`n`+`e` | tamaño | los bytes del manifiesto | — |

**Ordena las quejas como lo hacen las implementaciones:** comprueba el
*nombre* antes que nada. Un archivo cuya entrada cero es otro archivo
tropezará con cualquiera de las comprobaciones de cabecera que ese
archivo falle, y reportar *eso* manda al lector a buscar un problema
con un manifiesto que no tiene.

Rechazos que esto produce, con sus vectores:

* la entrada cero no es `MANIFEST.json` → `manifest-not-first`.
* la entrada cero está comprimida → `manifest-compressed`.
* el tamaño se pasa del final del archivo → paquete truncado.

**Un paquete que contenga un `MANIFEST.json` en cualquier lugar NO
DEBE leerse como un paquete pre-v2.** Si el manifiesto está presente
pero no es la entrada cero, la respuesta es un rechazo, nunca un
retroceso a las reglas más débiles. De otro modo, mover una entrada
bastaría para desactivar el hashing por archivo, que es lo único que
añade v2. (`manifest-not-first` existe para exigir esto a cada
implementación.)

### 4.1 El directorio central debe coincidir

La entrada cero existe dos veces: una en la cabecera local en el
offset 0, y otra como el registro del directorio central que usará el
lector ZIP. Nada en el formato ZIP los obliga a describir los mismos
bytes — el directorio central se añade al final.

Un verificador **DEBE** leer el manifiesto por *ambas* vías y
comparar:

* la CLI y el registro comparan los dos strings de bytes / sus
  digests;
* el daemon lee la entrada 0 mediante su lector ZIP y compara los
  bytes con los que tomó del offset 0.

Vector: `header-disagree`. Este es el ataque más específico de v2 que
existe. Sin comprobar, el registro hashea, muestra y contrafirma un
manifiesto que ningún daemon aplicará jamás.

**Qué bytes se hashean cuando coinciden:** los bytes en el offset 0.
Cuando no coinciden el paquete se rechaza, así que la pregunta no se
plantea.

## 5. `MANIFEST.json`

JSON UTF-8, un objeto. La CLI lo escribe con formato bonito y un salto
de línea final; el digest se calcula sobre los bytes realmente
escritos, así que el formato es elección del productor y un
verificador **NO DEBE** reserializar antes de hashear.

Ejemplo completo — vector `ok-minimal`, los bytes exactos que hashean
a `2e16024e…`:

```json
{
  "schema": "astra.bundle/2",
  "plugin_id": "vector-plugin",
  "version": "1.0.0",
  "platform": {
    "os": "linux",
    "arch": "x86_64"
  },
  "protocol": 1,
  "min_astra_version": "",
  "capabilities": [
    "tools"
  ],
  "permissions": {},
  "permissions_hash": "sha256:44136fa355b3678a1146ad16f7e8649e94fb4fc21fe77e8310c060f61caaff8a",
  "entry": {
    "command": "./bin/fixture",
    "args": []
  },
  "files": [
    {
      "path": "bin/fixture",
      "sha256": "0f7ceb62618162c2ac6765ac683e65dc81ad19add148ada1e7186d186847caba",
      "size": 33,
      "mode": "0755"
    },
    {
      "path": "plugin.toml",
      "sha256": "da1141bb5c5390f1c8a646a0e0b0be1f26cdc0862ccb850dd86e0cd0238f3117",
      "size": 218,
      "mode": "0644"
    }
  ]
}
```

### 5.1 Campos

| campo | tipo | productor | verificador |
|---|---|---|---|
| `schema` | string | **DEBE** ser `"astra.bundle/2"` | **DEBE** comparar exactamente; cualquier otro valor → rechazar, nunca adivinar |
| `plugin_id` | string | el id del plugin, coincidiendo con `plugin.toml` | §9 |
| `version` | string | semver | comparado contra el listado por el registro y el daemon |
| `platform` | `{os, arch}` | ver §5.2 | la comprobación de compatibilidad de host es del instalador, no del formato |
| `protocol` | integer ≥ 0 | el protocolo de cable que habla el plugin | la comprobación de rango es del host |
| `min_astra_version` | string | semver, o `""` para sin requisito | — |
| `capabilities` | array de string | el vocabulario de capabilities del daemon | — |
| `permissions` | object | la sección `[permissions]` de `plugin.toml`, textual | §10 |
| `permissions_hash` | string | `"sha256:" ‖ hex` sobre los bytes canónicos del §10 | §10 |
| `entry` | `{command, args}` | §8 | §8 |
| `files` | array | §7 | §7 |

**Los productores DEBEN emitir cada campo de arriba.** Los
verificadores **DEBEN** rechazar un manifiesto al que le falte
`schema`, `plugin_id`, `version`, `platform`, `entry` o `files`.

*Divergencia, indicada en lugar de ocultada:* el daemon pone valor por
defecto a `protocol`, `min_astra_version`, `capabilities`,
`permissions` y `permissions_hash` cuando faltan
(`#[serde(default)]`); el lector de la CLI los exige. Un paquete que
omita uno es por tanto instalable y no verificable con
`astra-plugin verify`. No produzcas uno.

**Los miembros desconocidos DEBEN aceptarse e ignorarse.** Una adición
posterior de v2 (una `changelog_url`, por ejemplo) no debe hacer que
cada paquete que la lleve sea no instalable en un host más antiguo. Lo
que no puede cambiar sin un salto de schema es el *significado* de los
campos de arriba — y `schema` se compara exactamente, que es lo que
acota esto.

### 5.2 `platform`

```json
{"os": "linux",   "arch": "x86_64"}     → registry platform key  linux-x64
{"os": "windows", "arch": "x86_64"}     → registry platform key  windows-x64
{"os": "any",     "arch": "any"}        → registry platform key  noarch
```

`any` en un eje significa "sin requisito": un paquete es compatible
con un host cuando
`(os == "any" || os == host_os) && (arch == "any" || arch == host_arch)`.
`noarch` es cómo se distribuye cada plugin de TypeScript y Python —
código fuente o bytecode, ejecutado por una runtime que el host ya
tiene — y el registro escribe la misma URL y el mismo digest bajo cada
clave de plataforma soportada para uno, así que ningún cliente
necesita aprender la palabra. Vector: `ok-noarch-runtime`.

Ningún otro par `{os, arch}` nombra un target hoy. `linux-arm64`,
`windows-arm64`, `macos-x64` y `macos-arm64` son claves de plataforma
reservadas en el schema del registro; Astra no distribuye ningún
daemon para ellas.

## 6. Nombres de entrada

Se comprueba cada nombre de entrada del archivo. Las reglas existen
porque un nombre de entrada se convierte en una ruta en el sistema de
archivos de otra persona, y el extractor no es lo único que lo lee.

Un nombre de entrada se **rechaza** si se cumple alguna de estas
condiciones:

1. **vacío**.
2. contiene una **barra invertida** `\`. Las rutas ZIP usan solo `/`;
   una barra invertida es un separador de ruta en Windows y un
   carácter de nombre de archivo literal en otros sistemas.
3. **absoluta** — empieza con `/`.
4. contiene **`:`**. En NTFS `bin/fixture:stream` escribe *dentro de*
   `bin/fixture` como un flujo de datos alternativo, invisiblemente.
   Vector: `path-ads`.
5. contiene un **carácter de control** (U+0000–U+001F, U+007F).
6. tiene un **componente vacío** (`a//b`), o un componente igual a
   **`.`** o **`..`**. Vector: `path-traversal` (`../escape`).
7. tiene un componente que termina en un **punto o un espacio**. Win32
   elimina ambos en silencio, así que `bin/fixture.` y `bin/fixture`
   son dos entradas y un archivo. Vector: `path-trailing-dot`.
8. tiene un componente cuya **raíz** (el texto antes del primer `.`,
   comparado sin distinguir mayúsculas) es un nombre de dispositivo
   MS-DOS reservado: `con`, `prn`, `aux`, `nul`, `com1`–`com9`,
   `lpt1`–`lpt9`. `CON.txt` también es la consola.

Además:

9. **Los nombres duplicados se rechazan**, tanto exactamente como
   **sin distinguir mayúsculas**: `plugin.toml` y `Plugin.TOML` son
   dos entradas para un lector ZIP y un archivo en NTFS y APFS, donde
   la segunda sobrescribe la primera *después* de que la primera se
   hasheara. Vectores: `duplicate-entry`, `duplicate-entry-case` (ver
   divergencia F1).
10. **Las entradas de directorio se rechazan** (§2). Una entrada es un
    directorio si su nombre termina en `/`, o si sus atributos
    externos dan un modo Unix con `mode & 0o170000 == 0o040000`.
    Comprueba ambos: el primero es lo que un escritor ZIP emite
    convencionalmente, el segundo es lo que uno hostil puede emitir en
    su lugar.
11. **Las entradas de enlace simbólico se rechazan**: una entrada cuyos
    atributos externos dan un modo Unix con
    `mode & 0o170000 == 0o120000`. La fuga aquí está en el *destino*
    del enlace, que es el *contenido* de la entrada — cada regla de
    ruta anterior inspecciona el nombre y ninguna de ellas puede verlo.
    Vector: `symlink-entry`.

Estas reglas se aplican a **cada** entrada, incluyendo
`MANIFEST.json`, `SIGNATURE` y `PUBKEY`.

## 7. `files` — la lista contra la que se comprueba el archivo

`files` es un array de objetos:

| miembro | tipo | regla |
|---|---|---|
| `path` | string | un nombre de entrada del archivo; obedece §6 |
| `sha256` | string | **exactamente 64 caracteres hex en minúsculas**, sin prefijo |
| `size` | integer ≥ 0 | longitud en bytes sin comprimir |
| `mode` | string | cuatro dígitos octales, p. ej. `"0755"` — un *string*, porque JSON no tiene literal octal y `755` decimal es un modo distinto |

* `sha256` que contenga cualquier dígito hex en mayúscula se
  **rechaza**, no se pliega. Los digests aquí se comparan como
  strings, así que uno en mayúsculas nunca coincidiría con nada y se
  presentaría como un archivo corrupto en lugar de un manifiesto mal
  formado. Vector: `uppercase-digest`.
* `mode` **DEBE** analizarse como octal. Un `0o` inicial lo acepta el
  parser del daemon; los productores **NO DEBEN** emitirlo. `"0788"`
  se rechaza — 8 no es un dígito octal.
* El mismo `path` **NO DEBE** aparecer dos veces.
* Un nombre reservado (`MANIFEST.json`, `SIGNATURE`, `PUBKEY`) **NO
  DEBE** aparecer: el manifiesto no puede listar su propio digest, y
  el par heredado se calcula *sobre* los archivos listados.

### 7.1 Exhaustividad, en ambas direcciones

Sea `Listed` el conjunto de `files[].path` y `Present` el conjunto de
nombres de entrada del archivo menos los tres nombres reservados de
arriba. Un verificador **DEBE** aplicar:

```
Present ⊆ Listed     (no archive entry that the manifest does not list)
Listed ⊆ Present     (no listed file that the archive does not contain)
```

Ambas, siempre. Una sola es un agujero:

* comprobar solo `Listed ⊆ Present` le permite a un atacante
  **añadir** una entrada que el extractor escribe y que nada hashea —
  vector `extra-file` (`bin/backdoor`);
* comprobar solo `Present ⊆ Listed` le permite **eliminar** una y
  llamar íntegro al paquete — vector `missing-file`.

Y es la conjunción la que separa el par de colisión (§3.3).

### 7.2 Digests de contenido

Para cada entrada en `Present`: el SHA-256 del **contenido sin
comprimir** de la entrada **DEBE** ser igual al `sha256` de su línea
en `files`. Vector: `content-digest-mismatch` — el conjunto de
archivos correcto, las longitudes correctas, los bytes incorrectos.
Esta es la comprobación con la que tropieza un binario intercambiado.

*Cuándo* se realiza es una decisión de implementación con una
restricción dura: los bytes que se hashean **DEBEN** ser los bytes que
terminan en disco. El daemon, por tanto, hashea durante la extracción
en lugar de en su pasada previa a la extracción — ver divergencia F2,
que es por diseño y no un agujero.

### 7.3 Tamaños

El `size` de cada entrada **DEBE** ser igual al del manifiesto. Dos
comprobaciones independientes son apropiadas y el daemon hace ambas:
el tamaño declarado en el directorio central antes de hacer ningún
trabajo (está controlado por el atacante, así que esto es un detector
de mentiras barato, no la comprobación real), y un conteo de bytes
durante el streaming. El tamaño declarado es lo que acota la
extracción en streaming. Vector: `size-mismatch`.

### 7.4 Modos

Donde una entrada del archivo lleva un modo Unix, `mode & 0o777`
**DEBE** ser igual al `mode & 0o777` del manifiesto. Donde no lleva
ninguno — un archivo escrito en Windows — la comparación se omite; un
modo faltante no es un defecto, uno discrepante sí lo es. El modo del
manifiesto es lo que aplica un extractor. Vector: `mode-mismatch` (ver
divergencia F3).

Los productores normalizan: la CLI escribe `0755` para cualquier cosa
ejecutable (el binario de entrada resuelto, el bit de ejecución en
disco, o una ruta listada en `[bundle] executables`) y `0644` para
todo lo demás. Deliberadamente no copia modos arbitrarios en disco: un
checkout bajo un umask distinto, si no, cambiaría los bytes del
paquete sin cambiar su contenido.

### 7.5 Ordenado

`files` **DEBE** estar ordenado estrictamente ascendente por `path`,
comparado como **bytes crudos** (no por colación Unicode, no sin
distinguir mayúsculas). El daemon aplica el ascenso estricto
(`w[0].path >= w[1].path` → rechazar), lo que también captura el caso
de duplicado. A un verificador se le permite buscar binariamente en
este array; uno sin ordenar haría eso incorrecto en silencio. Vector:
`unsorted-files`.

## 8. `entry.command`

`entry.command` es el único campo del manifiesto que se convierte en
un `execve`. **DEBE** ser uno de:

* **una runtime del host**, comparada exactamente contra la lista
  cerrada `python`, `python3`, `node`, `bun`, `deno`; o
* **una ruta a un archivo que lista el manifiesto.** Comparar tras
  quitar un `./` inicial y convertir `\` a `/`. El resultado **DEBE**
  aparecer en `files[].path`.

Rechazado de plano:

* vacío (tras recortar);
* absoluto (`/usr/bin/sh`, o un prefijo de letra de unidad de Windows
  como `C:\…`);
* que contenga un componente `..` — vector `entry-command-escape`
  (`../../../bin/sh`);
* que nombre un archivo que el manifiesto no lista — vector
  `entry-command-shell` (`sh`).

**Sobre las shells.** El registro rechaza una shell por nombre — `sh`,
`bash`, `zsh`, `fish`, `dash`, `csh`, `ksh`, `cmd`, `cmd.exe`,
`powershell`, `powershell.exe`, `pwsh`, `pwsh.exe` — con un código de
error distinto, porque `entry.command: "sh"` convierte `args` sin
restringir en código arbitrario. La CLI y el daemon llegan al mismo
veredicto mediante la regla runtime-o-archivo-listado (una shell no es
ninguna de las dos cosas). Un verificador conforme solo necesita la
regla general; nombrar shells por separado compra un mejor mensaje, no
un resultado distinto.

`entry.args` es un array de strings, por defecto `[]`. Este formato no
impone ninguna restricción sobre su contenido; el host no lo
interpreta.

**No lo "endurezcas" a "debe ser un archivo listado".** Eso dejaría
fuera de servicio toda la mitad script del catálogo — cada plugin de
TypeScript y Python se ejecuta a través de una runtime del host. El
vector `ok-noarch-runtime` (`entry.command: "node"`,
`platform: any/any`) existe precisamente para capturar ese error, y es
un vector de *aceptación*.

## 9. `plugin.toml` y `plugin.id`

Cada paquete **DEBE** contener una entrada `plugin.toml`, listada en
`files` como cualquier otro archivo. Es el manifiesto de plugin que
analiza el host; su referencia completa de campos está en
[la referencia del manifiesto](../reference/manifest.md).

Dos reglas pertenecen a *este* documento porque un paquete puede
rechazarse por ellas:

* `MANIFEST.plugin_id` y `MANIFEST.version` **DEBEN** coincidir con lo
  que se le pidió al instalador, y con el listado que ofrece el
  paquete. Sin esto, una entrada de registro `foo` podría servir un
  archivo cuyo manifiesto dice `bar`, y `bar` se instalaría.
* **`plugin.id` se convierte en un componente de ruta** —
  `<plugins_dir>/<id>/` — un directorio que el host crea, en el que
  escribe y que elimina recursivamente. Por tanto se valida:
  * no vacío, y cada carácter es `[a-z0-9-]` (letras ASCII
    minúsculas, dígitos, guion);
  * **NO DEBE** terminar en un punto o un espacio (ya excluido por el
    conjunto de caracteres; mantenido como regla separada para que
    relajar el conjunto de caracteres más adelante no pueda
    reintroducir el agujero en silencio);
  * **NO DEBE** ser un nombre de dispositivo MS-DOS reservado según
    la regla de raíz del §6.8.

  Vectores: `plugin-id-traversal`, `plugin-id-con` (ver divergencia
  F4). `con` es instalable en Linux, imposible en Windows, e invisible
  para una CI de Linux que solo ejecuta cosas.

## 10. `permissions` y `permissions_hash`

`MANIFEST.permissions` es la sección `[permissions]` del plugin,
copiada textualmente: un objeto que mapea un id de permiso a un objeto
de solicitud (`{reason?, types?, scopes?}`). Su vocabulario y
significado están en [`permissions.md`](permissions.md); esta sección
solo define los bytes y el hash.

```
canonical_bytes  = RFC 8785 (JCS) serialisation of the permissions object
permissions_hash = "sha256:" ‖ lowercase_hex( SHA256( canonical_bytes ) )
```

Reglas:

* **`null` y `{}` son el mismo valor** — un plugin que no pide nada —
  y ambos se canonicalizan a `{}`. Un productor que omite el miembro y
  uno que escribe un objeto vacío **DEBEN** producir el mismo hash.
  Ese hash es
  `sha256:44136fa355b3678a1146ad16f7e8649e94fb4fc21fe77e8310c060f61caaff8a`
  = `sha256("{}")`, y aparece en la mayoría de los vectores.
* El prefijo `sha256:` es **parte del valor**, a diferencia de
  `files[].sha256`. Lleva su algoritmo porque este número se compara
  a través de un límite de repositorio — el empaquetador lo escribe,
  el registro lo vuelve a derivar en la ingesta, el host lo vuelve a
  derivar antes de creerlo.
* Los miembros vacíos se **omiten**, no se emiten vacíos: una
  solicitud sin reason, sin types y sin scopes es `{}`, nunca
  `{"reason":""}`. Dos ortografías canónicas de una declaración son
  exactamente la desviación que este hash existe para prevenir.
* JCS en la práctica: claves de objeto ordenadas por unidad de código
  UTF-16, sin espacios en blanco insignificantes, strings escapados
  como exige RFC 8785 §3.2.2.2. Los valores de este documento son solo
  strings, arrays de strings y objetos — sin números — así que la
  mitad sutil de JCS (la canonicalización de números del §3.2.2) no
  se presenta aquí.

Ejemplo resuelto (vector `ok-permissions`, los valores a los que se
sujeta cada implementación):

```
{"fire_trigger":{"reason":"Fires the on_dice_roll trigger you configure"},"subscribe_events":{"reason":"Watches for command_completed"}}
→ sha256:63dde3632926bc9fb348e0973dbce01d07476a1569cede023edde451b04a6a85
```

y uno con argumentos, canonicalizado:

```
{"set_variable":{"scopes":["plugin"]},"subscribe_events":{"reason":"Watches for command_completed","types":["command_completed","tool_started"]}}
```

Un verificador **DEBE** recalcular el hash a partir de
`MANIFEST.permissions` y rechazar un manifiesto que discrepe de su
propio `permissions_hash`. Vector: `permissions-hash-mismatch` — el
bloque `permissions` pide `fire_trigger` y el `permissions_hash` es el
hash de `{}`, es decir, los dos describen plugins distintos. Consulta
la divergencia F5 para saber quién comprueba esto hoy.

## 11. El par heredado `SIGNATURE` / `PUBKEY`

Un paquete pre-v2 podía llevar dos entradas extra: `SIGNATURE` (base64
de una firma Ed25519 de 64 bytes sobre el digest de concatenación del
§3.3) y `PUBKEY` (base64 de la clave pública cruda de 32 bytes). Están
**en retirada**, y mientras existan:

* nunca se **listan** en `files` (se calculan sobre los archivos
  listados);
* si una está presente, **AMBAS DEBEN** estarlo, y **DEBEN** ser las
  dos últimas entradas del archivo, `SIGNATURE` y luego `PUBKEY`.
  Cualquier cosa después de ellas quedaría fuera de lo que cubre la
  firma. Vector: `ok-legacy-signed` (un vector de aceptación — el par
  se tolera, no se exige).
* **No son una señal de confianza.** Una clave que se distribuye en el
  archivo que autentica no prueba nada sobre quién la escribió, y el
  digest que cubren es el ambiguo. Un verificador **NO DEBE** tratar
  su presencia, validez o ausencia como evidencia de nada. El registro
  emite un aviso (`W_LEGACY_SIGNATURE_ENTRY`) y continúa.

Retirada, nombrada una vez en cada lado para que los dos no puedan
divergir: el `LEGACY_PAIR_SUNSET` de la CLI
(`astra-plugin 0.5.0 / Astra 0.4.0`) y el `LEGACY_SIGNATURE_SUNSET`
del daemon (`Astra 0.4.0 (astra-plugin 0.5.0)`). `astra-plugin build`
ya no las escribe; `astra-plugin sign` es lo único que lo hace, y se
retira junto con el lector del daemon.

## 12. Límites

De [`spec/limits.yaml`](../../../spec/limits.yaml), el único lugar
donde se declaran estos números:

| límite | valor | se aplica a |
|---|---|---|
| `max_archive_entries` | 10 000 | número de entradas ZIP, incluyendo `MANIFEST.json` |
| `max_extract_bytes` | 524 288 000 (500 MiB) | total de bytes sin comprimir |
| techo del manifiesto | 4 MiB | solo `MANIFEST.json` |

Un paquete que exceda alguno de estos **DEBE** rechazarse. Aplica el
techo de conteo de entradas **antes** de asignar un registro por
entrada, y el techo de bytes tanto a la suma declarada del manifiesto
como a los bytes que realmente llegan durante el streaming — los
números declarados son la propia afirmación del archivo.

La CLI se niega a *compilar* más allá de estos límites, así que un
autor se entera en su propia máquina en lugar de por una instalación
fallida de un usuario.

## 13. El algoritmo de verificación

Esta es la forma implementable. Un verificador tiene un archivo y,
opcionalmente, una expectativa `(plugin_id, version, platform_key)` de
un listado. Cada paso es un **rechazo** en caso de fallo.

**A. El archivo.**
1. `artifact_digest = SHA256(file)`. Si se proporcionó un digest
   esperado y no coincide, detente aquí; nada de lo de abajo es
   significativo.

**B. Entrada cero, desde el offset 0.** (§4)
2. Analiza la cabecera de archivo local. Nombre = `MANIFEST.json`;
   bits de flags 0 y 3 desactivados; método 0; tamaño no es el
   centinela ZIP64 y ≤ 4 MiB; extrae los bytes del manifiesto.
3. `manifest_digest = SHA256("astra.bundle/2" ‖ 0x00 ‖ manifest_bytes)`.
4. Analiza el manifiesto como JSON. `schema == "astra.bundle/2"`,
   exactamente.

**C. El directorio central.** (§2, §4.1, §12)
5. Abre el archivo normalmente. Conteo de entradas ≤ 10 000.
6. La entrada 0 en el directorio central es `MANIFEST.json`, stored, y
   sus bytes son iguales a los del paso 2.

**D. Estructura, antes de cualquier contenido.** (§6, §7, §12)
7. Recorre las entradas en orden. Para cada una: aplica §6 (reglas de
   nombre, sin directorio, sin symlink, sin duplicado exacto o
   plegado por mayúsculas).
8. Construye `Present` (nombres de entrada menos los tres nombres
   reservados). Comprueba `Present ⊆ Listed` y `Listed ⊆ Present`.
9. Para cada línea de `files`: `sha256` hex de 64 caracteres en
   minúsculas, `mode` octal de cuatro dígitos analizable, sin `path`
   duplicado, sin `path` reservado; el array es estrictamente
   ascendente por `path` como bytes.
10. Para cada entrada en `Present`: el `size` declarado coincide, y —
    donde el archivo lleva un modo — `mode & 0o777` coincide.
11. Suma de `files[].size` ≤ 500 MiB.
12. Si `SIGNATURE` o `PUBKEY` está presente: ambas lo están, y son las
    dos últimas entradas en ese orden.
13. `entry.command` es un archivo listado o una runtime del host (§8).

**E. Contenido.** (§7.2)
14. Para cada entrada en `Present`, en streaming y acotado por el
    tamaño declarado: el SHA-256 del contenido sin comprimir es igual
    al del manifiesto. Si el verificador también extrae, hashea los
    bytes que escribe, no una segunda lectura.

**F. Comprobaciones cruzadas que exige el formato y que un lector
estructural por sí solo no puede hacer.**
15. `permissions_hash` es igual al recalculado a partir de
    `MANIFEST.permissions` (§10).
16. `plugin.toml` se analiza, y `plugin.id` obedece §9.
    `plugin_id` / `version` / `platform` coinciden con el listado que
    ofreció el paquete, si lo hay.

Los pasos A–E solo necesitan el archivo. El paso F necesita el archivo
y el listado.

## 14. Vectores dorados

`testdata/bundles/` contiene 27 archivos `.astraplugin` congelados,
`vectors.json` (veredicto, capa, ambos digests, y qué hace hoy cada
implementación) y `SHA256SUMS`. Los dos consumidores tienen copias
vendorizadas (`Astra/astra-rs/astra-daemon/testdata/bundles/`,
`astra-registry/tests/vectors/`), refrescadas por
`tools/vendor-testdata.sh`. Cada suite verifica su copia contra
`SHA256SUMS` antes de leer un solo vector.

**Ninguna suite regenera sus fixtures.** Una suite que construyera sus
entradas a partir del código de hoy estaría afirmando que el código de
hoy concuerda consigo mismo.

### Aceptar (5)

| vector | qué demuestra |
|---|---|
| `ok-minimal` | el control. Todo rechazo tiene que ser un rechazo *de* algo |
| `ok-noarch-runtime` | `platform: any/any` + `entry.command: "node"` — cómo se distribuye cada plugin de TypeScript y Python (§5.2, §8) |
| `ok-permissions` | un mapa de permisos no vacío con un hash correcto — tres implementaciones de JCS forzadas a coincidir (§10) |
| `ok-legacy-signed` | el par en retirada, dos últimas entradas, en orden (§11) |
| `collision-a-bc` | la mitad honesta del par de colisión (§3.3) |

### Rechazar (22)

| vector | regla que rechaza |
|---|---|
| `collision-ab-c` | §7.1, **ambas** direcciones |
| `extra-file` | §7.1 `Present ⊆ Listed` |
| `missing-file` | §7.1 `Listed ⊆ Present` |
| `duplicate-entry` | §6.9 duplicado exacto |
| `duplicate-entry-case` | §6.9 duplicado plegado por mayúsculas (F1) |
| `symlink-entry` | §6.11 |
| `content-digest-mismatch` | §7.2 (F2) |
| `size-mismatch` | §7.3 |
| `mode-mismatch` | §7.4 (F3) |
| `uppercase-digest` | conjunto de caracteres `sha256` del §7 |
| `unsorted-files` | §7.5 |
| `manifest-not-first` | §4 |
| `manifest-compressed` | §4 |
| `header-disagree` | §4.1 |
| `path-traversal` | §6.6 (y §7.1: la entrada no está listada) |
| `path-ads` | §6.4 (y §7.1) |
| `path-trailing-dot` | §6.7 (y §7.1) |
| `entry-command-shell` | §8 |
| `entry-command-escape` | §8 |
| `plugin-id-traversal` | §9 (F4) |
| `plugin-id-con` | §9 (F4) |
| `permissions-hash-mismatch` | §10 (F5) |

Nota sobre los tres vectores `path-*`: cada uno esconde su entrada
hostil *fuera* de `MANIFEST.files`, así que un verificador que solo
implemente §7.1 rechaza los tres. Aun así debería implementar §6 — el
día en que un manifiesto liste tal ruta, la exhaustividad no tiene
nada que decir y solo las reglas de nombre sí.

### 14.1 Valores de autocomprobación

Para cualquier implementación, la comprobación inicial más rápida es
que ambos digests de cada vector coincidan con `artifact_sha256` y
`manifest_digest` de `vectors.json`. Esos números no vienen de ninguno
de los tres programas: `testdata/bundles/handcheck.sh` los deriva de
nuevo a partir de `dd`, `od`, `printf`, `cat` y `sha256sum`. 27 digests
de artefacto y 25 digests de manifiesto coinciden — las dos omisiones
son `manifest-not-first` y `manifest-compressed`, cuya entrada cero
por construcción no es un manifiesto almacenado. Un bug compartido
puede hacer que tres programas concuerden entre sí; no puede hacer que
concuerden con coreutils.

## 15. Divergencias conocidas

Están en `vectors.json` bajo `divergence`, y cada una la verifican las
tres suites — un comportamiento fallido con una prueba que cambia de
color cuando se arregla, en lugar de un TODO en un comentario. **En
cada fila el veredicto de este documento es la respuesta correcta.**

| | vector | quién está fuera de línea | por qué está donde está |
|---|---|---|---|
| **F1** | `duplicate-entry-case` | solo el daemon pliega mayúsculas antes de buscar duplicados | la CLI y el registro usan conjuntos de coincidencia exacta. Ambos deberían plegar. |
| **F2** | `content-digest-mismatch` | la pasada previa a la extracción del daemon lo acepta | **por diseño.** El daemon hashea el contenido *durante* la extracción, así que los bytes hasheados son los bytes escritos. No es un agujero; es la misma comprobación en un momento distinto. |
| **F3** | `mode-mismatch` | el bot del registro no compara modos en absoluto (solo aviso) | los modos los aplica el instalador, no el registro, así que degradó la comprobación. El §7.4 dice: comparar. |
| **F4** | `plugin-id-*` | la CLI no valida ninguno, ni en `verify` ni en `check` | tanto `PluginManifest::validate` del daemon como `invalidId` del registro rechazan. La propia máquina del autor también debería. |
| **F5** | `permissions-hash-mismatch` | solo el lector de paquetes de la CLI no recalcula el hash | el daemon bloquea la instalación (`PERMISSIONS_HASH_MISMATCH`) y el registro se niega a listar (`E_PERMISSIONS_HASH_MISMATCH`). |

Si cierras una, borra el bloque `divergence` y pon el `expect` de esa
implementación al veredicto — las suites te lo dirán en el momento en
que lo hayas hecho.

## 16. Qué te dice un paquete verificado y qué no

**Sí dice:** estos bytes son exactamente los bytes que lista su
manifiesto, cada archivo del paquete está contabilizado en ambas
direcciones, nada se extrae fuera del directorio de instalación, y el
digest que tienes es el digest que obtendrá cualquier otro que lo
calcule sobre este archivo.

**No dice:** quién lo escribió (eso es la attestation y el índice
firmado — [`registry-index.md`](registry-index.md)), si está
actualmente retirado (eso es la lista de revocación), qué puede
llamar en tiempo de ejecución ([`permissions.md`](permissions.md)), o
qué puede hacerle el proceso a la máquina una vez que arranca. Un
plugin se ejecuta como el usuario, con los privilegios del usuario.
Nada en este formato cambia eso, y nada en la interfaz de Astra puede
dar a entender que sí.

---

*Fuentes comprobadas al escribir este documento, todas leídas en el
commit en que aterrizó: `astra-plugin-cli/src/bundle.rs`;
`Astra/astra-rs/astra-daemon/src/plugins/bundle.rs`;
`Astra/astra-rs/astra-daemon/src/plugins/trust.rs` (`permissions_hash`, `jcs`);
`Astra/astra-rs/astra-plugin-manifest/src/manifest.rs` (`validate`,
`is_reserved_device_name`); `astra-registry/bot/lib/bundle.mjs`;
`astra-registry/tools/lib/canonical.mjs`; `spec/limits.yaml`;
`testdata/bundles/{README.md,vectors.json}` y los propios bytes de los
vectores.*
</content>
