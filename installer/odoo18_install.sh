#!/usr/bin/env bash
# Odoo 18 Community installer for Ubuntu 24.04/WSL2.
# Based on the installation flow popularized by Yenthe Van Ginneken, updated
# for systemd, Python virtual environments, idempotent reruns, and this repo.

set -Eeuo pipefail

ODOO_USER="${ODOO_USER:-odoo}"
ODOO_PASSWORD="${ODOO_PASSWORD:-odoo}"
ODOO_HOME="${ODOO_HOME:-/odoo}"
ODOO_VERSION="${ODOO_VERSION:-18.0}"
ODOO_SOURCE="${ODOO_SOURCE:-${ODOO_HOME}/odoo-server}"
ODOO_VENV="${ODOO_VENV:-${ODOO_HOME}/venv}"
ODOO_CONFIG="${ODOO_CONFIG:-/etc/odoo-server.conf}"
ODOO_SERVICE="${ODOO_SERVICE:-odoo.service}"
ODOO_PORT="${ODOO_PORT:-8069}"
ODOO_ADMIN_PASSWORD="${ODOO_ADMIN_PASSWORD:-admin}"
CUSTOM_ADDONS="${CUSTOM_ADDONS:-${ODOO_HOME}/custom/addons}"
ASSISTANT_NAME="${ASSISTANT_NAME:-ai-odoo-assistant}"
SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)"
ASSISTANT_SOURCE_DIR="${ASSISTANT_SOURCE_DIR:-$(cd -- "${SCRIPT_DIR}/.." && pwd -P)}"
ASSISTANT_TARGET="${CUSTOM_ADDONS}/${ASSISTANT_NAME}"

log() {
    printf '\n---- %s ----\n' "$1"
}

fail() {
    printf 'Installation error: %s\n' "$1" >&2
    exit 1
}

if [[ "${EUID}" -ne 0 ]]; then
    fail "run this installer as root (sudo bash installer/odoo18_install.sh)"
fi

if [[ ! -r /etc/os-release ]]; then
    fail "cannot read /etc/os-release"
fi

# shellcheck disable=SC1091
source /etc/os-release
if [[ "${ID:-}" != "ubuntu" || "${VERSION_ID:-}" != "24.04" ]]; then
    fail "this installer supports Ubuntu 24.04; detected ${ID:-unknown} ${VERSION_ID:-unknown}"
fi

log "Installing operating-system dependencies"
export DEBIAN_FRONTEND=noninteractive
apt-get update
apt-get install -y \
    build-essential ca-certificates curl git gnupg libevent-dev libffi-dev \
    libjpeg-dev libldap2-dev libopenjp2-7-dev libpq-dev libsasl2-dev \
    libssl-dev libxml2-dev libxslt1-dev libzip-dev nodejs npm postgresql \
    postgresql-server-dev-all python3-dev python3-pip python3-venv \
    python3-wheel rsync wkhtmltopdf zlib1g-dev

log "Preparing PostgreSQL"
systemctl enable --now postgresql
PG_HBA="$(find /etc/postgresql -type f -path '*/main/pg_hba.conf' -print | sort -V | tail -n 1)"
if [[ -z "${PG_HBA}" ]]; then
    fail "PostgreSQL pg_hba.conf was not found"
fi
if ! grep -q '^# odoo-ai-assistant managed local access$' "${PG_HBA}"; then
    PG_HBA_TEMP="$(mktemp)"
    {
        printf '%s\n' '# odoo-ai-assistant managed local access'
        printf '%s\n' 'local   all   postgres   peer'
        printf 'local   all   %s   peer\n' "${ODOO_USER}"
        cat "${PG_HBA}"
    } >"${PG_HBA_TEMP}"
    install -o postgres -g postgres -m 0640 "${PG_HBA_TEMP}" "${PG_HBA}"
    rm -f "${PG_HBA_TEMP}"
    systemctl reload postgresql
fi
if ! runuser -u postgres -- env PGCONNECT_TIMEOUT=5 psql -tAc \
    "SELECT 1 FROM pg_roles WHERE rolname='${ODOO_USER}'" | grep -qx 1; then
    runuser -u postgres -- createuser --createdb "${ODOO_USER}"
fi

log "Preparing the Odoo account and directories"
if ! getent group "${ODOO_USER}" >/dev/null; then
    groupadd --system "${ODOO_USER}"
fi
if ! id "${ODOO_USER}" >/dev/null 2>&1; then
    useradd --system --gid "${ODOO_USER}" --create-home --home-dir "${ODOO_HOME}" \
        --shell /bin/bash --comment "Odoo" "${ODOO_USER}"
else
    usermod --home "${ODOO_HOME}" --shell /bin/bash "${ODOO_USER}"
fi
printf '%s:%s\n' "${ODOO_USER}" "${ODOO_PASSWORD}" | chpasswd
install -d -o "${ODOO_USER}" -g "${ODOO_USER}" -m 0755 \
    "${ODOO_HOME}" "${CUSTOM_ADDONS}" /var/log/odoo

log "Installing or updating Odoo ${ODOO_VERSION} Community"
if [[ -d "${ODOO_SOURCE}/.git" ]]; then
    runuser -u "${ODOO_USER}" -- git -C "${ODOO_SOURCE}" fetch --depth 1 origin "${ODOO_VERSION}"
    runuser -u "${ODOO_USER}" -- git -C "${ODOO_SOURCE}" checkout "${ODOO_VERSION}"
    runuser -u "${ODOO_USER}" -- git -C "${ODOO_SOURCE}" merge --ff-only FETCH_HEAD
elif [[ -e "${ODOO_SOURCE}" ]]; then
    fail "${ODOO_SOURCE} exists but is not an Odoo Git checkout"
else
    runuser -u "${ODOO_USER}" -- git clone --depth 1 --branch "${ODOO_VERSION}" \
        https://github.com/odoo/odoo.git "${ODOO_SOURCE}"
fi

if [[ ! -x "${ODOO_VENV}/bin/python" ]]; then
    runuser -u "${ODOO_USER}" -- python3 -m venv "${ODOO_VENV}"
fi
runuser -u "${ODOO_USER}" -- "${ODOO_VENV}/bin/python" -m pip install --upgrade pip wheel setuptools
runuser -u "${ODOO_USER}" -- "${ODOO_VENV}/bin/python" -m pip install -r "${ODOO_SOURCE}/requirements.txt"
npm install --global rtlcss

log "Installing ai-odoo-assistant under custom addons"
if [[ "$(readlink -f "${ASSISTANT_SOURCE_DIR}")" != "$(readlink -m "${ASSISTANT_TARGET}")" ]]; then
    install -d -o "${ODOO_USER}" -g "${ODOO_USER}" -m 0755 "${ASSISTANT_TARGET}"
    rsync -a "${ASSISTANT_SOURCE_DIR}/" "${ASSISTANT_TARGET}/"
fi
chown -R "${ODOO_USER}:${ODOO_USER}" "${ASSISTANT_TARGET}"

log "Writing Odoo configuration"
cat >"${ODOO_CONFIG}" <<EOF
[options]
admin_passwd = ${ODOO_ADMIN_PASSWORD}
db_host = False
db_user = ${ODOO_USER}
db_password = False
addons_path = ${ODOO_SOURCE}/odoo/addons,${ODOO_SOURCE}/addons,${CUSTOM_ADDONS},${ASSISTANT_TARGET}/addons
http_interface = 127.0.0.1
http_port = ${ODOO_PORT}
logfile = /var/log/odoo/odoo-server.log
proxy_mode = False
EOF
chown root:"${ODOO_USER}" "${ODOO_CONFIG}"
chmod 0640 "${ODOO_CONFIG}"

log "Installing the systemd service"
cat >/etc/systemd/system/"${ODOO_SERVICE}" <<EOF
[Unit]
Description=Odoo 18 Community
After=network.target postgresql.service
Requires=postgresql.service

[Service]
Type=simple
User=${ODOO_USER}
Group=${ODOO_USER}
ExecStart=${ODOO_VENV}/bin/python ${ODOO_SOURCE}/odoo-bin --config=${ODOO_CONFIG}
WorkingDirectory=${ODOO_SOURCE}
Restart=on-failure
RestartSec=5
KillSignal=SIGINT
TimeoutStopSec=60

[Install]
WantedBy=multi-user.target
EOF
systemctl daemon-reload
systemctl enable --now "${ODOO_SERVICE}"

log "Installation complete"
printf 'Odoo version: %s\n' "${ODOO_VERSION}"
printf 'Odoo service: %s\n' "${ODOO_SERVICE}"
printf 'Odoo config: %s\n' "${ODOO_CONFIG}"
printf 'Custom addons: %s\n' "${CUSTOM_ADDONS}"
printf 'Assistant checkout: %s\n' "${ASSISTANT_TARGET}"
printf 'Local URL: http://127.0.0.1:%s\n' "${ODOO_PORT}"
