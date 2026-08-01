#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)"
REPO_ROOT="$(cd -- "${SCRIPT_DIR}/.." && pwd -P)"
CORE_ROOT="${REPO_ROOT}/qiko-core"
CORE_PYTHON="${REPO_ROOT}/qiko-core/.venv/bin/python"
FRONTEND_ROOT="${REPO_ROOT}/frontend"
PROJECT_NAME="qiko-dev"
HOST_SERVICES=(qiko-core worker db redis caddy)
PARITY_SERVICES=(qiko-core worker creator admin db redis caddy)
HOST_COMPOSE_ARGS=(--env-file "${REPO_ROOT}/.env" -p "${PROJECT_NAME}" -f "${REPO_ROOT}/docker-compose.yml" -f "${REPO_ROOT}/docker-compose.dev.yml")
PARITY_COMPOSE_ARGS=(--env-file "${REPO_ROOT}/.env" -p "${PROJECT_NAME}" -f "${REPO_ROOT}/docker-compose.yml" -f "${REPO_ROOT}/docker-compose.dev.yml" -f "${REPO_ROOT}/docker-compose.dev.parity.yml")
DOCKER=""

fail() {
  printf 'ERROR: %s\n' "$*" >&2
  exit 1
}

usage() {
  cat <<'EOF'
Usage: ./scripts/dev.sh COMMAND [OPTIONS]

Commands:
  setup            Create .env when absent, validate prerequisites, and install dependencies
  up               Start backend services for host frontend development
  frontend         Start Creator and Admin Next.js development servers
  parity           Build and check the complete container parity stack
  status            Show local service status
  logs [OPTIONS]   Show the last 200 log lines (accepts -f/--follow and service names)
  down              Stop local services while preserving volumes
  reset             Confirm volume deletion, recreate, migrate, and bootstrap an Admin
  check             Run runtime and focused non-mutating quality checks
  bootstrap-admin   Securely bootstrap a local tenant owner and platform Admin
EOF
}

discover_docker() {
  if [[ -n "${DOCKER_BIN:-}" ]]; then
    if [[ -x "${DOCKER_BIN}" ]]; then
      DOCKER="${DOCKER_BIN}"
    elif command -v -- "${DOCKER_BIN}" >/dev/null 2>&1; then
      DOCKER="$(command -v -- "${DOCKER_BIN}")"
    else
      fail "DOCKER_BIN does not identify an executable Docker CLI"
    fi
  elif command -v docker >/dev/null 2>&1; then
    DOCKER="$(command -v docker)"
  elif [[ -x /Applications/Docker.app/Contents/Resources/bin/docker ]]; then
    DOCKER="/Applications/Docker.app/Contents/Resources/bin/docker"
  else
    fail "Docker was not found; set DOCKER_BIN or install Docker Desktop"
  fi

  if [[ "${DOCKER}" == */* ]]; then
    local docker_directory docker_filename
    docker_directory="${DOCKER%/*}"
    docker_filename="${DOCKER##*/}"
    [[ -n "${docker_directory}" ]] || docker_directory="/"
    docker_directory="$(cd -- "${docker_directory}" && pwd -P)" || fail "Docker executable directory is unavailable"
    [[ -n "${docker_directory}" && "${docker_directory}" != "." && "${docker_directory}" != *:* ]] || fail "Docker executable directory is invalid"
    DOCKER="${docker_directory}/${docker_filename}"
    case ":${PATH:-}:" in
      *":${docker_directory}:"*) ;;
      *) PATH="${docker_directory}${PATH:+:${PATH}}"; export PATH ;;
    esac
  fi

  local compose_version compose_major compose_minor compose_patch
  compose_version="$("${DOCKER}" compose version --short 2>/dev/null)" || fail "Docker Compose 2 or newer is unavailable"
  [[ "${compose_version}" =~ ^v?([0-9]+)\.([0-9]+)\.([0-9]+)([-+][0-9A-Za-z.-]+)?$ ]] || fail "Docker Compose 2 or newer is required"
  compose_major="${BASH_REMATCH[1]}"
  compose_minor="${BASH_REMATCH[2]}"
  compose_patch="${BASH_REMATCH[3]}"
  [[ "${compose_major}" == "0" || "${compose_major}" != 0* ]] || fail "Docker Compose 2 or newer is required"
  [[ "${compose_minor}" == "0" || "${compose_minor}" != 0* ]] || fail "Docker Compose 2 or newer is required"
  [[ "${compose_patch}" == "0" || "${compose_patch}" != 0* ]] || fail "Docker Compose 2 or newer is required"
  (( ${#compose_major} > 1 || 10#${compose_major} >= 2 )) || fail "Docker Compose 2 or newer is required"
}

require_local_config() {
  [[ -f "${REPO_ROOT}/.env" && -r "${REPO_ROOT}/.env" ]] || fail "missing readable .env; run ./scripts/dev.sh setup first"
}

host_compose() {
  "${DOCKER}" compose "${HOST_COMPOSE_ARGS[@]}" "$@"
}

parity_compose() {
  "${DOCKER}" compose "${PARITY_COMPOSE_ARGS[@]}" "$@"
}

validate_frontend_tools() {
  command -v node >/dev/null 2>&1 || fail "Node.js is required (supported major version: 20 or newer)"
  command -v pnpm >/dev/null 2>&1 || fail "pnpm 9.12.0 is required"

  local node_version node_major pnpm_version
  node_version="$(node --version)"
  [[ "${node_version}" =~ ^v([0-9]+)\. ]] || fail "could not determine the Node.js version"
  node_major="${BASH_REMATCH[1]}"
  (( node_major >= 20 )) || fail "Node.js 20 or newer is required"

  pnpm_version="$(pnpm --version)"
  [[ "${pnpm_version}" == "9.12.0" ]] || fail "pnpm 9.12.0 is required"
}

validate_prerequisites() {
  discover_docker
  command -v python3 >/dev/null 2>&1 || fail "Python 3 is required"
  python3 -c 'import sys; raise SystemExit(sys.version_info.major != 3)' >/dev/null 2>&1 || fail "Python 3 is unavailable"
  validate_frontend_tools
}

extract_local_config_value() {
  local key="$1"
  local line candidate="" matches=0
  while IFS= read -r line || [[ -n "${line}" ]]; do
    if [[ "${line}" == "${key}="* ]]; then
      candidate="${line#*=}"
      candidate="${candidate%$'\r'}"
      matches=$((matches + 1))
    fi
  done < "${REPO_ROOT}/.env"

  (( matches <= 1 )) || return 2
  (( matches == 1 )) || return 1
  printf '%s' "${candidate}"
}

validate_port() {
  local key="$1" value="$2" numeric normalized
  [[ "${value}" =~ ^[0-9]+$ ]] || fail "${key} must be numeric"
  normalized="${value}"
  while [[ "${normalized}" == 0* && "${#normalized}" -gt 1 ]]; do
    normalized="${normalized#0}"
  done
  (( ${#normalized} <= 5 )) || fail "${key} must be between 1 and 65535"
  numeric=$((10#${normalized}))
  (( numeric >= 1 && numeric <= 65535 )) || fail "${key} must be between 1 and 65535"
}

resolve_port() {
  local key="$1" default_value="$2" value status
  if value="$(printenv "${key}" 2>/dev/null)"; then
    :
  elif value="$(extract_local_config_value "${key}")"; then
    :
  else
    status=$?
    (( status == 1 )) || fail "${key} must appear at most once in .env"
    value="${default_value}"
  fi

  validate_port "${key}" "${value}"
  printf -v "${key}" '%s' "${value}"
  export "${key}"
}

resolve_local_ports() {
  resolve_port QIKO_DEV_HTTP_PORT 8080
  resolve_port QIKO_DEV_API_PORT 8000
  resolve_port QIKO_DEV_CREATOR_PORT 3000
  resolve_port QIKO_DEV_ADMIN_PORT 3001
}

prepare_local_runtime() {
  require_local_config
  resolve_local_ports
  discover_docker
}

create_local_config_if_absent() {
  if [[ -e "${REPO_ROOT}/.env" || -L "${REPO_ROOT}/.env" ]]; then
    printf 'Existing .env was left untouched.\n'
    return
  fi

  if (umask 077; set -o noclobber; cat -- "${REPO_ROOT}/.env.example" > "${REPO_ROOT}/.env") 2>/dev/null; then
    printf 'Created .env from .env.example. Review its local-only values before startup.\n'
  elif [[ -e "${REPO_ROOT}/.env" || -L "${REPO_ROOT}/.env" ]]; then
    printf 'Existing .env was left untouched.\n'
  else
    fail "could not create .env exclusively"
  fi
}

migrate() {
  host_compose exec -T qiko-core alembic upgrade head
}

up_host() {
  host_compose up -d --build --wait --wait-timeout 180 "${HOST_SERVICES[@]}"
  migrate
}

run_local_contract_check() {
  python3 "${REPO_ROOT}/scripts/check_local_contract.py" --port "${QIKO_DEV_HTTP_PORT}"
}

validate_check_tools() {
  command -v uv >/dev/null 2>&1 || fail "uv is required; install the version pinned by the development guide"
  uv --version >/dev/null 2>&1 || fail "uv is unavailable"
  validate_frontend_tools
  [[ -x "${CORE_PYTHON}" ]] || fail "backend virtual environment is missing; run uv sync --frozen --extra dev in qiko-core"
}

run_focused_quality_checks() {
  validate_check_tools
  "${CORE_PYTHON}" "${REPO_ROOT}/scripts/sync_openapi.py" --check
  "${CORE_PYTHON}" -m pytest -c "${CORE_ROOT}/pyproject.toml" --no-cov \
    "${CORE_ROOT}/tests/test_bootstrap_dev.py" \
    "${CORE_ROOT}/tests/test_openapi_sync.py"
  "${CORE_PYTHON}" -m ruff check --config "${CORE_ROOT}/pyproject.toml" \
    "${CORE_ROOT}/app/db/dev_bootstrap.py" \
    "${CORE_ROOT}/scripts/bootstrap_dev.py" \
    "${CORE_ROOT}/tests/test_bootstrap_dev.py" \
    "${CORE_ROOT}/tests/test_openapi_sync.py" \
    "${REPO_ROOT}/scripts/check_local_contract.py" \
    "${REPO_ROOT}/scripts/sync_openapi.py"
  pnpm --dir "${FRONTEND_ROOT}" --filter creator test
  pnpm --dir "${FRONTEND_ROOT}" --filter admin test
  pnpm --dir "${FRONTEND_ROOT}" -r lint
}

prompt_required() {
  local output_name="$1" prompt="$2" value
  read -r -p "${prompt}" value
  [[ -n "${value}" ]] || fail "a value is required"
  printf -v "${output_name}" '%s' "${value}"
}

run_bootstrap_admin() {
  local argument password password_confirmation
  for argument in "$@"; do
    case "${argument}" in
      --password|--password=*|--password-stdin) fail "password arguments are forbidden; the password is prompted securely" ;;
    esac
  done

  [[ -t 0 ]] || fail "bootstrap-admin requires an interactive terminal"
  read -r -s -p "Local Admin password: " password
  printf '\n'
  read -r -s -p "Confirm local Admin password: " password_confirmation
  printf '\n'
  [[ -n "${password}" ]] || fail "password cannot be empty"
  [[ "${password}" == "${password_confirmation}" ]] || fail "passwords did not match"

  printf '%s\n' "${password}" | host_compose exec -T qiko-core \
    python scripts/bootstrap_dev.py "$@" --password-stdin
}

command_setup() {
  create_local_config_if_absent
  validate_prerequisites
  pnpm --dir "${FRONTEND_ROOT}" install --frozen-lockfile
}

command_up() {
  prepare_local_runtime
  up_host
}

command_frontend() {
  require_local_config
  resolve_local_ports
  validate_frontend_tools
  export NEXT_PUBLIC_API_BASE="/api/v1"
  export NEXT_PUBLIC_CREATOR_BASE_URL="http://qiko.localhost:${QIKO_DEV_HTTP_PORT}"
  pnpm --dir "${FRONTEND_ROOT}" run dev:local
}

command_parity() {
  prepare_local_runtime
  parity_compose up -d --build --wait --wait-timeout 180 "${PARITY_SERVICES[@]}"
  migrate
  run_local_contract_check
}

command_status() {
  prepare_local_runtime
  host_compose ps
}

command_logs() {
  local argument follow=false
  local services=()
  for argument in "$@"; do
    case "${argument}" in
      -f|--follow) follow=true ;;
      qiko-core|worker|creator|admin|db|redis|caddy) services+=("${argument}") ;;
      *) fail "logs accepts only -f/--follow and approved service names" ;;
    esac
  done

  prepare_local_runtime
  local log_args=(--tail 200)
  [[ "${follow}" == true ]] && log_args+=(--follow)
  log_args+=("${services[@]}")
  host_compose logs "${log_args[@]}"
}

command_down() {
  prepare_local_runtime
  host_compose down --remove-orphans
}

command_reset() {
  prepare_local_runtime
  [[ -t 0 ]] || fail "reset requires an interactive terminal"

  local confirmation tenant display_name email
  read -r -p "Type DELETE qiko-dev volumes to delete local databases and queues: " confirmation
  [[ "${confirmation}" == "DELETE qiko-dev volumes" ]] || fail "reset cancelled; confirmation did not match"

  host_compose down --volumes --remove-orphans
  up_host
  prompt_required tenant "Local tenant identifier: "
  prompt_required display_name "Local Admin display name: "
  prompt_required email "Local Admin email: "
  run_bootstrap_admin \
    --tenant "${tenant}" \
    --display-name "${display_name}" \
    --email "${email}"
}

command_check() {
  prepare_local_runtime
  host_compose config --quiet
  parity_compose config --quiet

  local running_services required_service running_service found
  running_services="$(host_compose ps --services --status running)"
  for required_service in "${HOST_SERVICES[@]}"; do
    found=false
    while IFS= read -r running_service; do
      if [[ "${running_service}" == "${required_service}" ]]; then
        found=true
        break
      fi
    done <<< "${running_services}"
    [[ "${found}" == true ]] || fail "required local service is not running: ${required_service}"
  done

  host_compose exec -T db sh -c 'exec pg_isready -U "$POSTGRES_USER" -d "$POSTGRES_DB"' >/dev/null
  host_compose exec -T redis redis-cli ping >/dev/null

  local migration_status
  migration_status="$(host_compose exec -T qiko-core alembic current)"
  [[ "${migration_status}" == *"(head)"* ]] || fail "database migration is not at an Alembic head"
  run_local_contract_check
  run_focused_quality_checks
}

command_bootstrap_admin() {
  prepare_local_runtime
  run_bootstrap_admin "$@"
}

main() {
  local command="${1:-}"
  if (( $# > 0 )); then
    shift
  fi

  case "${command}" in
    setup) (( $# == 0 )) || fail "setup does not accept options"; command_setup ;;
    up) (( $# == 0 )) || fail "up does not accept options"; command_up ;;
    frontend) (( $# == 0 )) || fail "frontend does not accept options"; command_frontend ;;
    parity) (( $# == 0 )) || fail "parity does not accept options"; command_parity ;;
    status) (( $# == 0 )) || fail "status does not accept options"; command_status ;;
    logs) command_logs "$@" ;;
    down) (( $# == 0 )) || fail "down does not accept options"; command_down ;;
    reset) (( $# == 0 )) || fail "reset does not accept options"; command_reset ;;
    check) (( $# == 0 )) || fail "check does not accept options"; command_check ;;
    bootstrap-admin) command_bootstrap_admin "$@" ;;
    -h|--help|help) usage ;;
    '') usage; exit 1 ;;
    *) fail "unknown command" ;;
  esac
}

main "$@"
