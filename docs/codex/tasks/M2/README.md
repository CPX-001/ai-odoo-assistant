# M2 — UI / context / delegation

Estado: completado. M2-01 a M2-09 implementados y verificados; **M2 GATE: PASS**. El siguiente milestone es M3 — Source + logs y no se ha iniciado.

M2 empieza únicamente después del **M1 GATE: PASS**. Su objetivo es demostrar el primer flujo contextual real del producto sin introducir todavía Codex ni un agent loop: desde un registro abierto en Odoo, el usuario puede abrir el asistente, enviar una pregunta y el sistema vuelve a leer ese registro por ORM bajo la identidad efectiva del mismo usuario mediante una delegación firmada y acotada.

Fuente de verdad: `docs/source-of-truth/Odoo_AI_Assistant_Source_of_Truth_v1.0.pdf`, `docs/ARCHITECTURE.md`, `AGENTS.md`, `addons/AGENTS.md`, `service/AGENTS.md` y `tests/AGENTS.md`. Si un task packet entra en conflicto con el Source of Truth, se detiene y se corrige el packet antes de implementar.

Resultado observable del milestone:

```text
usuario abre sale.order
    ↓
panel Odoo-native captura ScreenContext
    ↓
Odoo deriva identidad efectiva server-side
    ↓
Odoo crea delegación firmada y acotada
    ↓
Odoo server llama al Assistant Service
    ↓
Assistant Service usa OdooGateway acotado
    ↓
Odoo relee el pedido por ORM como ese usuario
    ↓
la UI muestra el resultado contextual sanitizado
```

M2 es deliberadamente un **context/read vertical slice determinista**. La pregunta del usuario puede viajar por el flujo y mostrarse en la UI, pero no se implementa razonamiento LLM todavía. M4 incorporará Codex/ReasoningEngine y el agent loop.

## Orden de ejecución

1. [`M2-01-delegation-security-foundation.md`](M2-01-delegation-security-foundation.md) — contrato mínimo de delegación, firma, expiración y schemas de transporte.
2. [`M2-02-server-identity-delegation.md`](M2-02-server-identity-delegation.md) — identidad efectiva y emisión server-side de delegaciones desde Odoo.
3. [`M2-03-delegated-orm-read-tools.md`](M2-03-delegated-orm-read-tools.md) — endpoints internos acotados para metadata y relectura ORM bajo el usuario delegado.
4. [`M2-04-odoo-gateway-http-adapter.md`](M2-04-odoo-gateway-http-adapter.md) — adapter HTTP del `OdooGateway` en el Assistant Service.
5. [`M2-05-context-read-turn-api.md`](M2-05-context-read-turn-api.md) — ingress de turn contextual y orquestación determinista service → OdooGateway.
6. [`M2-06-odoo-assistant-panel-screen-context.md`](M2-06-odoo-assistant-panel-screen-context.md) — panel Odoo-native, captura de `ScreenContext` y bridge browser → Odoo server.
7. [`M2-07-delegation-permissions-security-tests.md`](M2-07-delegation-permissions-security-tests.md) — hardening de delegación, ACL/record rules, campos restringidos y multi-company.
8. [`M2-08-sale-order-e2e.md`](M2-08-sale-order-e2e.md) — vertical slice real desde `sale.order` hasta relectura contextual visible en UI.
9. [`M2-09-gate.md`](M2-09-gate.md) — gate integral y cierre de M2.

Ejecutar una sola task cada vez. Cada task debe inspeccionar el estado real dejado por la anterior, ejecutar sus verificaciones y detenerse. No avanzar automáticamente a la siguiente.

## Invariantes de M2

- El browser aporta navegación y texto del usuario; **no aporta identidad confiable**.
- `ScreenContext` es una pista. El registro se relee siempre por ORM antes de usarlo como evidencia.
- `uid`, compañía efectiva, compañías permitidas y lenguaje se derivan server-side desde Odoo.
- La delegación está firmada, versionada, expira rápido y queda ligada al turn, usuario, compañía, modelo/registro y scopes permitidos.
- El token de delegación y el shared secret nunca llegan al browser, a prompts ni a resultados del modelo.
- Durante M2 sólo existen scopes de lectura/metadata explícitos. No existe ejecución arbitraria de métodos.
- El Assistant Service no recibe credenciales SQL de Odoo y no hace SQL contra la DB productiva.
- Odoo ejecuta lecturas bajo el usuario delegado sin `sudo()` y deja que ACL, record rules, field restrictions y multi-company sean autoritativos.
- `OdooGateway` conserva una superficie pequeña; nunca `execute_kw`, `execute_method`, shell, SQL o Python arbitrarios.
- Los endpoints internos tienen límites de registros, fields, bytes y tiempo; no se convierten en proxies genéricos.
- El ReasoningEngine/LLM no recibe el token de delegación ni secretos de transporte.
- El flujo browser → Odoo → Assistant Service se conserva; el browser no llama a `127.0.0.1:<assistant>`.
- La URL interna de Odoo/Assistant y cualquier dato de deployment siguen siendo configuración server-side, no constantes de JS ni del entorno DEV.
- M2 no implementa source/log providers, Codex, RAG, queries arbitrarias, writes, approvals ni business actions.

## Política de replay en M2

El Source of Truth exige que una delegación expirada o reproducida sea rechazada. Como el vertical slice M2 necesita una llamada de metadata y otra de lectura, el consumo es one-shot por `(jti, scope)`: un token puede usar una vez `fields_get` y una vez `read_records`, siempre dentro de su TTL y sin cambiar turn, DB, usuario, compañías, modelo, IDs ni límites. Repetir cualquiera de esos scopes se rechaza.

El addon conserva únicamente el `jti`, scope y expiración en un ledger técnico ORM con restricción única; nunca persiste el token firmado. Esta semántica no anticipa approvals ni writes de M6.

## Gate de M2

M2 sólo se considera terminado cuando:

- el addon sigue instalando/actualizando en Odoo 18 Community;
- un usuario interno puede abrir el panel del asistente desde un `sale.order` real;
- `ScreenContext` identifica el registro actual sin transportar identidad confiable;
- Odoo deriva `UserExecutionContext` server-side y crea una delegación válida;
- el Assistant Service puede releer únicamente el registro/modelo delegado mediante `OdooGateway`;
- la relectura se ejecuta con ORM bajo el usuario efectivo y respeta permisos reales;
- manipular uid/compañía/modelo/id/tool, firma o expiración no permite escalar acceso;
- el browser nunca ve el shared secret, token de delegación ni endpoint interno sensible;
- el vertical slice funciona con service real y Odoo real, no sólo con mocks;
- tests, lint y type-check siguen verdes y M1 no retrocede.

La evidencia ejecutable y el veredicto final están en
[`docs/M2_GATE_REPORT.md`](../../../M2_GATE_REPORT.md).
