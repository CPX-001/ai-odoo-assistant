# M6-03 — Pipeline de preview sin efectos

Estado: **implementado y verificado el 2026-08-23.**

## Contexto

- Requiere M6-01 y M6-02 verdes.
- La preview debe demostrar exactamente qué se pretende cambiar bajo permisos actuales sin ejecutar `write()` ni side effects.
- El commit posterior debe poder detectar si el estado relevante cambió desde esta preview.

## Objetivo

Implementar una preview determinista de `record_patch` bajo el usuario real que revalide target/schema/policy, relea el estado actual, construya un diff before/after bounded y produzca una precondition comprobable para la approval posterior, sin mutar Odoo.

## Contratos que NO puedes romper

- Browser no habla con Assistant directamente.
- M2/M5 authorities siguen read-only y separadas.
- No usar `sudo()` para comprobar acceso o leer estado.
- Una preview no es una simulación de todos los side effects de `write()`; no debe prometer efectos que no pueda verificar.

## Debes reutilizar

- gateway Odoo y machine-auth existentes;
- identidad/companies derivadas server-side;
- schema efectivo de M6-02;
- EvidenceLedger y patrones de Evidence checked cuando apliquen;
- canonical payload/fingerprint de M6-01.

## Debes implementar

### Endpoint/handler de preview estrecho

Implementa una ruta interna específica para preview de record patch. Debe recibir únicamente contratos validados y autoridad de preview apropiada; nunca un método libre.

El lado Odoo debe:

1. resolver el record exacto bajo el usuario real;
2. comprobar acceso de escritura relevante sin hacer write;
3. revalidar ActionPolicy y effective write schema;
4. leer únicamente los fields afectados + metadata mínima necesaria;
5. validar los nuevos valores;
6. devolver estado before y una representación after calculada como datos;
7. generar/permitir generar una precondition fingerprint ligada al estado relevante observado.

### Precondition

Define una estrategia explícita para evitar TOCTOU. Como mínimo el commit posterior debe poder detectar cambios en los datos relevantes aprobados. Puede incluir valores before canónicos y/o metadata estable como `write_date` cuando sea fiable, pero no depender de una señal que no exista en todos los modelos soportados.

Una preview hecha sobre estado A no puede autorizar silenciosamente el mismo payload si el estado relevante pasa a B antes del commit.

### Diff seguro

La respuesta de preview debe incluir sólo información necesaria para que el usuario entienda el cambio:

- target sanitizado;
- field label/name permitido;
- before;
- after;
- warnings/limitations host-controlled;
- proposal fingerprint;
- precondition fingerprint;
- expiry recomendada;
- policy/schema revision.

No devolver tokens, raw contexts, internal endpoints, tracebacks ni fields fuera del write set.

### Evidence

La preview válida genera Evidence checked que documenta el estado observado y el diff. Esa Evidence puede citarse en el workflow ACTION, pero sigue sin conceder write authority.

## Fuera de scope

- persistir approval;
- aprobar desde UI;
- commit;
- verification post-write;
- business methods/actions;
- onchange arbitrario o simulación completa del transaction graph de Odoo.

## Tests obligatorios

- preview válida produce before/after sin alterar DB;
- comprobar explícitamente que `write()` no se invoca en preview;
- model/record/field fuera de schema/policy falla cerrado;
- usuario sin write access no obtiene preview válida;
- record rule y multi-company se respetan;
- tampering del proposal fingerprint falla;
- cambiar estado relevante produce precondition distinta;
- tipos/valores inválidos se rechazan antes de approval;
- values adversariales se renderizan como datos;
- outputs y Evidence quedan bounded/sanitizados;
- regresión M5 read/query/how-to;
- suite, Ruff y mypy.

## Acceptance criteria

- el usuario puede recibir un diff fiable de lo observado sin mutación;
- la preview queda criptográficamente/semanticamente ligada al payload y estado relevante;
- cualquier cambio posterior detectable obliga a revalidar antes del commit;
- aún no existe ninguna vía de commit.

## Después

1. Documenta exactamente qué cubre la precondition y qué no.
2. Explica por qué la preview no ejecuta onchange/write para 'simular'.
3. Ejecuta el conjunto combinado de tests de M6-01..M6-03 antes de iniciar el siguiente Goal.
