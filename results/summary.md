# Resultados — deepseek-v4.1-flash: CommandCode vs OpenCode (Go)

Fecha: 2026-09-23 (CEST) · máquina: macOS 26.6.2 · cliente: `curl` con UA de navegador,
desde la misma sesión y en ventanas de tiempo solapadas (A/B intercalado).
Modelo idéntico en ambos: `deepseek/deepseek-v4.1-flash` (CommandCode) / `deepseek-v4.1-flash` (OpenCode).

- Lado CommandCode: 18 peticiones limpias (A/B) + 55 en la sesión de caracterización inicial.
- Lado OpenCode Go: 18 peticiones limpias (A/B) + 4 concurrentes.
- Tokens contados siempre desde el bloque `usage` de la respuesta, nunca contando líneas SSE.

## Tabla comparativa (medianas, A/B intercalado)

| Métrica | CommandCode | OpenCode (Go) | OpenCode vs CC |
|---|---|---|---|
| TLS (conexión nueva) | 24 ms | 200 ms | 8,4x |
| TTFB `/models`, conexión nueva | 47 ms | 460 ms | 9,7x |
| TTFB con conexión reutilizada | **20 ms** | **265 ms** | 13x |
| Respuesta corta: TTFT 1er token | 912 ms | 1561 ms | 1,71x |
| Respuesta corta: TTFT token visible / total | 1044 / 1046 ms | 1785 / 1792 ms | 1,71x |
| Gen. larga (~620 tok): TTFT 1er token | 884 ms | 2052 ms | 2,32x |
| Gen. larga: TTFT token visible | 1511 ms | 3033 ms | 2,01x |
| Gen. larga: total | **2673 ms** | **4948 ms** | 1,85x (+85 %) |
| TPS decodificación sostenida | **360 tok/s** (343–364) | **230 tok/s** (199–269) | 1,56x |
| TPS en fase de contenido visible | **439 tok/s** | **260 tok/s** | 1,69x |
| Prefill 18k tokens de entrada: TTFT | 1671 ms | 3774 ms | 2,26x |
| Concurrencia 4: por petición | 378 tok/s (373–385) | 233 tok/s (215–259) | 1,63x |
| Concurrencia 4: agregado | **947 tok/s · 1,66 req/s** | **476 tok/s · 0,81 req/s** | 2,0x |

## De dónde sale la diferencia

- **~245 ms por petición son overhead fijo del gateway de OpenCode**, no de la red ni del modelo:
  con el socket ya establecido (tres peticiones dentro de una sola invocación de `curl`), `/models`
  tarda 265 ms en OpenCode frente a 20 ms en CommandCode. En el TTFT de respuesta corta ese overhead
  explica el 38 % del hueco (249 ms de 649 ms).
- El resto (~400 ms de TTFT y la diferencia de régimen) es cola/arranque del modelo: OpenCode
  sirve el mismo modelo ~1,6x más lento en decodificación sostenida.
- El volumen de trabajo es comparable (619 vs 650 tok de salida; 120 vs 150 de razonamiento), así
  que la comparación es limpia: la misma respuesta tarda 2,7 s en CommandCode y 4,9 s en OpenCode.
- La varianza de cola es mayor en OpenCode: TTFT 1511–2580 ms frente a 800–1027 ms en CommandCode.

## Concurrencia

| Endpoint | petición individual | 4 en paralelo (agregado) | req/s |
|---|---|---|---|
| CommandCode | 346 tok/s · 0,23 req/s | 947 tok/s | 1,66 |
| OpenCode (Go) | — | 476 tok/s | 0,81 |

Ninguno de los dos degrada el tok/s por petición al pasar de 1 a 4 concurrentes (CommandCode
378 vs 346, OpenCode 233 frente a su régimen individual), es decir el cuello de botella aguanta
al menos 4 en paralelo.

## Hallazgos del modelo (válidos para ambos endpoints)

- **El razonamiento está siempre activo**: incluso `"Reply with exactly: pong"` gasta 10–14 tokens de
  razonamiento antes de responder. En generación larga: 47–668 tokens de razonamiento antes del
  contenido (mediana ~380 en la sesión de caracterización, ~43 % de la salida).
- `thinking: {"type": "disabled"}` **no** desactiva el razonamiento y `reasoning_effort` (low/high)
  no produjo diferencia sistemática: el gateway parece ignorar ambos en esta ruta.
- **Prefill es barato**: en la sesión de caracterización, pasar de 637 a 18 037 tokens de entrada movió
  el TTFT 71 ms (944 → 1015 ms, dentro del ruido). El TTFT es cola + arranque de razonamiento.
  (En la sesión A/B posterior el TTFT con 18k de entrada sí subió, hasta 1671/3774 ms: la cola del
  proveedor domina y varía entre ventanas.)

## Salvedades

- n pequeño por escenario (1–6) y ventana corta (~10 min por sesión): los ratios ±10 % son ruido.
- La tasa depende del tipo de salida (aquí listas de números); prosa o código pueden diferir.
- No se probaron reintentos, tool-calling ni streaming con herramientas, donde un gateway puede
  comportarse de otra forma.
- El TPS "visible" no tiene sentido para respuestas de 3 tokens (sale un número absurdo): úsalo solo
  en generaciones largas.

## Datos crudos en `results/`

| Fichero | Contenido |
|---|---|
| `commandcode_single_20260923.json` | sesión de caracterización completa contra CommandCode (55 registros: transporte, corta, media, streaming, prefill, concurrencia 1 y 4, thinking on/off) |
| `ab_commandcode_20260923.json` | A/B intercalado, lado CommandCode (18 registros) |
| `ab_opencode-go_20260923.json` | A/B intercalado, lado OpenCode Go (18 registros) |
| `<endpoint>_<UTC>.json` | salida de `bench.py run` (formato `{meta, records}`) |
