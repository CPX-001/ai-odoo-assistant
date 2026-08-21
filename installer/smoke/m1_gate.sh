#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
python_bin="${repo_root}/.venv/bin/python"
ruff_bin="${repo_root}/.venv/bin/ruff"
mypy_bin="${repo_root}/.venv/bin/mypy"
profile="${1:-quality}"

if [[ ! -x "${python_bin}" ]]; then
  echo "Missing ${python_bin}; create the repository virtualenv first" >&2
  exit 2
fi

cd "${repo_root}/service"
export PYTHONPATH="${repo_root}${PYTHONPATH:+:${PYTHONPATH}}"

case "${profile}" in
  quality)
    "${python_bin}" -m pytest
    "${ruff_bin}" check src ../installer ../tests ../addons
    "${mypy_bin}" src
    ;;
  postgres)
    ODOO_AI_RUN_POSTGRES_BOOTSTRAP_TEST=1 \
      "${python_bin}" -m pytest ../tests/integration/test_postgres_bootstrap.py -q
    ;;
  runtime)
    ODOO_AI_RUN_RUNTIME_INSTALL_TEST=1 \
      "${python_bin}" -m pytest ../tests/integration/test_runtime_release_smoke.py -q
    ;;
  systemd)
    ODOO_AI_RUN_SYSTEMD_BOOTSTRAP_TEST=1 \
      "${python_bin}" -m pytest ../tests/integration/test_systemd_runtime.py -q
    ;;
  odoo)
    ODOO_AI_RUN_ODOO_PLACEHOLDER_TEST=1 \
      "${python_bin}" -m pytest ../tests/integration/test_odoo_placeholder.py -q
    ;;
  alternate)
    ODOO_AI_RUN_NONDEFAULT_BOOTSTRAP_TEST=1 \
      "${python_bin}" -m pytest ../tests/integration/test_nondefault_bootstrap.py -q
    ;;
  *)
    echo "Usage: $0 {quality|postgres|runtime|systemd|odoo|alternate}" >&2
    exit 2
    ;;
esac
