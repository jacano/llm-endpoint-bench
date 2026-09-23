# llm-endpoint-bench

Banco de pruebas de **latencia, throughput y TPS** para endpoints de LLM compatibles con OpenAI,
medido con `curl` (sin SDK, sin reintentos que escondan la cola) y con los tokens contados siempre
desde el bloque `usage` de la respuesta — nunca contando líneas SSE.

Incluye los resultados medidos el **2026-09-23** comparando el mismo modelo
(`deepseek-v4.1-flash`) servido por **CommandCode** y por **OpenCode (Go)**:
resumen en [`results/summary.md`](results/summary.md).

---

## Resultados (resumen)

| Métrica | CommandCode | OpenCode (Go) | OpenCode vs CC |
|---|---|---|---|
| TTFB `/models` (conexión nueva) | 47 ms | 460 ms | 9,7x |
| TTFB **conexión reutilizada** (overhead por petición) | **20 ms** | **265 ms** | 13x |
| Respuesta corta: TTFT 1er token / total | 912 / 1046 ms | 1561 / 1792 ms | 1,71x |
| Gen. larga (~620 tok): TTFT visible / total | 1511 / **2673 ms** | 3033 / **4948 ms** | 1,85x |
| **TPS decodificación sostenida** | **360 tok/s** | **230 tok/s** | 1,56x |
| TPS en contenido visible | 439 tok/s | 260 tok/s | 1,69x |
| Prefill 18k tok: TTFT | 1671 ms | 3774 ms | 2,26x |
| 4 concurrentes: agregado | **947 tok/s** · 1,66 req/s | **476 tok/s** · 0,81 req/s | 2,0x |

Conclusión: mismo modelo, infraestructura distinta. CommandCode gana en todo lo medible —
~13x menos overhead por petición, 1,6x más tok/s de decodificación y 2x en agregado concurrente.
OpenCode (Go) añade dos fricciones operativas: la cabecera `x-opencode-session` es obligatoria
(sin ella `400 MissingSessionID`) y su ruta PAYG `/zen/v1` responde `402 Insufficient account funds`
con una clave de suscripción Go.

---

## Requisitos

- `python3` (solo stdlib) y `curl`.
- Claves de API. El script las busca primero en el entorno y, si no, en `~/.hermes/.env`
  (solo se imprimen **nombres** de variable, nunca valores).

| Endpoint (`--endpoint`) | Base URL | Variable de clave | Cabecera extra |
|---|---|---|---|
| `commandcode` | `https://api.commandcode.ai/provider/v1` | `COMMANDCODE_API_KEY` | — |
| `opencode-go` | `https://opencode.ai/zen/go/v1` | `OPENCODE_GO_API_KEY` | `x-opencode-session` (obligatoria) |
| `opencode-zen` | `https://opencode.ai/zen/v1` | `OPENCODE_ZEN_API_KEY` | — |

`python bench.py list` muestra esta tabla desde el propio código.

## Cómo invocarlo

```bash
git clone <este repo> && cd llm-endpoint-bench

# 1) qué endpoints conoce
python3 bench.py list

# 2) benchmark completo de un endpoint (transporte + corta + larga + prefill)
python3 bench.py run --endpoint commandcode
python3 bench.py run --endpoint opencode-go            # añade la cabecera de sesión solo

# 3) solo algunas fases
python3 bench.py run --endpoint commandcode --phases transport,short
python3 bench.py run --endpoint opencode-go --phases short,long

# 4) medición concurrente (N peticiones en paralelo)
python3 bench.py run --endpoint commandcode --phases concurrent --concurrent 4

# 5) A/B intercalado: la carga del proveedor golpea a ambos lados por igual
python3 bench.py ab --a commandcode --b opencode-go --phases transport,short,long --n 4

# 6) agregar cualquier fichero de resultados (mediana, mínimo, máximo)
python3 bench.py report results/ab_commandcode_20260923.json
```

Cada ejecución escribe `results/<endpoint>_<UTC>.json` con `{meta, records}` y, en `run`,
imprime el agregado al terminar.

### Endpoint propio (cualquier API compatible con OpenAI)

```bash
python3 bench.py run \
  --base-url https://api.example.com/v1 \
  --model vendor/model-id \
  --key-env EXAMPLE_API_KEY \
  --tag example
# añade --session-header si el gateway exige x-opencode-session
```

### Invocación mínima a mano (para comprobar una clave o un modelo)

CommandCode:

```bash
curl -sS https://api.commandcode.ai/provider/v1/chat/completions \
  -H "Authorization: Bearer $COMMANDCODE_API_KEY" \
  -H 'Content-Type: application/json' \
  -d '{"model":"deepseek/deepseek-v4.1-flash","messages":[{"role":"user","content":"hi"}],"stream":true}'
```

OpenCode (Go) — sin la cabecera de sesión devuelve `400 MissingSessionID`:

```bash
curl -sS https://opencode.ai/zen/go/v1/chat/completions \
  -H "Authorization: Bearer $OPENCODE_GO_API_KEY" \
  -H "x-opencode-session: $(python3 -c 'import uuid;print(uuid.uuid4())')" \
  -H 'Content-Type: application/json' \
  -d '{"model":"deepseek-v4.1-flash","messages":[{"role":"user","content":"hi"}],"stream":true}'
```

Ojo con el id del modelo: **CommandCode usa el prefijo del proveedor** (`deepseek/deepseek-v4.1-flash`),
OpenCode usa el id pelado (`deepseek-v4.1-flash`). Lista los modelos disponibles con
`curl <base_url>/models` (`/models` en CommandCode es público).

### Usarlo desde Hermes Agent

Los tres endpoints ya tienen perfil de proveedor en Hermes; basta con la variable de entorno
correspondiente y elegir el proveedor por nombre:

- `model.provider: commandcode` + `COMMANDCODE_API_KEY`
- `model.provider: opencode-go` (alias `go`) + `OPENCODE_GO_API_KEY`
- `model.provider: opencode-zen` (alias `opencode`, `zen`) + `OPENCODE_ZEN_API_KEY`

## Qué mide cada fase

| Fase | Peticiones | Para qué |
|---|---|---|
| `transport` | 3 nuevas + 3 reutilizando socket | separa handshake (DNS/TCP/TLS) del overhead por petición del gateway |
| `short` | 5 streaming, `max_tokens=64` | latencia que nota el usuario en una respuesta corta |
| `long` | 4 streaming, `max_tokens=1200` | TTFT desglosado + tok/s sostenido |
| `prefill` | 1 streaming, ~18k tokens de entrada | ¿crece el TTFT con el prompt? |
| `concurrent` | N en paralelo | tok/s agregado y req/s, y si degrada el tok/s por petición |

### Definiciones de las métricas

- `ttft_any_ms` — primer delta de cualquier tipo (razonamiento **o** contenido).
- `ttft_reasoning_ms` / `ttft_content_ms` — primer token de razonamiento / primer token **visible**.
  La diferencia entre ambos es lo que el usuario percibe como "tarda en empezar a escribir".
- `tok_per_s_total` — `completion_tokens / (último delta − primer delta)`: incluye razonamiento.
- `tok_per_s_visible` — tokens de contenido / tiempo de la fase de contenido. Con respuestas de
  2–3 tokens el número no tiene sentido (sale enorme): úsalo solo en generaciones largas.
- `models_reuse.ttfb_ms` — TTFB con el socket ya abierto, es decir el coste fijo del gateway
  por petición (sin handshake ni cola del modelo).
- `concurrent_summary.aggregate_tok_per_s` — suma de tokens de todas las peticiones / wall clock.

## Estructura

```
bench.py                     # runner unificado (esto es lo que se usa normalmente)
results/
  summary.md                 # tablas y conclusiones de la campaña 2026-09-23
  commandcode_single_20260923.json     # caracterización completa de CommandCode (55 registros)
  ab_commandcode_20260923.json         # A/B lado CommandCode
  ab_opencode-go_20260923.json         # A/B lado OpenCode Go
scripts/                     # scripts originales de la sesión (tal cual se usaron)
  probe_commandcode.py       # v1: fases models/tiny/medium/stream
  probe_cc_v2.py             # streaming con `usage` parseado (TTFT desglosado)
  probe_concurrent.py        # concurrencia N en paralelo
  diag_commandcode.py        # ¿el SSE trae usage? ¿el toggle thinking hace algo?
  aggregate_commandcode.py   # agregado de la sesión de caracterización
  ab_cc_vs_opencode.py       # A/B intercalado (origen de los dos ficheros ab_*)
  ab_concurrent.py           # concurrencia A/B back-to-back
  agg_ab.py                  # tabla comparativa lado a lado
```

`bench.py` es la versión consolidada y probada de esos scripts; se conservan los originales por
trazabilidad.

## Trampas aprendidas (y por qué el código hace lo que hace)

- **Las líneas SSE no son tokens.** El gateway emite deltas vacíos, deltas de razonamiento y a veces
  agrupa varios tokens por chunk: contar líneas subestima o sobreestima según el momento. Los tokens
  salen del `usage` final (`completion_tokens` + `completion_tokens_details.reasoning_tokens`).
- **Sin streaming, TTFB == total** (el cuerpo llega de golpe), así que el "tok/s sin TTFT" calculado
  sobre una respuesta no-streaming es basura. Para eso está el streaming.
- **`thinking: {"type": "disabled"}` no desactiva nada** en esta ruta, y `reasoning_effort` no mostró
  efecto: no esperes bajar la latencia por ahí.
- **`x-opencode-session` es obligatoria en OpenCode Go** (`400 MissingSessionID`) y hay que mandar UA
  de navegador: `urllib`/UA de python recibe `403`.
- **`curl` con varias URLs y un solo `-o`**: el segundo cuerpo se imprime en stdout y se pega al
  número del `-w`. Un `-o /dev/null` por URL (así lo hace `bench.py`).
- **Intercala A/B** (`A,B,A,B…`): bloques secuenciales confunden la comparación con la carga variable
  del proveedor.
- **Normaliza por tokens, no por tiempo**: dos endpoints nunca emiten el mismo número de tokens para
  el mismo prompt.

## Salvedades

Campaña de ~10 min por sesión, n=1–6 por escenario, desde una sola máquina. Los ratios ±10 % son
ruido; la cola del proveedor varía entre ventanas (TTFT de 620 a 2660 ms en el mismo endpoint con el
mismo prompt). No se probaron reintentos, tool-calling ni streaming con herramientas. Fechas y
versiones de modelo caducan: vuelve a medir antes de tomar una decisión de coste o de ruta.

## Licencia

MIT (ver `LICENSE`).
