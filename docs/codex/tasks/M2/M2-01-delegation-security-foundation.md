# M2-01 — Foundation de delegación firmada y contratos de transporte

## Contexto

- Requiere M1 completado y `docs/M1_GATE_REPORT.md` en PASS.
- Lee el Source of Truth, `docs/ARCHITECTURE.md`, `AGENTS.md`, `addons/AGENTS.md`, `service/AGENTS.md`, `tests/AGENTS.md` y `docs/codex/tasks/M2/README.md`.
- M0 ya define `ScreenContext`, `UserExecutionContext`, `RecordRef`, `RecordSnapshot`, `Evidence` y `OdooGateway`.
- M1 ya proporciona shared secret server-side y autenticación HMAC-safe para endpoints locales. No dupliques secretos sin necesidad.

## Objetivo

Definir e implementar la primitive mínima de delegación firmada y los schemas de transporte necesarios para el vertical slice de M2, demostrando firma, tamper detection y expiración sin implementar todavía ORM, endpoints de tools ni UI.

## Contratos que NO puedes romper

- `ScreenContext` no contiene identidad confiable.
- `UserExecutionContext` representa identidad derivada server-side.
- `contracts` no depende de FastAPI, Odoo, storage ni adapters.
- El shared secret/delegation token no puede aparecer en prompts, traces ni payloads devueltos al browser.
- `ReasoningEngine` no recibe credenciales de transporte.

## Debes reutilizar

- `service/src/odoo_ai/contracts/`;
- `service/src/odoo_ai/security/shared_secret.py` y su política de comparación/secret file;
- `addons/odoo_ai_assistant/services/assistant_client.py` para la configuración server-side existente;
- tests de boundaries y sanitización existentes.

## Debes implementar

### 1. Confirmar el trust model exacto

Antes de decidir la clave de firma, localiza en el Source of Truth la semántica de delegación. Si exige un signer que el Assistant Service no pueda reproducir, respeta esa separación. Si permite reutilizar el secreto local compartido dentro del trust boundary Odoo ↔ Assistant Service, deriva una clave con purpose separation o aplica el mecanismo exacto documentado.

No cambies el trust model por comodidad. Documenta en código/test qué componente es confiable y qué componente no debe ver la credencial.

### 2. Claims mínimos y versionados

Crear una representación interna estricta, JSON-serializable y sin `Any` abierto equivalente a:

- versión del formato;
- `jti`/nonce aleatorio;
- `turn_id` UUID;
- binding de instancia/DB suficiente para impedir cross-database accidental;
- `uid`;
- `company_id`;
- `allowed_company_ids`;
- `lang` opcional;
- modelo permitido;
- IDs de registro permitidos, con límite pequeño;
- scopes explícitos de M2 (`fields_get`/metadata y `read_records` o nombres equivalentes estrechos);
- `issued_at` y `expires_at`;
- límites relevantes del token si el Source of Truth los contempla.

No firmar `display_name` ni datos de negocio como autoridad. La autoridad es identidad + scope; los datos se releen.

### 3. Codec firmado

Implementar un codec pequeño con stdlib cuando sea suficiente:

- canonicalización determinista del payload;
- HMAC seguro o primitive exacta del Source of Truth;
- base64url/encoding sin ambigüedad;
- `hmac.compare_digest` o equivalente;
- validación estricta de versión, tamaños, timestamps, TTL máximo y shape;
- errores tipados/sanitizados que no incluyan token ni secret;
- clock injectable/fakeable para tests.

No introducir JWT/JWK/framework de auth sólo para resolver este token salvo necesidad real demostrada.

### 4. Schemas de transporte M2

Añadir schemas estrechos para el futuro ingress de context-read, sin implementar la ruta todavía. Deben reutilizar `ScreenContext` y `UserExecutionContext` y transportar al menos:

- `turn_id`;
- texto del usuario con límite razonable;
- `screen`;
- `user`;
- token de delegación opaco;
- referencia/config server-side estrictamente necesaria para alcanzar el gateway Odoo si el Source of Truth no define otra resolución.

No meter headers, sockets o clientes HTTP dentro de contracts de dominio.

## Fuera de scope

- derivar el usuario desde una request Odoo;
- routes/controllers Odoo;
- `fields_get` real;
- `read_records` real;
- adapter HTTP `OdooGateway`;
- panel OWL;
- persistencia de chat;
- Codex/ReasoningEngine;
- writes/approvals.

## Restricciones

- no `sudo()`;
- no SQL directo a Odoo;
- no secreto/token en logs, exceptions o reprs;
- no claims de identidad recibidos desde JS;
- no formato de token extensible mediante `dict[str, Any]`;
- no TTL largo por comodidad; la delegación es efímera.

## Tests obligatorios

- roundtrip válido del token;
- modificación de un byte/claim → rechazo;
- firma incorrecta → rechazo;
- token expirado → rechazo;
- versión desconocida → rechazo;
- payload/IDs/scopes fuera de límites → rechazo;
- JSON Schema/serialización de los schemas de transporte;
- prueba de que `repr`/errores no contienen token ni secret;
- suite actual, Ruff y mypy.

## Acceptance criteria

- existe un formato de delegación mínimo, versionado y probado;
- la clave/trust model coincide con el Source of Truth y queda explícito;
- el token queda ligado a identidad, turn y scope contextual;
- el codec rechaza tampering y expiración;
- los schemas M2 reutilizan contratos existentes sin contaminar `contracts` con infraestructura;
- no se ha implementado todavía ninguna lectura Odoo;
- tests verdes.

## Antes de editar

1. Inspecciona security/contracts actuales y evita duplicar primitives de M1.
2. Resume el trust model de delegación que exige el Source of Truth.
3. Señala si el shared secret de M1 puede o no reutilizarse y por qué.

## Después

1. Ejecuta tests/lint/type-check.
2. Informa claims finales, TTL y primitive de firma.
3. Indica explícitamente dónde vive la clave y qué componentes pueden verla.
4. No avances a M2-02.
