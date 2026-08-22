# M3-04 — Manifest literal y Python AST

## Contexto

- Requiere M3-03 verde.
- El scanner estático nunca importa ni ejecuta addons.
- ERPipe sólo puede reutilizarse según el informe M3-01.

## Objetivo

Implementar extractores estáticos para `__manifest__.py` y Python que produzcan metadata/símbolos con líneas y fingerprints correctos.

## Contratos que NO puedes romper

- extractores reciben un fichero ya validado por el orchestrator;
- no pueden ampliar roots;
- no ejecutan Python;
- output normalizado a contracts M3-02;
- no introducen lógica de workflow/LLM.

## Debes reutilizar

- código MIT aprobado en M3-01 cuando aporte valor;
- `ast` estándar;
- storage/orchestrator M3-02/M3-03;
- hashing común del proyecto.

## Debes implementar

### 1. Manifest extractor

Para `__manifest__.py`:
- parsear AST;
- usar `ast.literal_eval` únicamente cuando el manifest sea literal;
- extraer al menos `name`, `version`, `depends`, `data`, `assets`, `license`;
- manifest dinámico/no literal → resultado `unevaluable`, nunca ejecución/import;
- validar tipos y limitar listas/bytes.

### 2. Python AST extractor

Extraer estáticamente:
- clases Odoo relevantes;
- `_name`;
- `_inherit`;
- fields declarados cuando sean reconocibles;
- métodos;
- decorators;
- imports básicos útiles;
- fichero y rango de líneas.

Para métodos como `sale.order.action_confirm`, generar símbolo con:
- module;
- kind=`method`;
- model;
- name;
- path lógico;
- start_line/end_line;
- fingerprint.

Soportar `_inherit` string y listas/tuplas literales. Metaprogramación desconocida queda sin resolver; no inventarla.

### 3. Provenance

No etiquetar `custom` por nombre de carpeta. Mantener clasificación conservadora:
- oficial confirmado;
- OCA confirmado cuando haya evidencia;
- remote/manifest conocido;
- regla manual;
- `third_party_or_custom`/unknown.

Si no hay evidencia suficiente, usar categoría conservadora.

### 4. Integración incremental

Al cambiar el hash de un `.py`:
- reemplazar símbolos derivados;
- eliminar símbolos que ya no existen;
- no duplicar entradas.

## Fuera de scope

- XML;
- CSV;
- resolver monkey patches/metaprogramación;
- inferir causalidad;
- `read_excerpt`;
- logs.

## Restricciones

- nunca `importlib`, `exec`, `eval` ni importar addon;
- `ast.literal_eval` sólo sobre nodos acotados;
- límites de bytes/nodos por fichero;
- errores de parseo se registran y no abortan todo el scan salvo policy explícita.

## Tests obligatorios

Fixtures:
- manifest literal;
- manifest dinámico;
- clase `_name`;
- clase `_inherit`;
- herencia múltiple literal;
- `action_confirm`;
- syntax error;
- fichero enorme/cap;
- cambio y eliminación de método.

Comprobar:
- líneas correctas;
- fingerprint;
- no ejecución de side effects;
- incremental replace;
- tests/lint/type-check.

## Acceptance criteria

- `action_confirm` fixture queda indexado con modelo/módulo/path/líneas correctos;
- manifests dinámicos no se ejecutan;
- re-scan elimina símbolos stale;
- provenance no afirma “custom” sin evidencia.

## Antes de editar

1. Indica qué piezas del donor se reutilizarán realmente.
2. Define límites del parser.
3. Señala cómo mapearás `_inherit` a modelo(s).

## Después

1. Muestra un símbolo real del fixture.
2. Demuestra que un manifest dinámico no se evalúa.
3. Ejecuta tests.
4. No avances a M3-05.
