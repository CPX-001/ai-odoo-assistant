# Instrucciones del repositorio

## Flujo Git

- Trabajar siempre directamente sobre `main`.
- No crear ramas de trabajo, ramas de feature ni pull requests para cambios ordinarios.
- Hacer commit y push directamente a `main` después de verificar los cambios.
- Usar otra rama únicamente cuando el usuario lo ordene explícitamente para una tarea concreta.

## Fuente de verdad

- `docs/source-of-truth/Odoo_AI_Assistant_Source_of_Truth_v1.0.pdf` es la especificación principal.
- `docs/ARCHITECTURE.md` es una referencia operativa resumida, no un sustituto.
- Todo cambio de una invariante arquitectónica requiere un ADR y la actualización explícita del Source of Truth cuando corresponda.
- No reinterpretar decisiones cerradas sin nueva evidencia. Señalar cualquier conflicto antes de continuar.

## Filosofía

**Evidencia determinista primero; LLM después.**

Priorizar corrección, seguridad, simplicidad, capacidades nativas de Odoo, reutilización selectiva, un MVP funcional y mantenibilidad. Evitar sobrearquitectura, abstracciones especulativas, frameworks universales prematuros y refactors grandes sin necesidad.

## Plataforma inicial

- Odoo 18 Community.
- Linux self-hosted.
- PostgreSQL.
- Monorepo propio.
- Odoo addon + Assistant Service local.
- Codex App Server como primer `ReasoningEngine`.

## Invariantes de seguridad

Nunca introducir como arquitectura normal:

- `sudo()` para tools del agente.
- SQL directo del Assistant Service contra la DB productiva de Odoo.
- Shell libre, SQL arbitrario o Python arbitrario para el agente.
- `execute_method` / `execute_kw` genérico como tool del modelo.
- Identidad de usuario confiada desde JavaScript.
- Secretos dentro de prompts.
- Writes sin validación adecuada.

La identidad efectiva del usuario y las ACL/record rules de Odoo son autoritativas.

## Arquitectura

```text
Odoo addon
    ↓
Assistant Service
    ↓
Evidence / Tools / Reasoning
```

Codex es un adapter inicial, no el centro de la arquitectura. Los schemas Odoo se descubren en runtime; no crear clases por versión como `SaleOrder18`, `SaleOrder19` o `AccountMove18`.

## Desarrollo

Trabajar por milestones y task packets pequeños.

Antes de editar:

1. Inspeccionar el repo real.
2. Leer los `AGENTS.md` aplicables.
3. Leer documentación y ADRs relevantes.
4. Resumir brevemente el estado actual.
5. Detectar conflictos con el Source of Truth.

Después de editar:

1. Ejecutar las verificaciones disponibles.
2. Informar qué cambió.
3. Indicar las decisiones tomadas.
4. Indicar riesgos o trabajo pendiente.
5. No declarar la tarea completada si falta una verificación relevante.
