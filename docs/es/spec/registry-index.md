> **Traducción.** Esta es una traducción. Si hay alguna discrepancia, [`docs/en`](../../en/spec/registry-index.md) es la referencia autorizada.

# Los documentos firmados del registro — especificación normativa

**Estado:** normativo para los formatos de documento y las reglas de
verificación. **Todavía no en vigor:** la cadena de firmas descrita
aquí está especificada, implementada en ambos extremos, y **no
anclada** — consulta el §0.1 antes de confiar en ninguna frase de este
archivo como garantía de seguridad.

Cuatro documentos, tres schemas, una construcción de firma:

| documento | string de schema | firmado por | copia de este repo |
|---|---|---|---|
| `root.json` | `astra.registry.root/1` | **nada** — es una transcripción de claves compiladas en Astra | `astra-registry/registry/v1/root.json` |
| `trust.json` | `astra.registry.trust/1` | una clave **raíz** | publicado junto al catálogo |
| `index.json` | `astra.registry.index/1` | una clave de **índice** en la que delega `trust.json` | `astra-registry/registry/v1/index.json` |
| `revocations.json` | `astra.registry.revocations/1` | la misma clave de índice | `astra-registry/registry/v1/revocations.json` |

Las palabras de requisito siguen RFC 2119.

---

## 0. Qué responde esta cadena, y qué no

Responde: *¿es este el catálogo que publicó el registro de Astra, está
actualizado, y se ha retirado algo de él?* Es lo único que hace seguro
instalar desde un registro en caché, porque el registro fija un digest
de artefacto y un digest no caduca.

**No** responde *quién compiló el plugin*. Eso es la attestation de
compilación de GitHub, comprobada por el bot del registro en la
ingesta (§7), nunca por el daemon. Lo que tiene el daemon es una
*afirmación* del registro sobre el autor, fijada en la primera
instalación (TOFU) y vinculada a la URL de descarga — consulta el
§7.3. El texto de la UI está obligado a decir "mismo autor que antes"
y nunca "compilación verificada".

### 0.1 La cadena todavía no está anclada — lee esto primero

* `astra-registry/registry/v1/root.json` lleva
  `"status": "provisioned"` y dos claves Ed25519. La ceremonia en
  `astra-registry/SECURITY.md` §4 (`tools/keygen-root.sh`) se ejecutó
  sin conexión el 2026-08-11.
* `PRODUCTION_ROOT_KEYS` de `astra-daemon` lista las mismas dos. La
  copia del registro es pública para que un tercero pueda leerlas sin
  desensamblar un binario, y para que un desacuerdo entre ambas sea
  visible; las mitades privadas nunca estuvieron en una máquina
  conectada a red.
* **Una clave raíz no firma un catálogo.** Firma `trust.json`, que
  delega en una clave de firma de índice. **Ese documento ya está
  firmado.** `registry/v1/trust.json` se verifica bajo
  `astra-root-2026a`, delega en la clave de firma de índice
  `astra-index-2026a`, y nombra el único commit del workflow
  reutilizable que el bot aceptará en una attestation de compilación
  (`e3329df252a46d747676cb540ae4b986af68a3ad`, al que apunta la
  etiqueta `plugin-release/v1`). El propio
  `node tools/sign-trust.mjs --verify registry/v1/trust.json` del
  registro imprime los tres hechos. Así que `E_TRUST_UNPROVISIONED`
  ya no se dispara en la ingesta.
* Por tanto, hoy: `trust.json` se verifica y una clave de índice está
  delegada, pero **nada ha firmado el catálogo con ella**. Cada
  catálogo se sigue clasificando como `UNSIGNED`, pero la ceremonia cambió
  el motivo que lleva — de `NoTrustAnchor` a **`NoSignatures`**. El
  `classify_signature` del daemon los separa con exactitud:
  `NoTrustAnchor` significa que ningún `trust.json` verificado llegó a la
  compilación, así que no hay clave con la que comprobar ninguna firma y el
  catálogo bien podría estar firmado; `NoSignatures` significa que el ancla
  está y el catálogo mismo no lleva ninguna. Lo que se movió es qué enlace
  falta: la brecha ahora está entre la clave delegada y el índice, no entre
  la raíz y la delegación.
* `registry/v1/index.json` y `registry/v1/revocations.json` están
  confirmados con `"signatures": []` — "sin firmar" dicho en voz alta,
  donde un miembro ausente no podría distinguirse de uno eliminado.
* Consecuencias que se derivan y que no deben disimularse: un catálogo
  sin firmar nunca puede ascender un registro a instalable con
  confianza total, y porque `verify_revocations_document` es estricto
  (§6.4), **una lista de retirada sin firmar se rechaza, así que la
  aplicación de revocaciones tampoco está activa** —
  `RevocationFreshness::NotEnforced` hasta que se obtenga una vez una
  lista con firma válida.

Todo lo de abajo describe el formato y el algoritmo, y nada de eso
cambia cuando llegue el enlace que falta. La ceremonia de la raíz ya
se ha ejecutado y la delegación está firmada; lo que falta es que
aparezca una firma en el array `signatures` de un `index.json`
publicado, momento en el que la cadena empieza a tener peso en la
máquina de un usuario.

## 1. El sobre

Cada documento firmado tiene la misma forma exterior:

```json
{
  "$comment": "…free text…",
  "signed":     { "schema": "…", "serial": 1, "…": "…" },
  "signatures": [ { "key_id": "astra-reg-2026a", "sig": "<base64, 88 chars>" } ]
}
```

* **Solo `signed` está autenticado.** Nada fuera de él puede leerse
  como un hecho — ni `$comment`, ni los strings de `key_id`, ni la
  propia forma de la lista de firmas.
* `sig` es base64 de la **firma Ed25519 cruda de 64 bytes**. El schema
  del índice fija la ortografía: `^[A-Za-z0-9+/]{86}==$`.
* `key_id` es una **pista** para logging y selección de clave. Un
  verificador **DEBE** probar cada clave de confianza contra cada
  firma ofrecida y **DEBE** reportar la `key_id` de la clave que
  realmente verificó, nunca la que afirmaba el documento. Un documento
  que mienta sobre quién lo firmó igual verifica si lo hizo una clave
  de confianza, y nunca verifica solo porque nombró la clave correcta.
* Un array `signatures` vacío significa sin firmar. No es una forma de
  error; es el estado previo a la ceremonia y el estado de cualquier
  catálogo local escrito a mano.

## 2. La entrada de firma

```
digest = SHA-256( domain ‖ 0x00 ‖ JCS(signed) )
sig    = Ed25519(private_key, digest)
```

* `domain` es el string de schema del documento: `astra.registry.trust/1`,
  `astra.registry.index/1`, o `astra.registry.revocations/1`.
* **El verificador suministra `domain` desde su propia constante,
  nunca desde el miembro `schema` del archivo que está leyendo.** De
  lo contrario, una firma sobre un `trust.json` sería reproducible
  como firma sobre un `index.json` editando un string — y cualquiera
  que consiguiera firmar un catálogo podría entonces publicar una
  lista de retirada *vacía* y apagar el mecanismo.
* El `0x00` es lo que impide que un dominio que es prefijo de otro
  colisione con él.
* La verificación Ed25519 **DEBERÍA** ser estricta
  (`ed25519_dalek::verify_strict`, o equivalente): rechazar claves
  públicas de orden bajo y las codificaciones maleables que un
  verificador permisivo acepta.
* La firma es sobre el digest SHA-256, pasado a Ed25519 como un mensaje
  ordinario. No actives ningún modo "pre-hasheado"; Ed25519 hashea
  internamente y esta construcción le da 32 bytes.

Ambos extremos de esto existen y concuerdan por prueba:
`astra-registry/bot/lib/sign.mjs` (`signingDigest`, `signEnvelope`,
`verifyEnvelope`) y `astra-daemon/src/plugins/trust.rs`
(`signing_digest`, `verify_envelope`). `astra-registry/bot/fixtures/index/`
contiene un documento producido por el firmante de JavaScript que el
verificador de Rust comprueba byte a byte, así que ninguno de los dos
puede desviarse sin un build en rojo.

## 3. Canonicalización (perfil JCS)

`JCS(signed)` es JSON canónico según RFC 8785, con un estrechamiento
deliberado.

* **Las claves de objeto se ordenan por unidad de código UTF-16** (RFC
  8785 §3.2.3). Eso es lo que hace por defecto
  `Array.prototype.sort()` de JavaScript, y el lado de Rust lo
  deletrea explícitamente
  (`a.encode_utf16().cmp(b.encode_utf16())`) en lugar de asumir orden
  de bytes. Para claves todo-ASCII los dos órdenes coinciden; por
  encima del BMP no.
* **Sin espacios en blanco insignificantes.** Forma compacta.
* Los **strings** se escapan como exige RFC 8785 §3.2.2.2: escapar
  `"`, `\` y los controles C0 (formas cortas donde existan), dejar `/`
  y todo lo no-ASCII como UTF-8 literal.
* **Los números DEBEN ser enteros en ±(2^53 − 1)** —
  `Number.MAX_SAFE_INTEGER` de JavaScript. Ambas implementaciones
  **rechazan** cualquier otra cosa en lugar de implementar la
  canonicalización de punto flotante del §3.2.2. El registro solo
  emite enteros (`serial`, `size`, `protocol`), y una implementación
  que acierte el §3.2.2 *casi* del todo produce firmas que verifican
  en un lado y no en el otro. `1.0` y `1` son el mismo número JSON y
  ambos serializan como `1`.
* **Las claves de objeto duplicadas DEBEN rechazarse en el momento del
  análisis**, no resolverse (RFC 8785 §3.1). `{"a":1,"a":2}` significa
  dos cosas, y un documento firmado debe significar una. Los bytes
  después del documento se rechazan por la misma razón.
* Los miembros cuyo valor sea `undefined` no existen; eso no existe en
  JSON. (El serializador del registro los descarta; un parser JSON
  nunca produce uno.)

El archivo bonito confirmado en el repositorio lo produce el *mismo*
serializador (`stableStringify`) con el mismo orden de claves, así que
un revisor que lee un diff está leyendo los bytes que se firman,
salvo espacios en blanco.

## 4. Claves, delegación y rotación

### 4.1 Raíces

* Ed25519. Las mitades públicas están **compiladas en Astra**, base64
  de los 32 bytes crudos.
* **Dos ranuras**, generadas en una ceremonia sin conexión: una
  `Active`, una `Reserve` que nunca se usa hasta que hay que
  reemplazar una raíz. Ambas se distribuyen desde el primer día, así
  que reemplazar una raíz es una firma en lugar de un día de corte.
* Una raíz firma **`trust.json` y nada más**. Una firma raíz nunca
  aparece en `index.json`, en `revocations.json`, ni en un paquete.
* `root.json` es una transcripción, no una autoridad: está sin firmar
  a propósito — un documento raíz autofirmado no demuestra nada que
  la clave compilada no demuestre ya. Existe para que las dos copias
  puedan compararse. El `fingerprint_sha256` de cada entrada es
  SHA-256 sobre la clave pública cruda de 32 bytes, hex en
  minúsculas; el mismo valor que imprime `tools/keygen-root.sh` y que
  registra el daemon cuando una firma raíz verifica.
* Existen raíces de prueba (`astra-registry/tools/testkeys/`, mitades
  privadas confirmadas a propósito, `key_id` con prefijo
  `TEST-ONLY-DO-NOT-TRUST-`). El daemon solo puede compilarlas detrás
  del feature no predeterminado `insecure-test-trust-roots` **en un
  perfil de depuración**; pedirlo en un perfil de release es un
  `compile_error!`.

### 4.2 `trust.json`

```json
{ "signed": {
    "schema": "astra.registry.trust/1",
    "serial": 3,
    "issued_at": "2026-08-01T00:00:00Z",
    "expires_at": "2026-11-01T00:00:00Z",
    "index_keys": [
      { "key_id": "astra-reg-2026a", "public_key": "<base64 32 bytes>",
        "not_before": "2026-07-01T00:00:00Z", "not_after": "2026-10-01T00:00:00Z",
        "comment": "quarterly" }
    ],
    "reusable_workflow_shas": ["<40-hex commit>"]
  },
  "signatures": [ … ] }
```

Reglas de verificación:

* `serial` **NO DEBE** ser 0 — 0 es el centinela "todavía nada
  aceptado" del lado del verificador, así que un documento publicado
  no puede reclamarlo.
* `schema` **DEBE** ser igual a `astra.registry.trust/1`. Compruébalo
  antes de la firma únicamente para que un documento mal archivado
  diga "schema incorrecto" en lugar de "ninguna raíz firmó esto"; no
  puede cambiar el resultado, porque el dominio del digest es la
  propia constante del verificador.
* Los miembros desconocidos se **conservan e ignoran**. Un registro
  más nuevo que añada un campo no debe inutilizar a un daemon más
  antiguo, y el `signed` verificado en crudo sobrevive un round trip,
  así que nada se descarta y refirma en silencio.
* Una entrada de `index_keys` con una clave no analizable o una
  ventana no analizable se **omite con un aviso**, no es fatal: una
  fila mala no debe costarle un catálogo que otra clave podría
  verificar. Un `not_before` no analizable se trata como *todavía no
  válido* y un `not_after` no analizable como *caducado* — fail
  closed en la fila, abierto en el documento.
* `reusable_workflow_shas` es la lista blanca de SHA de commit de
  workflow reutilizable resueltos que aplica el **bot del registro**
  (§7). El daemon la lleva y no la usa. Cambiarla es una ceremonia de
  clave raíz, que es todo el sentido de ponerla aquí.

**Rotación.** Trimestral, e inmediata ante sospecha. Una rotación
planificada publica un `trust.json` en el que la clave saliente y la
entrante tienen **ventanas solapadas durante 30 días**, así que
`index_keys_valid_at(now)` devolviendo dos claves es el estado normal
durante un cambio, no una anomalía.

### 4.3 Qué reloj juzga una ventana de clave

Existen dos lecturas de reloj: la de esta máquina, y el `Date` HTTP
del fetch que produjo el documento.

* La **actualidad** (§5) se juzga en `now = server_date ?? local` —
  cree la lectura del registro durante la duración de un fetch. Esto
  no le cuesta al atacante nada que no tuviera ya (podría servir un
  documento obsoleto a una máquina cuyo reloj no controla) y rescata
  el caso mucho más común: un portátil con el reloj mal a quien se le
  dice que su catálogo ha caducado.
* Las **ventanas de validez de clave** se juzgan en
  `window_now = max(local, server)` — la red puede tirar de "now"
  *hacia adelante* y **nunca** empujarlo hacia *atrás*. `not_after`
  es el único mecanismo que retira una clave de índice comprometida;
  juzgarlo en un instante suministrado por la red le permitiría al
  ladrón también elegir el día, para siempre, respondiendo con un
  `Date` antiguo. Tomar la lectura más tardía hace que una clave
  retirada robada quede *más* caducada, controle el atacante la
  lectura que controle.
* Un desacuerdo más allá de **2 horas** (`CLOCK_SKEW_TOLERANCE_HOURS`)
  es en sí mismo la señal: el veredicto se convierte en `CLOCK_SKEW`
  en lugar de una afirmación sobre el documento. Lo bastante pequeño
  para que una batería CMOS muerta lo dispare de inmediato, lo
  bastante grande para que el desfase ordinario sin NTP no lo haga.
* Cualquier cosa **duradera** escrita a partir de un reloj (marcas de
  tiempo de la última obtención, pisos) se fija primero al reloj
  local. Una respuesta con `Date: Fri, 01 Jan 2100 …` de otro modo
  movería permanentemente la noción de presente de un daemon a 2100 —
  una denegación de servicio duradera escrita por cualquiera que
  pueda responder a un solo fetch.

## 5. `index.json`

### 5.1 Forma

`signed` es:

| miembro | tipo | regla |
|---|---|---|
| `schema` | const `astra.registry.index/1` | obligatorio |
| `serial` | integer ≥ 0 | obligatorio, monótono (§5.4) |
| `issued_at` | `YYYY-MM-DDTHH:MM:SSZ` | sellado **al firmar**, ausente en el árbol confirmado |
| `expires_at` | igual | `issued_at + 30 días` |
| `plugins` | array | un registro por plugin listado, ordenado por `id` |

Las marcas de tiempo son RFC 3339 UTC, **precisión de segundos, sin
milisegundos, sin offset**. Dos ortografías de un instante son dos
documentos firmados distintos.

Un registro de plugin lleva `id`, `name`, `version`, `description`,
`license`, `capabilities`, `repository_url`, `source`, `icon_url`,
`downloads`, `stars`, `updated_at`, `download_url`,
`platform_downloads` y `releases[]`. El JSON Schema completo es
`astra-registry/schema/index-v1.json`; es
`additionalProperties: false` y es la autoridad sobre la lista de
campos.

Dos reglas vale la pena repetir porque un verificador depende de
ellas:

* **`releases[]` es la mitad autoritativa**, la más nueva primero por
  precedencia semver. Cada release tiene `version`, `published_at`,
  `release` (`{kind: "github_release", repo, tag}` o
  `{kind: "direct", base_url}`) y `artifacts` (clave de plataforma →
  `{url, filename, sha256, size}`).
* **Los campos planos son una proyección** de `releases[0]`,
  calculada en la misma pasada del generador, así que no pueden
  discrepar de ella. `version`, `platform_downloads` y `download_url`
  existen porque el daemon que se distribuye lee exactamente esos.

Claves de plataforma: `linux-x64`, `windows-x64`, `noarch`, más las
reservadas `linux-arm64`, `windows-arm64`, `macos-x64`,
`macos-arm64`. Un artefacto `noarch` se escribe bajo **cada clave de
plataforma soportada**, así que ningún cliente necesita conocer la
palabra (`PLATFORM_KEYS_FOR_NOARCH = ["linux-x64", "windows-x64"]`).

`downloads` y `stars` son siempre `0`. Este registro no cuenta nada.

Las **entradas en staging** — un listado cuyo release existe sobre el
papel pero todavía no tiene digest de artefacto — se marcan
`staging: true`, se **omiten de `platform_downloads` y
`download_url`**, y no son instalables por construcción: sin digest,
sin instalación.

### 5.2 El digest del artefacto, y hacia dónde pueden apuntar las URL

`artifacts.<key>.sha256` es el `sha256` del archivo `.astraplugin`
completo — el mismo número que el sujeto de la attestation y lo que
hashea el daemon
([`bundle-v2.md` §3.1](bundle-v2.md#31-digest-del-artefacto)). `size` es la
longitud de ese archivo; el schema la limita a 256 MiB.

Cada URL de artefacto **DEBE** ser `https://` y **DEBE** estar bajo el
prefijo que implica su propio objeto `release`:

* `github_release` →
  `https://github.com/<repo>/releases/download/<tag>/`,
* `direct` → el `base_url` del release,

y **DEBE** terminar en el `filename` declarado. Esto se aplica en
`astra-registry/tools/validate.mjs`, no mediante un patrón de schema,
porque un patrón que solo pudiera describir GitHub hacía inexpresable
el caso autoalojado. `direct` existe para catálogos autoalojados y de
staging; la política lo mantiene fuera del catálogo público.

### 5.3 Determinismo — la propiedad en la que se apoya un auditor

El miembro `signed` de `index.json` se genera a partir de
`plugins/**` por `tools/build-index.mjs` y **no lee ningún reloj**:
mismas fuentes + misma serial → mismos bytes. Claves ordenadas por
unidad de código UTF-16, plugins por id, releases por semver.
`--check` falla si el archivo confirmado difiere en un byte, y la CI
lo ejecuta.

`issued_at`/`expires_at` los añade `bot/sign-index.mjs` en el momento
de firmar, no el generador, por dos razones: son propiedades de la
*publicación*, y un generador que leyera un reloj no podría
reproducirse. Esto es lo que hace posible en absoluto la auditoría del
§8 — un tercero puede reconstruir el contenido del catálogo a partir
del árbol git y compararlo con lo que se firmó.

### 5.4 Serial

* **Monótona**, derivada de `git rev-list --count HEAD -- plugins` en
  la rama por defecto. Nunca leída-e-incrementada de un archivo: dos
  merges en el mismo minuto leen ambos *N* y escriben ambos *N+1*, y
  el segundo deshace en silencio el incremento del primero. Un conteo
  de commits es una propiedad de la historia, así que los merges
  concurrentes obtienen valores distintos por construcción. Limitar
  por ruta significa que un commit de docs no mueve el número de
  versión del catálogo.
* Un verificador mantiene un **piso de serial** por URL de catálogo y
  rechaza cualquier cosa por debajo. El piso es
  `max(en memoria, en disco)` y vive en estado que posee el daemon,
  con MAC (`astra.registry.state/1`), **no** en la caché del índice:
  la caché es una conveniencia que puede borrarse en cualquier
  momento, y el piso es una decisión de seguridad que debe sobrevivir
  exactamente al borrado que realizaría un atacante. Es monótono *en
  código*, así que corromper el archivo de estado reinicia el archivo
  y no el proceso en ejecución.

Tres documentos, tres reglas de serial, y las diferencias son
deliberadas:

| documento | se acepta cuando | por qué |
|---|---|---|
| `trust.json` | **estrictamente mayor** que lo que se tiene | solo cambia en una rotación de clave, así que "misma serial, bytes distintos" es un intento de rollback y nada más |
| `index.json` | **no por debajo** del piso | republicación ordinaria |
| `revocations.json` | **mayor o igual** en disco; una serial **estrictamente mayor** reemplaza el conjunto, una menor-o-igual solo puede **añadir** | la lista se refirma según un calendario para mantenerse dentro de su ventana de 7 días; rechazar la igualdad bloquearía instalaciones cada semana tranquila. "Misma serial, menos entradas" es un replay, y solo-añadir lo derrota |

El MAC del archivo de estado es una **alarma, no un límite**: la clave
vive en el mismo directorio 0700 que el archivo que autentica, así
que un atacante que pueda leer ese directorio puede falsificarlo. Sube
el listón de "editar un archivo" a "encontrar y usar la clave". El
límite real es el directorio — un hermano de `plugins/`, nunca un
hijo, así que el sujeto de estas decisiones no es también su autor.

### 5.5 Actualidad, y la asimetría que más importa

| documento | TTL | qué cuesta la obsolescencia |
|---|---|---|
| `index.json` | **30 días** (`CATALOG_TTL_DAYS` / `CATALOG_MAX_AGE_DAYS`) | un **banner**. Browse dice que el catálogo es viejo. **Los registros en caché fijados por digest siguen siendo instalables.** |
| `revocations.json` | **7 días** (`REVOCATION_TTL_DAYS` / `REVOCATION_MAX_AGE_DAYS`) | un **bloqueo duro** de nuevas instalaciones |

Esta asimetría es toda la política de actualidad, y se deriva de para
qué sirve cada documento. Un registro de catálogo es un *digest*, y un
digest no caduca: un atacante que congele el registro para que
mantengas un registro que ya verificaste no gana nada. Una lista de
retirada es lo contrario — "seguir adelante" ahí significa "seguir
instalando algo que quizá ya hayamos retirado" — así que esa es el
bloqueo:

> `REVOCATIONS_STALE: Astra can't check whether this plugin has been withdrawn.
> The withdrawal list it has is N days old and Astra will not install with one
> older than 7 days. Reconnect to the network and try again. Plugins already
> installed keep running.`

Nota la última frase. La obsolescencia nunca detiene un plugin que ya
está en ejecución.

Códigos de veredicto que emite un cliente conforme, más severo primero
(`IndexVerdict::code`):

| código | significado |
|---|---|
| `SIGNATURE_INVALID` | se ofrecieron firmas y ninguna la hizo una clave de confianza. **El único código que significa manipulación.** No hay ningún reloj involucrado en llegar a él, así que ningún reloj puede excusarlo. |
| `SIGNATURE_KEY_EXPIRED` | una clave delegada lo firmó, fuera de su ventana, juzgado con un `Date` de servidor en mano (así que el desfase no es una explicación) |
| `CLOCK_SKEW` | el reloj de esta máquina y las marcas de tiempo del documento no pueden estar ambos en lo correcto, y la firma verificó — así que el reloj es el sospechoso |
| `CATALOG_STALE` | pasado `expires_at` |
| `FRESHNESS_UNKNOWN` | sin `issued_at` y sin `expires_at` — un catálogo local escrito a mano |
| `UNSIGNED` | sin firmas, o sin ancla de confianza contra la que comprobarlas |

`SIGNATURE_INVALID` y `SIGNATURE_KEY_EXPIRED` son **rechazos**: el
documento no se lee en absoluto, y no se ofrece ningún respaldo en
caché para él. `UNSIGNED` no es un rechazo — es el estado previo a la
ceremonia del mundo y de cada catálogo local — pero nunca puede
ascender un registro a totalmente confiable.

De **dónde** se obtuvo un documento nunca es una entrada. Se cree en
un catálogo porque una clave delegada lo firmó; `plugins.registry_url`
es configuración ordinaria y se espera que el catálogo cambie de host.
La ruta de verificación del daemon no contiene ninguna comprobación de
nombre de host y no debe adquirir una.

## 6. `revocations.json`

### 6.1 Forma

```json
{ "signed": {
    "schema": "astra.registry.revocations/1",
    "serial": 12,
    "issued_at": "…", "expires_at": "…",
    "revocations": [
      { "kind": "digest", "value": "<64 hex>",
        "id": "ASTRA-2026-0001", "severity": "critical", "action": "disable",
        "reason": "Exfiltrated conversation history to an attacker-controlled host.",
        "advisory_url": "https://…" }
    ] },
  "signatures": [ … ] }
```

Generado a partir de un archivo por advisory bajo
`astra-registry/tools/revocations/` por `tools/build-revocations.mjs`;
un advisory se convierte en una entrada por cada clave que nombra, y
cada entrada lleva el id, severidad, acción, motivo y URL del
advisory, porque un cliente muestra exactamente uno de ellos — el
primero que coincida — y cada uno debe valerse por sí mismo. Las
entradas se ordenan por `(kind, value)`, así que el documento es
determinista.

### 6.2 El vocabulario de tipo (kind)

`RevocationKind` en `astra-daemon/src/plugins/trust.rs` es la
autoridad; la tabla `KINDS` del registro existe para que un registro
no pueda publicar un kind que el daemon ignoraría en silencio — un
kind desconocido es una retirada que no ocurre.

| kind | `value` | coincide con |
|---|---|---|
| `digest` | 64 hex minúscula | `sha256` de un `.astraplugin` completo, comparado sin distinguir mayúsculas |
| `binary` | 64 hex minúscula | `sha256` de un **archivo `entry.command` resuelto** |
| `id` | id del plugin | cada versión de ese plugin |
| `id_version` | `<id>@<semver>` | ese release exacto |
| `version_range` | id del plugin + ventana `versions` | ver §6.3 |
| `identity` | `github:owner/repo` o `origin:host` | una identidad de publicador fijada |
| `publisher_key` | un id de clave | el `signer_key_id` de un registro de confianza |

`action` es `block_install`, `disable` o `warn`. `warn` no bloquea una
instalación; `disable` también detiene y desactiva una copia ya
instalada. `severity` (`critical` / `high` / `moderate` / `low`) es
solo informativa — ningún comportamiento depende de ella.

`reason` se muestra a un usuario **textualmente** en una notificación
que el daemon marca como persistente, así que el generador rechaza
texto que contenga overrides bidi o joiners de ancho cero, y lo limita
a 300 caracteres.

### 6.3 Ventanas de versión

La forma y semántica de OSV: `introduced` es **inclusivo**, `fixed` es
**exclusivo**, ambos opcionales, y `{}` significa toda versión — lo
que hace de `version_range` una generalización estricta de `id`.
`introduced == fixed` no cubre nada y se rechaza en el momento de
construir.

El orden es la precedencia semver estándar, así que
`1.0.0-rc.1 < 1.0.0`: un advisory que diga "corregido en 1.0.0" no
debe dejar a `1.0.0-rc.1` sin revocar. Los metadatos de build se
ignoran (semver §10). **Un string de versión que ninguno de los dos
lados pueda analizar está *dentro* de la ventana** — la alternativa es
que `version = "totally-fine"` se cuele por cualquier límite que un
advisory pudiera expresar, y el atacante elige ese string.

### 6.4 La verificación es estricta, a diferencia de la del catálogo

`verify_index_document` devuelve un veredicto gradual;
`verify_revocations_document` devuelve `Err`. Sin ancla de confianza,
sin firma, una firma de un desconocido, o una firma de una clave fuera
de su ventana son todos fallos. Una lista de retirada solo se
consulta para *rechazar* algo, así que un documento que nadie puede
atribuir tiene exactamente una lectura segura — "esto no es una lista
de retirada" — y devolverlo como un conjunto vacío sería el resultado
preferido del atacante, alcanzable sirviendo cualquier archivo en
absoluto.

La ausencia de una lista utilizable se maneja un nivel por encima, con
el bloqueo de 7 días (§5.5). Eso, y no un parser permisivo, es lo que
evita que una caída del registro se convierta en una pérdida
silenciosa de aplicación.

Una lista en caché se **vuelve a verificar en cada carga**, nunca se
confía solo porque este daemon la escribió alguna vez — lo que le
permite a la copia en caché ser una entrada de nivel instalación, y
por qué una rotación de clave retira la lista en caché en el mismo
momento en que retira una en vivo.

### 6.5 La brecha del sideload, cerrada en el origen

Un advisory solo por digest deja un agujero por defecto: retirar por
digest, y un usuario puede desinstalar (descartando el registro de
confianza del que se leyó el digest), copiar `plugin.toml` y el
binario a un directorio, y hacer sideload del mismo código. Un
directorio no tiene archivo, así que no tiene digest de paquete ni
firmante.

El generador por tanto **rechaza un advisory cuyas entradas se basen
todas en algo que un directorio no puede tener.** Al menos una entrada
**DEBE** ser de tipo `binary`, `id`, `id_version` o `version_range`.
`identity` y `publisher_key` explícitamente no cuentan.

Cinco puntos de aplicación consumen la lista: instalación (§5.3-A.4
del plan), resolución de actualización, la vía de importación, la vía
de sideload, y la intersección periódica de la lista con los plugins
instalados por `artifact_sha256` registrado.

## 7. Procedencia — lo que comprueba el registro que el daemon no puede

### 7.1 En la ingesta (bot del registro, `bot/lib/attestation.mjs`)

1. `gh attestation verify <file> --repo <repo> --signer-workflow <path>
   --format json`. Esto demuestra que un workflow en ese repositorio
   compiló estos bytes y que Sigstore lo registró.
2. **El digest del sujeto de la attestation DEBE ser igual al
   `sha256` del artefacto** — el tercero de los tres lugares de ese
   número (`E_ATTESTATION_SUBJECT_MISMATCH`).
3. El repositorio de origen del certificado DEBE ser
   `https://github.com/<repo>` (`E_ATTESTATION_REPO_MISMATCH`).
4. El **SHA de commit del workflow reutilizable resuelto** se relee
   del certificado y DEBE aparecer en `reusable_workflow_shas` de
   `trust.json` (`E_WORKFLOW_NOT_ALLOWED`). Un SHA faltante es un
   fallo, no un valor por defecto (`E_ATTESTATION_INVALID`).

El paso 4 es lo que hace que una etiqueta `@v1` mutable sea inutilizable
como cadena de suministro: una etiqueta puede reapuntarse a cualquier
commit y la attestation seguiría nombrando el repositorio y archivo de
workflow correctos. Cambiar esa lista blanca es una ceremonia de clave
raíz.

Esa lista blanca ya existe: el `trust.json` firmado nombra exactamente
un commit, `e3329df252a46d747676cb540ae4b986af68a3ad`. Así que
`E_TRUST_UNPROVISIONED` ya no detiene la ingesta, y el paso 4 está
activo — un build producido por cualquier otro workflow se rechaza con
`E_WORKFLOW_NOT_ALLOWED`. La mitad del lado del daemon sigue fallando
cerrada por una razón distinta: el propio catálogo no lleva firma
(§0.1).

### 7.2 No implementado: la contrafirma por release

`PRODUCTION_PLAN` §5.2 especifica una contrafirma por release sobre

```
SHA256("astra-registry-countersign-v1" ‖ 0x00 ‖ id ‖ 0x00 ‖ version ‖ 0x00 ‖ platform ‖ 0x00 ‖ artifact_sha256)
```

**Nada calcula ni comprueba esto hoy.** El string aparece en el plan y
en ningún lugar de ninguno de los tres repositorios. La autenticidad
de un registro hoy proviene de la firma del sobre del índice, que
cubre todo el catálogo. No implementes un verificador contra esta
sección esperando encontrar tal campo.

### 7.3 Lo que hace el daemon en su lugar

El daemon no realiza **ninguna** verificación de Sigstore: las
attestations se comprueban en la CI del bot, donde existen la red, la
API de GitHub y `gh`. Localmente hace dos cosas, y su combinación es
lo que acota una compromisión de la clave del registro a "publicar
plugins nuevos":

* **Fijado TOFU.** En la primera instalación registra la identidad
  que declaró el listado (`{kind: "github", repo}` o
  `{kind: "origin", host}`). Una actualización cuya identidad
  difiera es un **bloqueo duro sin anulación, nunca**.
* **Vinculación URL-vs-identidad.** La URL del artefacto debe vivir
  bajo el espacio de nombres de releases del repositorio fijado,
  comparado en host y prefijo de ruta tras la resolución de
  redirecciones. La identidad es el repo que **declara** el registro,
  nunca el repo que implica la URL — derivarla de la URL haría la
  comprobación tautológica en una primera instalación.

Riesgo residual, indicado porque la UI no debe exagerar: `identity` es
un string que afirma el registro. Una clave de índice comprometida
puede publicar un registro con una identidad verdadera y un bloque de
procedencia fabricado. La comprobación de URL obliga a que los bytes
vengan del espacio de nombres de releases del repo fijado; una
compromisión de repo más registro derrota ambas.

## 8. El procedimiento de auditoría

Todo en el catálogo publicado es verificable por un tercero sin acceso
a ninguna clave privada. Este es el procedimiento. Los pasos marcados
**tooling** tienen un script en `astra-registry`; los pasos marcados
**manual** todavía no, y el `registry/tools/audit-index.sh` nombrado
en `PRODUCTION_PLAN` §5.5 **no existe hoy** — se describe aquí como el
procedimiento que automatizará.

**A. Reproducir el contenido del catálogo.** *(tooling)*

```sh
git clone <registry repo> && cd astra-registry
node tools/build-index.mjs --check          # byte-identical regeneration
node tools/build-revocations.mjs --check
node tools/validate.mjs                     # schema + URL pinning + digests
```

Luego compara el miembro `signed` publicado contra el regenerado,
ignorando solo `issued_at` y `expires_at` (§5.3). Cualquier otra
diferencia es un catálogo que no coincide con su propia historia git.

*Lo que esto imprime hoy* (verificado al escribir este documento):
ambas ejecuciones de `--check` reportan "byte-identical to a fresh
generation" en la serial 1 con 0 firmas, y `validate.mjs` **falla** —
los once listados son entradas en staging sin digest de artefacto, lo
cual rechaza a menos que se pase `--allow-staging`. Esa es la
respuesta correcta para un catálogo cuyos plugins todavía no se han
liberado, y es la razón por la que nada en él es instalable.

**B. Comprobar la cadena de firmas.** *(tooling)*

```sh
node bot/sign-index.mjs --verify registry/v1/index.json --trust registry/v1/trust.json
```

y, a mano, que `trust.json` verifica bajo una clave en
`registry/v1/root.json` cuya huella coincide con la que registra tu
binario de Astra. Recalcula de forma independiente si prefieres:
`SHA-256(domain ‖ 0x00 ‖ JCS(signed))`, verificación Ed25519, según
§2–§3.

*Lo que esto imprime hoy:* `FAIL … no trusted key was supplied
(offered: none; trusted: none)` — no hay ningún `trust.json` que pasar
ni ninguna raíz con la que verificar uno (§0.1). Un verificador que
reportara cualquier otra cosa contra el árbol actual estaría
mintiendo.

**C. Comprobar la serial y la ventana.** *(manual)* `serial` debe ser
≥ la última que viste; `expires_at − issued_at` debe ser 30 días para
el catálogo y 7 para la lista de retirada; `key_id` debe ser una clave
que nombre `trust.json` con una ventana que contenga `issued_at`.

**D. Comprobar cada artefacto contra el registro de transparencia
público.** *(manual)* Para cada release del índice — `<…>` son
marcadores de posición leídos del registro del índice, así que estos
dos comandos son una plantilla, no algo para copiar y pegar tal cual:

```sh
curl -fL -o a.astraplugin "<artifacts.<key>.url>"
sha256sum a.astraplugin                     # must equal artifacts.<key>.sha256
gh attestation verify a.astraplugin \
   --repo <release.repo> \
   --signer-workflow <AstraPlugins>/.github/workflows/plugin-release.yml \
   --format json
```

`--repo` es el repositorio del **autor**, de `release.repo` del
registro del índice. `--signer-workflow` es el workflow
**reutilizable compartido** que lo compiló — el mismo al que
`astra-plugin init-ci` fija al llamador, que el bot mantiene como
`DEFAULT_SIGNER_WORKFLOW` en `astra-registry/bot/ingest.mjs` y que se
comprueba contra un archivo que existe en
`AstraPlugins/.github/workflows/`. Toma el string exacto de esa
constante en lugar de reconstruirlo; una ruta transpuesta no coincide
con ninguna attestation en absoluto, y entonces cada artefacto
honesto parece no tener ninguna.

`gh attestation verify` obtiene el paquete Sigstore para ese digest de
artefacto y lo comprueba contra la raíz de confianza de Sigstore,
**incluyendo la prueba de inclusión en el registro de transparencia
Rekor**. A partir de su salida JSON, verifica a mano lo que verifica
el bot en la ingesta (§7.1): el digest del sujeto es igual al digest
del archivo, el repositorio de origen es el repo que nombra el índice,
y el SHA de commit del workflow firmante resuelto está en
`reusable_workflow_shas` de `trust.json`.

Un registro que el registro publicó para un artefacto **sin**
attestation, o uno cuya attestation nombra un repositorio distinto, es
exactamente la detección a posteriori para la que existe este
procedimiento: nada impide que una clave de registro comprometida
publique un plugin *nuevo*, y la auditabilidad es toda la mitigación.

**E. Comprobar el paquete mismo.** *(tooling)* Ejecuta
[`bundle-v2.md` §13](bundle-v2.md#13-el-algoritmo-de-verificación) sobre
el archivo descargado, y confirma que su `MANIFEST.json`
`plugin_id`, `version`, `platform` y `permissions_hash` concuerdan con
el registro del índice.

## 9. Resumen de lo que está en vigor hoy

| propiedad | estado |
|---|---|
| formatos de documento, sobre, construcción de firma, perfil JCS | implementado en ambos extremos, probado de forma cruzada por fixture |
| claves raíz | **aprovisionadas** el 2026-08-11 — las mismas dos en ambos lados |
| `trust.json` | **firmado** bajo `astra-root-2026a`, delegando en `astra-index-2026a` y con un commit de workflow en lista blanca |
| firmas de `index.json` / `revocations.json` | arrays vacíos en el árbol confirmado — **este es ahora el enlace que falta** |
| veredictos de catálogo, pisos de serial, actualidad, manejo de reloj | implementado en el daemon y bajo prueba |
| vocabulario de revocación, coincidencia, cinco puntos de aplicación | implementado; **inerte hasta que se obtenga una vez una lista con firma válida** |
| comprobación de attestation de compilación en la ingesta | implementado y activo; la lista blanca de workflow viene del `trust.json` firmado |
| contrafirma por release | especificada solo en el plan; **sin implementación** |
| `audit-index.sh` | no existe; el §8 es el procedimiento manual |

---

*Fuentes comprobadas al escribir este documento:
`astra-registry/schema/{index-v1,version-v1,plugin-v1}.json`;
`astra-registry/tools/lib/canonical.mjs`; `astra-registry/tools/lib/revocations.mjs`;
`astra-registry/tools/build-index.mjs`; `astra-registry/bot/lib/sign.mjs`;
`astra-registry/bot/sign-index.mjs`; `astra-registry/bot/lib/attestation.mjs`;
`astra-registry/registry/v1/{root,index,revocations}.json`;
`astra-registry/SECURITY.md`;
`Astra/astra-rs/astra-daemon/src/plugins/trust.rs`;
`Astra/astra-rs/astra-daemon/src/plugins/registry_client.rs`;
`Astra/astra-rs/astra-daemon/src/plugins/manager.rs` (`refresh_revocations`).*
</content>
