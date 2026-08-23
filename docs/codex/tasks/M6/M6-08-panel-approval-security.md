# M6-08 — Panel ACTION, aprobación explícita y hardening

Estado: **implementado y verificado de forma determinista el 2026-08-23.**

## Contexto

- Requiere M6-07 verde.
- El browser sigue hablando únicamente con Odoo.
- Odoo deriva identidad/compañías server-side y llama al Assistant mediante el boundary ya existente.
- La preview y el execution receipt ya existen antes de tocar la UX.

## Objetivo

Integrar ACTION en el panel existente de forma que el usuario pueda solicitar un cambio, inspeccionar una preview exacta, aprobar o cancelar explícitamente y ver el resultado verificado, sin que el browser pueda alterar el payload autoritativo ni disparar commits duplicados.

## Contratos que NO puedes romper

- No browser → Assistant directo.
- No identidad/uid/company confiada desde JS.
- No enviar ACTION authority, delegation tokens ni shared secrets al browser.
- No optimistic success: sólo mostrar éxito cuando M6-06 devuelva verification confirmada.
- `t-esc`/escaping para contenido no confiable.

## Debes reutilizar

- panel Owl actual y `/odoo_ai/v1/turn`;
- workflow routing M5;
- errores sanitizados del bridge/client;
- proposal/preview/execution contracts M6;
- patterns de diagnostics/readiness existentes.

## Debes implementar

### Selección ACTION

Añade `ACTION` como workflow explícito del panel y del router server-side. La selección debe ocurrir antes de construir el turn y nunca provocar una registry union.

La UX debe distinguir claramente:

- respuesta informativa;
- preview pendiente de aprobación;
- ejecutando/verificando;
- verified;
- rejected/cancelled;
- stale/repreview required;
- failed;
- execution unknown/unverified.

### Preview visible

Antes de habilitar aprobación, mostrar al menos:

- target entendible (modelo/registro o label seguro);
- lista exacta de fields afectados;
- before → after;
- warnings/limitations;
- expiración si aplica.

No ocultar cambios secundarios dentro de prose del modelo. El botón de aprobación sólo puede referirse a una proposal persistida válida.

### Approve / Cancel

El browser debe enviar únicamente lo mínimo, por ejemplo `proposal_id` + decisión. Nunca reenviar `values` autoritativos ni un payload editable.

Odoo debe:

1. autenticar sesión `auth="user"`;
2. derivar uid/company/context server-side;
3. resolver la proposal por ID;
4. llamar a la operación determinista M6-07/M6-04..06;
5. devolver sólo receipt/error sanitizado.

Tras el primer click, deshabilita controles para evitar dobles submits. La seguridad real sigue en backend; la desactivación UI es sólo UX.

### Cancel/reject

Cancelar debe persistir una decisión terminal y no realizar write. No basta con cerrar visualmente el modal/panel.

### Stale

Si el backend detecta `stale`, mostrar que la preview ha caducado/cambiado y exigir generar una nueva preview; no ofrecer “force anyway”.

### XSS e injection

- field labels, before/after, record names y respuesta del modelo se renderizan escapados;
- no `t-raw` para contenidos no confiables;
- valores que contengan HTML/script/instrucciones se muestran como datos;
- no incluir secrets ni raw backend errors en DOM/console.

### Diagnostics/readiness

Añade sólo la capability mínima necesaria para exponer si ACTION está disponible/degradada. No convertir esta task en el hardening completo de Settings de M7.

## Fuera de scope

- approval por lotes;
- scheduled actions;
- mobile-specific redesign;
- admin audit explorer;
- policy editor de M7;
- undo automático.

## Tests obligatorios

- ACTION puede seleccionarse sin alterar EXPLAIN/QUERY/HOW_TO;
- browser request de approve contiene sólo proposal id/decision esperados;
- payload/value inyectado por browser se rechaza/ignora y no altera commit;
- doble click/doble request no produce doble write;
- cancel/reject deja record sin cambios;
- stale exige repreview;
- verified sólo aparece tras verification receipt correcta;
- unverified/unknown no se presenta como éxito;
- XSS adversarial en labels/values/model output no ejecuta HTML/JS;
- proposal de otro usuario/DB no puede aprobarse;
- browser network trace sigue siendo sólo browser→Odoo;
- tests JS/Odoo addon + suite/Ruff/mypy aplicables.

## Acceptance criteria

- el usuario ve exactamente qué autoriza antes del commit;
- una decisión explícita y autenticada es obligatoria;
- el browser no puede sustituir el payload aprobado;
- estados de error/ambigüedad se representan sin inducir a pensar que hubo éxito;
- browser boundary M1-M5 permanece intacto.

## Después

1. Captura/documenta el flujo UI final y estados posibles.
2. Verifica con network inspection que no existe browser→Assistant.
3. Ejecuta tests combinados M6-07..M6-08 antes del Goal E2E.
