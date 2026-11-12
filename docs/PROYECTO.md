# Victoria2TGCX — documento único

Actualizado: 2026-11-12. **Este es el único documento de estado.** Todo lo que pasa en el proyecto
(qué está hecho, qué falta, decisiones, próximos pasos) se escribe acá y no en archivos nuevos.
Lo demás que hay en `docs/` son tus documentos de diseño (se dejan como están) y las notas del
agente (`docs/agent-notes/`, no hace falta leerlas). `AGENTS.md` en la raíz son las reglas que sigue Claude.

## 1. Qué es

Submod de Victoria II (3.04 + TGC v2.5.2) que expande la política: leyes negociadas con personajes,
hemiciclo, cabeza de Estado. Además salieron de él mods independientes (ATCU, Province Rename, Volunteers).
Repo: SJTG/victoria2tgcx (rama `master`). Tu copia: `C:\Users\User\Desktop\victoria2tgcx`; juego de prueba: `C:\V2test`.

## 2. Estado

Leyenda: ✅ probado en juego · 🟡 hecho, sin probar en juego · ⬜ no empezado.

### Política (la línea activa)

| Pieza | Estado | Nota |
|---|---|---|
| Hemiciclo (100 escaños, 7 filas, tooltip) | ✅ | queda pulido visual menor |
| Generador de leyes (23 grupos, todas las leyes de TGC) | ✅ | prueba corta; cobertura amplia sin confirmar |
| Pestaña Reforms sigue al juego | ✅ | filas se iluminan según lo que se puede ofrecer |
| Ventana del Bill (nativa, texturas, botones) | ✅ | probada hasta el modelo viejo de favores (2026-11-10) |
| Datos de personajes (`data/tgcx_leaders.txt`) | 🟡 | solo ENG con personajes a mano; **todos los números son provisorios (R9)** |
| Modelo de negociación por personaje (relación 0-10, visión, agenda, bandas, deudas) | 🟡 | script + 29 tests en simulador; el simulador no es el motor real |
| Ventana del Bill con personajes (tarjetas, "What They Ask", Abstain/Aye) | 🟡 | **no compilada para i686**; solo chequeo de tipos |
| Refresco automático de ofertas desde la DLL | 🟡 | idem |
| Script 33 MB → 12 MB (las 46 leyes ya no llevan su propia copia del conteo; la DLL manda Count al ver una ley activa sin id) | 🟡 | tests OK; falta probar en juego que la ventana cuente sola |
| Relación inicial calculada (base + bonus si su ideología gobierna − distancia en la escala izq-der) para personajes automáticos | 🟡 | números provisorios en `data/tgcx_leaders.txt` (`start_relation`); los escritos a mano se respetan |
| Cada tarjeta explica su pedido: "nombre - banda, relation N/10" encima de lo que pide | 🟡 | es texto en la ventana, no un tooltip flotante (el tooltip nativo queda para después) |
| Pestaña Parties (en Politics) | ⬜ | tablero 1b dibujado |
| Columnas "Leader wants / Ideology wants / Party will vote" + lista colapsable | ⬜ | tablero dibujado, sin implementar |
| Cabeza de Estado (cartas) | ⬜ | |
| Eventos/interacciones que cambian la relación, muerte del personaje, marionetas, alianzas, historial del partido | ⬜ | D36, D42, D43 |
| Medición real de partidos por país (CHAR-0) | ⬜ | hace falta para saber cuántos personajes hay |

### Mods independientes

| Mod | Estado |
|---|---|
| ATCU (plantillas de ejército + Conform) | ✅ release 0.0.3 preparada; probada en vanilla, HPM, DoD Fan Fork y TGC 2.5.2; MP sin probar |
| Province Rename Universal | ✅ 0.2.x aceptada; MP sin probar |
| Volunteers (prototipo) | 🟡 envío, batalla y asedio pasaron pruebas de jugador; créditos/visión/ocupación completos sin validar; **MP rechazado** |

## 3. Cómo se prueba lo de Política (cuando estés en tu entorno)

1. `cd rust\tgcx` → `cargo build --release --target i686-pc-windows-msvc`
2. Stage (carpeta fuera del juego, p. ej. `C:\v2stage_bill`): copiar `submod\`, luego
   `python tools\gen_law_catalog.py --release <S> --tgc <TGC>` y `python tools\tgcx_bill_gui.py --stage <S> --tgc <TGC>`
3. `python tools\install_submod.py <mod> --base tgc252 --packages politics --source <S> --dll <tgcx.dll> --backup <nuevo>`
4. Jugar como Inglaterra (tag ENG), abrir una ley, mandar `tgcx.log` + captura del Bill.
   En el log buscar "Bill asked the script to sound out the characters".

## 4. Decisiones vigentes de Política

| ID | Decisión |
|---|---|
| D1 | Solo TGC v2.5.2; nada de TGC entra a git (todo se genera del instalado) |
| D7 | Negociar una ley = relación e ideología (no dinero ni favores acumulados) |
| D24 / D25 | Partido = facción con líder; el bloque sigue al líder de su partido con más escaños |
| D37–D43 | Cada bloque tiene personajes (líder + cabecilla; a mano o automáticos); cada uno tiene **visión** (postura por ley) y **agenda** (leyes que pide); **relación 0-10** con vos define cuánto pide (tamaño del cambio y plazo), nunca un precio; 10 = marioneta, 0 = intransigente; la relación solo cambia por acciones, eventos y quién gobierna (el amigo de mi enemigo es mi enemigo) y se reinicia al morir; marionetas/alianzas muy difíciles (después); historial del partido (después) |
| D10 | Todo en inglés (docs, código). **Este documento está en español a propósito; decime si querés volver al inglés** |

Detalle de diseño (tuyo): `docs/plan-characters-favours-1110.md`, `docs/plan-character-driven-1109-v3.md`, `docs/law-design.md`.

## 5. Próximos pasos (en orden)

1. Compilar y probar el Bill con personajes (sección 3). Lo que busco: que las tarjetas muestren personajes, que los pedidos se lean bien, que Abstain/Aye muevan votos, deudas en "Debts".
2. Revisar los números de `data/tgcx_leaders.txt` (relaciones, pedidos, bandas) y activar con `enabled = yes`.
3. CHAR-0: medir partidos reales por país.
4. Pestaña Parties y columnas de Politics.
5. Relación fuera del Bill: eventos/interacciones (vos listás cuáles).

## 6. Diseño: lo que sigue

### Hecho en este tramo
- Relación inicial calculada, y explicación del pedido en la tarjeta (ver tabla de estado).
- **Tope de deudas:** ya existe: un personaje solo puede tener **una ley debida a la vez** (no acepta otro trato que pida ley mientras le debés una). Efecto de romperla: relación −3 y evento de ruptura. Falta lo grave (ver Radicalización).
- **Tamaño:** el peso venía de que cada una de las 46 decisiones de ley llevaba adentro una copia completa del conteo de votos (~430 KB cada una = 20 MB). Sacada esa copia: 12 MB. Lo que queda: 36 decisiones de trato (~5 MB, cada una revalida la cámara), refresco de ofertas (1,7 MB), votar (1 MB). Se puede bajar más (ver abajo).

### Propuesta A — "Vías" (estilo Frostpunk 2) para subir la relación
Problema: si la relación solo cambia por leyes y deudas, al principio nadie acepta nada. En Frostpunk 2 el motor es elegir entre ideas/tecnologías equivalentes, y cada opción alegra a una facción distinta. Traducido:
- Cada vez que pasa algo elegible (tecnología/invención investigada, ley aprobada, evento), el juego ofrece **2-3 vías con el mismo efecto práctico (a veces)** y cada vía "pertenece" a una ideología o personaje.
- Elegir una vía: relación + con sus partidarios, − con su rival. No cuesta plata ni maná.
- Así la relación sube **por lo que decidís**, no por tiempo, y a la vez te obliga a elegir bando (D38/D41).
- A verificar antes de construir: qué disparadores de evento ofrece Vic2 para "tecnología/invención investigada" (hay que mirarlo con `tgc_scan.py` sobre TGC 2.5.2) y cuáles de las vías tienen efectos realmente equivalentes. Qué vías hay y a quién favorecen lo decidís vos (R9).

### Propuesta B — Radicalización
Un sector al que le rompés deudas o ignorás mucho tiempo (relación en 0-1 sostenida) se **radicaliza**: sus miembros pasan a ser los militantes/revolucionarios.
- Fase 1: el personaje deja de negociar y sube la militancia de sus pops.
- Fase 2 (si seguís sin tocarlo): su facción deja de ser un bloque del hemiciclo y aparece como movimiento/rebeldes de esa ideología.
- Se revierte solo con vías o leyes de su agenda mientras esté en fase 1.
- A verificar: cómo se hace en script de Vic2 (efectos sobre militancia de pops de una ideología, disparar rebeldes). Se mide antes de prometer.

### Propuesta C — Reducir más el script
1. El refresco de ofertas y los tratos revalidan la cámara cada uno con la misma lógica; se puede sacar de los tratos y validarla solo en un punto (menos seguro: guarda contra comandos viejos).
2. Generar tratos solo para los personajes que existen en tu país (hoy hay 36 para todos los bloques posibles).
3. Pasar los números de pasos y plazos a tablas más chicas.
Primero se mide el tiempo de carga con 12 MB; si es aceptable no hace falta tocar nada más.

## 7. Mapa de archivos

| Qué | Dónde |
|---|---|
| Este documento | `docs/PROYECTO.md` |
| Reglas de Claude | `AGENTS.md` |
| Tus documentos de diseño | `docs/plan-*.md`, `docs/law-design.md`, `docs/law-1-affinity-review.md`, `docs/volunteers-design.md` |
| Releases publicados | `docs/release-*` |
| Notas del agente (no leer) | `docs/agent-notes/` |
| Tableros de diseño | artifact de Claude "design canvas" (ver `plan-characters-favours-1110.md`) |
| Historial viejo (reportes, instrucciones, ROADMAP, SUBAGENTS) | solo en git, antes del commit "Docs: un solo documento" |
