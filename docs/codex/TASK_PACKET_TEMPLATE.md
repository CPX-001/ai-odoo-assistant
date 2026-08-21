# PROMPT CODEX - MILESTONE &lt;ID&gt;

## Contexto

- Lee `docs/ARCHITECTURE.md` y ADRs relevantes.
- Si la task toca instalación, source, logs, filesystem, servicios o PostgreSQL, lee también `docs/DEPLOYMENT_CONFIG.md`.
- Inspecciona el repo real antes de modificar.

## Objetivo

- &lt;resultado observable único&gt;

## Contratos que NO puedes romper

- &lt;files/contracts&gt;

## Debes reutilizar

- &lt;componentes existentes/donors ya incorporados&gt;

## Debes implementar

- &lt;scope concreto&gt;

## Fuera de scope

- &lt;lista explícita&gt;

## Restricciones

- no `sudo()`;
- no direct Odoo SQL;
- no version checks in `application`;
- preserve current-user semantics;
- no convertir paths, nombres de servicios, usuarios, logs, addons o endpoints del entorno DEV en contratos del producto;
- defaults de deployment sólo como hints/configuración sustituible.

## Tests obligatorios

- &lt;commands&gt;
- si la task toca deployment: incluir al menos un fixture/layout no-default relevante.

## Acceptance criteria

- &lt;checks concretos&gt;

## Antes de editar

1. Resume brevemente el estado real del repo.
2. Señala cualquier conflicto con el Source of Truth.
3. Si aplica, lista assumptions de deployment y clasifícalas como requisito real, default/hint u override configurable.

## Después

1. Ejecuta tests.
2. Informa archivos cambiados, decisiones y riesgos pendientes.
3. Si aplica, lista cualquier assumption de deployment que permanezca y justifícala.
4. No declares done si falta una verificación.
