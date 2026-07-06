#!/usr/bin/env bash
set -Eeuo pipefail

# Deploy the latest checked-out Doceebot code into the systemd runtime directory,
# run migrations, restart the service, and verify health.
#
# Defaults match the current VPS deployment:
#   source repo: /root/Doceebot
#   runtime app: /opt/doceebot
#   service:     doceebot.service
#
# Common usage:
#   sudo scripts/deploy_update_restart.sh
#   sudo scripts/deploy_update_restart.sh --no-pull
#   sudo scripts/deploy_update_restart.sh --dry-run

SOURCE_DIR="${SOURCE_DIR:-/root/Doceebot}"
APP_DIR="${APP_DIR:-/opt/doceebot}"
SERVICE_NAME="${SERVICE_NAME:-doceebot}"
APP_USER="${APP_USER:-doceebot}"
if [[ -n "${APP_GROUP:-}" ]]; then
    APP_GROUP_EXPLICIT=true
else
    APP_GROUP_EXPLICIT=false
fi
APP_GROUP="${APP_GROUP:-$APP_USER}"
HEALTH_URL="${HEALTH_URL:-http://127.0.0.1:8000/health}"
PUBLIC_HEALTH_URL="${PUBLIC_HEALTH_URL:-https://doceebot.name.ng/health}"
UV_BIN="${UV_BIN:-}"
PULL_LATEST=true
RUN_TESTS=false
SKIP_MIGRATIONS=false
SKIP_PUBLIC_HEALTH=false
DRY_RUN=false
HEALTH_TIMEOUT_SECONDS="${HEALTH_TIMEOUT_SECONDS:-45}"

usage() {
    cat <<'USAGE'
Usage: deploy_update_restart.sh [options]

Safely deploy Doceebot from a source checkout into /opt/doceebot, preserving
.env, .venv, and storage, then run Alembic migrations, restart systemd, and
verify health.

Options:
  --source-dir PATH          Source checkout to deploy from. Default: /root/Doceebot
  --app-dir PATH             Runtime app directory. Default: /opt/doceebot
  --service NAME             systemd service name. Default: doceebot
  --app-user USER            Runtime user. Default: doceebot
  --app-group GROUP          Runtime group. Default: same as --app-user
  --health-url URL           Local health URL. Default: http://127.0.0.1:8000/health
  --public-health-url URL    Public health URL. Default: https://doceebot.name.ng/health
  --uv-bin PATH              uv executable. Default: first uv in PATH, then /root/.local/bin/uv
  --no-pull                  Do not git pull the source checkout before deploying
  --run-tests                Run ruff and pytest before syncing/restarting
  --skip-migrations          Do not run Alembic migrations
  --skip-public-health       Skip the public HTTPS health check
  --dry-run                  Print actions without changing files or restarting
  -h, --help                 Show this help

Environment variables with the same names as the defaults above can also be set.
USAGE
}

log() {
    printf '\n==> %s\n' "$*"
}

warn() {
    printf 'WARNING: %s\n' "$*" >&2
}

fail() {
    printf 'ERROR: %s\n' "$*" >&2
    exit 1
}

quote_cmd() {
    printf '+ '
    printf '%q ' "$@"
    printf '\n'
}

run() {
    quote_cmd "$@"
    if [[ "$DRY_RUN" == false ]]; then
        "$@"
    fi
}

run_shell() {
    printf '+ bash -lc %q\n' "$1"
    if [[ "$DRY_RUN" == false ]]; then
        bash -lc "$1"
    fi
}

as_app_user_shell() {
    local command="$1"
    printf '+ runuser -u %q -- bash -lc %q\n' "$APP_USER" "$command"
    if [[ "$DRY_RUN" == false ]]; then
        runuser -u "$APP_USER" -- bash -lc "$command"
    fi
}

require_root() {
    if [[ "${EUID:-$(id -u)}" -ne 0 && "$DRY_RUN" == false ]]; then
        fail "run as root because deployment writes to $APP_DIR and restarts $SERVICE_NAME"
    fi
}

resolve_uv() {
    if [[ -n "$UV_BIN" ]]; then
        return
    fi
    if command -v uv >/dev/null 2>&1; then
        UV_BIN="$(command -v uv)"
    elif [[ -x /root/.local/bin/uv ]]; then
        UV_BIN="/root/.local/bin/uv"
    else
        fail "uv was not found. Install uv or pass --uv-bin PATH"
    fi
}

parse_args() {
    while [[ $# -gt 0 ]]; do
        case "$1" in
            --source-dir)
                SOURCE_DIR="$2"
                shift 2
                ;;
            --app-dir)
                APP_DIR="$2"
                shift 2
                ;;
            --service)
                SERVICE_NAME="$2"
                shift 2
                ;;
            --app-user)
                APP_USER="$2"
                if [[ "$APP_GROUP_EXPLICIT" == false ]]; then
                    APP_GROUP="$2"
                fi
                shift 2
                ;;
            --app-group)
                APP_GROUP="$2"
                APP_GROUP_EXPLICIT=true
                shift 2
                ;;
            --health-url)
                HEALTH_URL="$2"
                shift 2
                ;;
            --public-health-url)
                PUBLIC_HEALTH_URL="$2"
                shift 2
                ;;
            --uv-bin)
                UV_BIN="$2"
                shift 2
                ;;
            --no-pull)
                PULL_LATEST=false
                shift
                ;;
            --run-tests)
                RUN_TESTS=true
                shift
                ;;
            --skip-migrations)
                SKIP_MIGRATIONS=true
                shift
                ;;
            --skip-public-health)
                SKIP_PUBLIC_HEALTH=true
                shift
                ;;
            --dry-run)
                DRY_RUN=true
                shift
                ;;
            -h|--help)
                usage
                exit 0
                ;;
            *)
                fail "unknown argument: $1"
                ;;
        esac
    done
}

check_prerequisites() {
    [[ -d "$SOURCE_DIR" ]] || fail "source directory does not exist: $SOURCE_DIR"
    [[ -f "$SOURCE_DIR/pyproject.toml" ]] || fail "source directory does not look like Doceebot: $SOURCE_DIR"
    [[ -d "$APP_DIR" || "$DRY_RUN" == true ]] || fail "app directory does not exist: $APP_DIR"
    command -v rsync >/dev/null 2>&1 || fail "rsync is required"
    command -v curl >/dev/null 2>&1 || fail "curl is required"
    command -v systemctl >/dev/null 2>&1 || fail "systemctl is required"
    command -v runuser >/dev/null 2>&1 || fail "runuser is required"
    id "$APP_USER" >/dev/null 2>&1 || fail "runtime user does not exist: $APP_USER"
    resolve_uv
}

source_git_state() {
    if git -C "$SOURCE_DIR" rev-parse --is-inside-work-tree >/dev/null 2>&1; then
        git -C "$SOURCE_DIR" status --short
        git -C "$SOURCE_DIR" rev-parse --short HEAD
    else
        printf 'not-a-git-checkout\n'
    fi
}

update_source_checkout() {
    if ! git -C "$SOURCE_DIR" rev-parse --is-inside-work-tree >/dev/null 2>&1; then
        warn "$SOURCE_DIR is not a git checkout, skipping git pull"
        return
    fi

    if [[ "$PULL_LATEST" == false ]]; then
        log "Skipping git pull (--no-pull)"
        return
    fi

    if [[ -n "$(git -C "$SOURCE_DIR" status --porcelain)" ]]; then
        fail "source checkout has uncommitted changes. Commit/stash them or rerun with --no-pull"
    fi

    log "Updating source checkout"
    run git -C "$SOURCE_DIR" fetch origin
    local branch
    branch="$(git -C "$SOURCE_DIR" branch --show-current)"
    [[ -n "$branch" ]] || fail "source checkout is detached; rerun with --no-pull or checkout a branch"
    run git -C "$SOURCE_DIR" pull --ff-only origin "$branch"
}

run_preflight_tests() {
    if [[ "$RUN_TESTS" == false ]]; then
        return
    fi
    log "Running pre-deploy checks"
    run_shell "cd $(printf '%q' "$SOURCE_DIR") && $(printf '%q' "$UV_BIN") run ruff check ."
    run_shell "cd $(printf '%q' "$SOURCE_DIR") && $(printf '%q' "$UV_BIN") run pytest"
}

sync_app_tree() {
    log "Syncing source into runtime directory"
    run rsync -a --delete \
        --chown="$APP_USER:$APP_GROUP" \
        --include='.env.example' \
        --exclude='.git/' \
        --exclude='.env' \
        --exclude='.env.*' \
        --exclude='.venv/' \
        --exclude='node_modules/' \
        --exclude='dashboard/dist/' \
        --exclude='dashboard/.wrangler/' \
        --exclude='.cache/' \
        --exclude='.local/' \
        --exclude='storage/' \
        --exclude='.pytest_cache/' \
        --exclude='.ruff_cache/' \
        --exclude='tmp_pipeline_artifacts/' \
        "$SOURCE_DIR/" "$APP_DIR/"
}

sync_python_environment() {
    log "Syncing Python environment"
    run_shell "cd $(printf '%q' "$APP_DIR") && $(printf '%q' "$UV_BIN") sync --frozen"
    run chown -R "$APP_USER:$APP_GROUP" "$APP_DIR/.venv" "$APP_DIR/.cache"
}

run_migrations() {
    if [[ "$SKIP_MIGRATIONS" == true ]]; then
        log "Skipping migrations"
        return
    fi
    log "Running Alembic migrations"
    local app_dir_q
    app_dir_q="$(printf '%q' "$APP_DIR")"
    as_app_user_shell "cd $app_dir_q && set -a && source .env && set +a && .venv/bin/alembic upgrade head && .venv/bin/alembic current"
}

write_deploy_marker() {
    local marker="$APP_DIR/DEPLOYED_COMMIT"
    local sha="unknown"
    if git -C "$SOURCE_DIR" rev-parse HEAD >/dev/null 2>&1; then
        sha="$(git -C "$SOURCE_DIR" rev-parse HEAD)"
    fi
    printf '+ write deployed marker %q\n' "$marker"
    if [[ "$DRY_RUN" == false ]]; then
        printf '%s\n' "$sha" > "$marker"
        chown "$APP_USER:$APP_GROUP" "$marker"
    fi
}

restart_service() {
    log "Restarting $SERVICE_NAME"
    run systemctl restart "$SERVICE_NAME"
    run systemctl is-active --quiet "$SERVICE_NAME"
}

wait_for_health() {
    local url="$1"
    local label="$2"
    local timeout="$3"
    log "Checking $label health: $url"
    if [[ "$DRY_RUN" == true ]]; then
        quote_cmd curl -fsS "$url"
        return
    fi

    local started now elapsed
    started="$(date +%s)"
    while true; do
        if curl -fsS "$url"; then
            printf '\n%s health check passed.\n' "$label"
            return
        fi
        now="$(date +%s)"
        elapsed=$((now - started))
        if (( elapsed >= timeout )); then
            journalctl -u "$SERVICE_NAME" --no-pager -n 100 || true
            fail "$label health check failed after ${timeout}s: $url"
        fi
        sleep 1
    done
}

show_status() {
    log "Service status"
    run systemctl show "$SERVICE_NAME" -p MainPID -p ActiveState -p SubState --no-pager
    if [[ "$DRY_RUN" == false ]]; then
        printf 'Deployed source state: '
        source_git_state | tail -n 1
    fi
}

main() {
    parse_args "$@"
    require_root
    check_prerequisites

    log "Deployment settings"
    printf 'source_dir=%s\napp_dir=%s\nservice=%s\napp_user=%s\nhealth_url=%s\npublic_health_url=%s\ndry_run=%s\n' \
        "$SOURCE_DIR" "$APP_DIR" "$SERVICE_NAME" "$APP_USER" "$HEALTH_URL" "$PUBLIC_HEALTH_URL" "$DRY_RUN"

    update_source_checkout
    run_preflight_tests
    sync_app_tree
    sync_python_environment
    run_migrations
    write_deploy_marker
    restart_service
    wait_for_health "$HEALTH_URL" "local" "$HEALTH_TIMEOUT_SECONDS"
    if [[ "$SKIP_PUBLIC_HEALTH" == false && -n "$PUBLIC_HEALTH_URL" ]]; then
        wait_for_health "$PUBLIC_HEALTH_URL" "public" "$HEALTH_TIMEOUT_SECONDS"
    fi
    show_status

    log "Deployment complete"
}

main "$@"
