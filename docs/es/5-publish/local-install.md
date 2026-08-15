> **Traducción.** Esta es una traducción. Si hay alguna discrepancia, [`docs/en`](../../en/5-publish/local-install.md) es la referencia autorizada.

# Instalar un archivo `.astraplugin` local

**Avanzado, y te cuesta cuatro permisos.** Esta página describe importar un
paquete que llegó fuera del registro — te lo envió un colega, lo compilaste
tú mismo, un release aún no está listado. No es así como se instalan los
plugins; [esa es la tienda](get-listed.md), donde el artefacto se fija por
digest y los fallos de verificación son bloqueos duros.

> **Entregarle a alguien este archivo no es publicar tu plugin.** Un
> paquete que compilaste y enviaste no lleva attestation de compilación ni
> registro en el registry, así que se instala en un nivel reducido en la
> única máquina a la que lo enviaste y no llega a nadie más. Publicar es
> un release etiquetado que la CI compila y certifica, más una única
> solicitud de listado —
> [todo el recorrido en una página](../publishing.md).

## Qué es

`PluginService.ImportPluginFile` toma una **ruta a un archivo
`.astraplugin`** — no los bytes, y no un directorio. La interfaz de Astra
lo llama cuando eliges un archivo.

El paquete es un ZIP con `MANIFEST.json` como su primera entrada,
almacenada. El daemon vuelve a derivar cada digest, comprueba que la lista
de archivos es exhaustiva en ambas direcciones, y rechaza cualquier cosa
que no coincida. `astra-plugin verify` ejecuta las mismas comprobaciones
en local, y deberías ejecutarlo antes de importar un archivo que te envió
alguien ([instala la CLI](../install-cli.md) si no la tienes):

<!-- doctest: cli -->
```bash
astra-plugin verify some-plugin-0.3.0-linux-x64.astraplugin
```

## El techo: cuatro permisos se rechazan de plano

Un archivo importado no tiene registro en el catálogo, así que nada
contrafirmó sus bytes y nada fijó a su autor. Se instala en el **nivel
2**, y el techo de ese nivel no es un aviso — los permisos se
**descartan**:

| Rechazado, pida lo que pida el manifiesto | Por qué |
|---|---|
| `send_chat_message` | Impulsa un turno de IA como si hubiera hablado el usuario |
| `set_theme_contribution` | Cambia el estilo de toda la app |
| `dom_access` | Ejecuta el código del plugin dentro de la ventana de Astra |
| `client` | Se convierte en un frontend de chat con su propia sesión |

`fire_trigger`, `subscribe_events`, `set_variable` y `push_to_ui`
sobreviven al techo — son el extremo de **bajo riesgo** del vocabulario,
por lo que dejarlos pasar no necesita que un listado responda por ellos.
De los cuatro, solo `push_to_ui` recibe su propia casilla de
consentimiento.

Las dos listas son deliberadamente distintas, y vale la pena ser preciso
sobre cuál es cuál:

| Lista | Miembros | Qué decide |
|---|---|---|
| `HIGH_RISK_PERMISSIONS` | `send_chat_message`, `push_to_ui`, `set_theme_contribution`, `dom_access`, `client` | cada uno recibe su **propia casilla de consentimiento**, en cada vía de instalación |
| `TIER2_REFUSED_PERMISSIONS` | `send_chat_message`, `set_theme_contribution`, `dom_access`, `client` | se **descartan de plano** en un archivo importado a mano, haya o no consentimiento |

Difieren en exactamente un id: `push_to_ui` vale una casilla y no vale la
pena rechazar un archivo que el usuario eligió deliberadamente importar —
solo envía eventos a los propios paneles del plugin y a ningún otro
lugar. Ambas listas están en
`astra-plugin-manifest/src/permissions.rs`, de donde las leen tanto el
daemon como la CLI y el registro, así que no puede surgir una tercera
lista.

Un plugin que necesite uno de los cuatro rechazados no puede entregarse
por esta vía. Puede
[cargarse por sideload durante el desarrollo](sideload.md), o listarse.

## Consentimiento, antes de escribir nada

`InspectPluginFile` lee el manifiesto **sin instalar**: no se extrae
nada, nada arranca, no se escribe ningún registro de confianza, no se
copian bytes fuera del archivo. El archivo se analiza en memoria y se
cierra. Llamarlo y luego nunca importar deja la máquina exactamente como
estaba.

Eso es lo que le permite a Astra mostrarte la misma pantalla de permisos
que muestra la vía de la tienda antes de que te comprometas a nada.

## Qué pierdes en comparación con la tienda

| | Tienda | Archivo importado |
|---|---|---|
| Bytes contrafirmados por el registro | sí | no |
| Autor fijado, así que una actualización desde otro repositorio se rechaza | sí | no |
| La retirada (revocación) te alcanza | sí (una vez anclada la cadena) | no |
| Actualizaciones | automáticas, con revisión de cambio de permisos | encuentras tú mismo el siguiente archivo |
| Permisos de alto riesgo | disponibles, con consentimiento | **cuatro se rechazan** |
| Fallo de verificación | bloqueo duro, sin anulación | las comprobaciones del archivo se siguen aplicando |

El plan describe promover un archivo importado a confianza total cuando
su digest aparece en un índice nuevo. **Esa promoción no está
implementada** — una importación permanece en el nivel 2 durante toda su
vida.

## Antes de importar algo que te envió alguien

Un plugin es un proceso nativo con todos tus privilegios de usuario. No
hay sandbox. Importar un archivo es una decisión sobre la persona que lo
envió, no sobre el archivo. [El modelo de seguridad](../1-orientation/security.md)
dice qué demuestran los mecanismos y qué no.

Si es tu propio plugin y todavía lo estás escribiendo, quieres
[`astra-plugin dev`](sideload.md), no esto.
</content>
