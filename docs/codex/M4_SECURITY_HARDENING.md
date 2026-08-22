# M4 agent-loop security hardening

Fecha de verificación: 2026-08-22.

## Threat matrix

| Threat | Garantía host-side | Test determinista | Resultado |
|---|---|---|---|
| instrucciones en record/source | se serializan dentro de `untrusted_data`; `ToolSpec` procede sólo del registry | `test_prompt_injection_remains_untrusted_data_and_cannot_expand_tools` | PASS |
| secreto/path bajo claves sensibles | redacción por clave y rechazo de capability names no lógicos antes del spawn | `test_prompt_injection_remains_untrusted_data_and_cannot_expand_tools`, `test_unsafe_instance_capability_fails_before_provider_spawn` | PASS |
| tool desconocida o path libre | alias inverso allowlisted + input Pydantic `extra=forbid` | `test_invented_tool_or_free_path_input_fails_closed`, `test_malicious_tool_inputs_fail_closed` | PASS |
| input extra, oversized o deeply nested | caps por binding, total bytes y profundidad antes del handler | `test_malicious_tool_inputs_fail_closed`, `test_deeply_nested_tool_input_fails_before_schema_or_handler` | PASS |
| `SourceRef` stale/manipulada | root/fingerprint se revalidan; no se añade Evidence checked | `test_stale_or_manipulated_source_ref_never_adds_checked_evidence` | PASS |
| duplicate/replay o budget agotado | call id y contadores se consumen host-side por turn | `test_duplicate_and_post_budget_calls_do_not_reach_handler`, `test_duplicate_dynamic_call_does_not_execute_handler_twice` | PASS |
| call/request de otro turn | threadId/turnId/request id se correlacionan y el turn se interrumpe | `test_forbidden_or_cross_turn_notifications_interrupt` y tests del bridge dinámico | PASS |
| output tool malformed/oversized | output schema + caps antes de ledger/response | `test_malformed_or_oversized_tool_output_never_enters_evidence` | PASS |
| command, file change, approval o evento inesperado | allowlist de eventos; server requests no-tool se deniegan; nunca se auto-aprueba | `test_forbidden_or_cross_turn_notifications_interrupt`, `test_approval_request_is_denied_and_never_auto_approved` | PASS |
| acceso directo al checkout | cwd aislado, roots vacíos y el source exacto sólo se devuelve tras `source.read_excerpt` | `test_fake_codex_completes_three_source_tool_roundtrips` | PASS |
| tool bloqueada o colgada | timeout por tool cancela el handler con ownership del task | `test_per_tool_timeout_cancels_owned_handler` | PASS |
| event flood/backpressure | frame/stdout caps del runtime + `max_events` + deadline total + interrupt/cleanup | `test_event_flood_is_bounded_and_interrupts`, runtime timeout/termination tests | PASS |
| JSON/action/evidence refs manipulados | schema Pydantic, workflow M4 read-only y ledger UUID del mismo turn | `test_invalid_structured_output_fails_closed`, `test_proposed_action_is_rejected`, `test_invented_final_evidence_ref_is_rejected` | PASS |
| high confidence sin record+source checked | se reduce a `medium` y se añade limitación | `test_high_confidence_is_degraded_when_source_is_unavailable` | PASS |
| citation metadata falsa | el modelo sólo aporta UUID; metadata browser-facing se reconstruye desde Evidence checked | tests de `_validated_answer`/citas de `test_explain.py` | PASS |
| HTML/script en answer | Owl usa `t-esc`; no existe `t-raw`/`innerHTML` en el panel | `assistant_panel_service.test.js` | PASS |
| canarios en outputs/traces/Diagnostics | serializers, schemas, trace attributes y status público son acotados/allowlisted | suite security, context, trace y Diagnostics | PASS |

## Budgets efectivos

- Engine: context 64 KiB, output schema 48 KiB, answer 64 KiB, 24 Evidence,
  512 eventos y deadline total configurado para el turn.
- Runtime: frame 256 KiB, stdout acumulado 4 MiB y stderr ring buffer 64 KiB.
- ToolExecutor: 12 calls, 64 KiB input total, 256 KiB output total, 24
  Evidence/192 KiB, profundidad 8, deadline 30 s y timeout por tool 5 s.
- Los límites del turn y de cada binding sólo pueden reducir estos caps.

## Riesgos residuales dependientes del modelo/runtime

- Un modelo puede redactar texto inspirado por evidencia adversarial. El host no
  promete impedir toda frase incorrecta; garantiza que esa frase no amplía tools,
  no crea Evidence y no se acepta con refs inventadas.
- App Server puede intentar iniciar una capability built-in antes de que el host
  observe su evento. El thread usa cwd desechable, roots vacíos, sandbox read-only
  y approval `never`; además el host rechaza el turn completo e interrumpe el
  proceso. El aislamiento fuerte sigue dependiendo de las garantías del runtime y
  del perfil Linux desplegado, por lo que se mantiene como self-test de gate.
- `dynamicTools` sigue siendo experimental y versionado dentro del adapter. Un
  evento nuevo falla cerrado hasta ser revisado y añadido explícitamente.
