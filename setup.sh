#!/usr/bin/env bash
#
# One-step setup: install what is missing, build the UI, and say what to run.
#
#   ./setup.sh                 ask before anything that needs sudo or downloads
#   ./setup.sh --yes           assume yes; for a fresh machine you are not watching
#   ./setup.sh --check         report what is missing and change nothing
#   ./setup.sh --models        also pull a local vision + text model (several GB)
#   ./setup.sh --libreoffice   install LibreOffice without asking (.pptx support)
#   ./setup.sh --no-libreoffice --no-frontend
#
# LibreOffice is optional and only needed to accept .pptx, so it is never installed
# without a yes: you are asked, and --yes alone is not one. Safe to re-run — every
# step is skipped when it is already done.

set -euo pipefail

cd "$(dirname "$0")"

ASSUME_YES=0
CHECK_ONLY=0
WANT_MODELS=0
WANT_FRONTEND=1
LIBREOFFICE="ask"   # ask | yes | no

VISION_MODEL="${VISION_MODEL:-qwen2.5vl:7b}"
TEXT_MODEL="${TEXT_MODEL:-gpt-oss:20b}"

for argument in "$@"; do
    case "$argument" in
        --yes|-y)         ASSUME_YES=1 ;;
        --check|-n)       CHECK_ONLY=1 ;;
        --models)         WANT_MODELS=1 ;;
        --libreoffice)    LIBREOFFICE="yes" ;;
        --no-libreoffice) LIBREOFFICE="no" ;;
        --no-frontend)    WANT_FRONTEND=0 ;;
        --help|-h)        sed -n '3,15p' "$0" | sed 's/^# \{0,1\}//'; exit 0 ;;
        *)                echo "unknown option: $argument (try --help)" >&2; exit 2 ;;
    esac
done

if [ -t 1 ]; then
    BOLD=$(tput bold 2>/dev/null || true); DIM=$(tput dim 2>/dev/null || true)
    RED=$(tput setaf 1 2>/dev/null || true); YELLOW=$(tput setaf 3 2>/dev/null || true)
    GREEN=$(tput setaf 2 2>/dev/null || true); OFF=$(tput sgr0 2>/dev/null || true)
else
    BOLD=""; DIM=""; RED=""; YELLOW=""; GREEN=""; OFF=""
fi

MISSING=()   # what --check found, reported at the end
NOTES=()     # non-fatal things worth knowing after a real run

step()  { printf '\n%s==> %s%s\n' "$BOLD" "$1" "$OFF"; }
ok()    { printf '    %s✓%s %s\n' "$GREEN" "$OFF" "$1"; }
skip()  { printf '    %s· %s%s\n' "$DIM" "$1" "$OFF"; }
warn()  { printf '    %s! %s%s\n' "$YELLOW" "$1" "$OFF"; }
die()   { printf '\n%serror:%s %s\n' "$RED" "$OFF" "$1" >&2; exit 1; }
have()  { command -v "$1" >/dev/null 2>&1; }

# confirm "question" [default]
#
# Asked before anything that needs sudo or pulls something down. The default also
# decides what --yes means, so an optional few-hundred-MB install can default to no
# and stay skipped on an unattended run. --check never says yes to anything.
confirm() {
    local question="$1" default="${2:-y}" hint reply
    [ "$CHECK_ONLY" -eq 1 ] && return 1
    if [ "$ASSUME_YES" -eq 1 ]; then
        [ "$default" = "y" ]
        return
    fi
    [ "$default" = "y" ] && hint="[Y/n]" || hint="[y/N]"
    printf '    %s %s ' "$question" "$hint"
    read -r reply </dev/tty || return 1
    [ -z "$reply" ] && { [ "$default" = "y" ]; return; }
    [[ "$reply" =~ ^[Yy] ]]
}

SUDO=""
if [ "$(id -u)" -ne 0 ]; then
    have sudo && SUDO="sudo"
fi

case "$(uname -s)" in
    Darwin) OS="macos" ;;
    Linux)  OS="linux" ;;
    *)      OS="other" ;;
esac

# ── package manager ──────────────────────────────────────────────────────────

if   have apt-get; then PM="apt"
elif have dnf;     then PM="dnf"
elif have pacman;  then PM="pacman"
elif have zypper;  then PM="zypper"
elif have brew;    then PM="brew"
else PM=""
fi

# One line per manager. Not a package abstraction — just the five commands.
pm_install() {
    case "$PM" in
        apt)    $SUDO apt-get update -qq && $SUDO apt-get install -y "$@" ;;
        dnf)    $SUDO dnf install -y "$@" ;;
        pacman) $SUDO pacman -Sy --noconfirm "$@" ;;
        zypper) $SUDO zypper --non-interactive install "$@" ;;
        brew)   brew install "$@" ;;
        *)      return 1 ;;
    esac
}

# A model Ollama has but config/models.toml does not mention is "unlisted": usable if
# you name it, never *offered* for a role. Pulling one without classifying it means
# downloading gigabytes the pickers then refuse to show, so --models does both.
classify() {  # classify <model> <role>...
    local name="$1"; shift
    local roles where="local"
    roles=$(printf '"%s", ' "$@"); roles="${roles%, }"
    case "$name" in *-cloud|*:cloud) where="cloud" ;; esac

    if [ ! -f config/models.toml ]; then
        warn "no config/models.toml to add $name to"
        return
    fi
    if grep -q "^name = \"$name\"$" config/models.toml; then
        skip "$name is already classified"
        return
    fi
    printf '\n[[models]]\nname = "%s"\nroles = [%s]\nwhere = "%s"\n' \
        "$name" "$roles" "$where" >> config/models.toml
    ok "$name classified as $* in config/models.toml"
}

pm_package() {  # role -> package name for this manager
    case "$1:$PM" in
        libreoffice:apt)  echo "libreoffice-impress" ;;
        libreoffice:brew) echo "--cask libreoffice" ;;
        libreoffice:*)    echo "libreoffice" ;;
        node:brew)        echo "node" ;;
        node:*)           echo "nodejs npm" ;;
    esac
}

printf '%sstudy-ai-tools setup%s  —  %s, %s\n' "$BOLD" "$OFF" "$OS" "${PM:-no known package manager}"
[ "$CHECK_ONLY" -eq 1 ] && printf '%schecking only; nothing will be installed%s\n' "$DIM" "$OFF"

# ── uv ───────────────────────────────────────────────────────────────────────

step "uv (fetches Python 3.14 and the dependencies)"
if have uv; then
    ok "uv $(uv --version 2>/dev/null | awk '{print $2}')"
elif [ "$CHECK_ONLY" -eq 1 ]; then
    warn "not installed"; MISSING+=("uv")
else
    warn "not installed — the official installer is https://astral.sh/uv/install.sh"
    if confirm "Download and run it?"; then
        curl -LsSf https://astral.sh/uv/install.sh | sh
        export PATH="$HOME/.local/bin:$PATH"
        have uv || die "uv installed but is not on PATH — open a new shell and re-run"
        ok "uv installed"
    else
        die "uv is required; install it yourself and re-run"
    fi
fi

# ── Ollama ───────────────────────────────────────────────────────────────────

step "Ollama"
if have ollama; then
    ok "ollama $(ollama --version 2>/dev/null | awk '{print $NF}')"
elif [ "$CHECK_ONLY" -eq 1 ]; then
    warn "not installed"; MISSING+=("ollama")
else
    if [ "$OS" = "macos" ] && [ "$PM" = "brew" ]; then
        confirm "Install with 'brew install ollama'?" && { brew install ollama && ok "installed"; }
    else
        warn "the official installer is https://ollama.com/install.sh"
        confirm "Download and run it? (needs sudo)" && { curl -fsSL https://ollama.com/install.sh | sh; ok "installed"; }
    fi
    have ollama || NOTES+=("Ollama is not installed — the app runs, but every job will fail.")
fi

# Installed is not the same as running: the app talks to it over HTTP.
if have ollama; then
    if ollama list >/dev/null 2>&1; then
        ok "reachable, $(ollama list 2>/dev/null | tail -n +2 | grep -c . || true) model(s) installed"
    else
        warn "installed but not reachable on ${OLLAMA_HOST:-localhost:11434}"
        case "$OS" in
            macos) NOTES+=("Start Ollama: open the app, or run 'ollama serve'.") ;;
            *)     NOTES+=("Start Ollama: 'sudo systemctl start ollama', or run 'ollama serve'.") ;;
        esac
    fi
fi

# ── LibreOffice — optional, and only ever installed on an explicit yes ───────

step "LibreOffice (optional — only needed to accept .pptx)"
if have libreoffice || have soffice; then
    ok "found — .pptx uploads will be accepted"
elif [ "$LIBREOFFICE" = "no" ]; then
    skip "declined (--no-libreoffice); PDF input is unaffected"
    NOTES+=("No LibreOffice: .pptx uploads are rejected, PDF still works. Add it later with ./setup.sh --libreoffice")
elif [ "$CHECK_ONLY" -eq 1 ]; then
    warn "not installed — optional, PDF input still works"; MISSING+=("libreoffice (optional)")
elif [ -z "$PM" ]; then
    warn "not installed, and no known package manager to install it with"
    NOTES+=("Install LibreOffice yourself if you want .pptx support; PDF works without it.")
else
    printf '    %sNot installed. With it, you can upload .pptx; without it, PDF only.%s\n' "$DIM" "$OFF"
    printf '    %sInstalling costs a few hundred MB via %s.%s\n' "$DIM" "$PM" "$OFF"
    # Default no: an optional dependency this size should be a deliberate yes,
    # which is also why --yes alone does not answer it. --libreoffice does.
    if [ "$LIBREOFFICE" = "yes" ] || confirm "Install LibreOffice now?" n; then
        # shellcheck disable=SC2046  # the brew cask flag has to split
        if pm_install $(pm_package libreoffice); then
            ok "LibreOffice installed"
        else
            warn "install failed — carry on without it, or install it yourself"
            NOTES+=("LibreOffice install failed; .pptx uploads will be rejected.")
        fi
    else
        skip "not installed"
        NOTES+=("No LibreOffice: .pptx uploads are rejected, PDF still works. Add it later with ./setup.sh --libreoffice")
    fi
fi

# ── Python dependencies ──────────────────────────────────────────────────────

step "Python dependencies"
if [ "$CHECK_ONLY" -eq 1 ]; then
    [ -d .venv ] && ok ".venv exists" || { warn "no .venv yet"; MISSING+=("uv sync"); }
else
    uv sync
    ok "uv sync"
fi

# ── your model list ──────────────────────────────────────────────────────────

step "config/models.toml"
if [ -f config/models.toml ]; then
    ok "already yours ($(grep -c '^\[\[models\]\]' config/models.toml) entries)"
elif [ "$CHECK_ONLY" -eq 1 ]; then
    warn "missing — the checked-in default would be used"; MISSING+=("config/models.toml")
else
    cp config/model_default.toml config/models.toml
    ok "copied from config/model_default.toml — expand it as you pull models"
fi

# ── models ───────────────────────────────────────────────────────────────────

step "Models"
if [ "$WANT_MODELS" -eq 0 ]; then
    skip "skipped; pass --models to pull $VISION_MODEL and $TEXT_MODEL"
elif ! have ollama || ! ollama list >/dev/null 2>&1; then
    warn "Ollama is not reachable, so nothing can be pulled"
elif [ "$CHECK_ONLY" -eq 1 ]; then
    skip "would pull $VISION_MODEL and $TEXT_MODEL"
else
    for model in "$VISION_MODEL" "$TEXT_MODEL"; do
        if ollama list 2>/dev/null | awk '{print $1}' | grep -qx "$model"; then
            skip "$model already installed"
        elif confirm "Pull $model? (several GB)"; then
            ollama pull "$model" || warn "could not pull $model"
        fi
    done
    # Roles are known by construction — these two variables *are* the roles.
    ollama list 2>/dev/null | awk '{print $1}' | grep -qx "$VISION_MODEL" \
        && classify "$VISION_MODEL" vision
    ollama list 2>/dev/null | awk '{print $1}' | grep -qx "$TEXT_MODEL" \
        && classify "$TEXT_MODEL" refine llm
fi

# ── frontend ─────────────────────────────────────────────────────────────────

step "Frontend"
if [ "$WANT_FRONTEND" -eq 0 ]; then
    skip "skipped by --no-frontend; the API still serves /api"
elif ! have npm; then
    if [ "$CHECK_ONLY" -eq 1 ]; then
        warn "npm not installed"; MISSING+=("npm")
    elif [ -z "$PM" ]; then
        warn "npm not installed and no known package manager — install Node yourself"
    elif confirm "Install Node and npm with $PM?"; then
        # shellcheck disable=SC2046  # two packages on most managers
        pm_install $(pm_package node) && ok "node $(node --version 2>/dev/null)"
    fi
fi

if [ "$WANT_FRONTEND" -eq 1 ] && have npm; then
    if [ "$CHECK_ONLY" -eq 1 ]; then
        [ -d frontend/dist ] && ok "frontend/dist exists" || { warn "not built"; MISSING+=("npm run build"); }
    else
        (cd frontend && npm install --no-audit --no-fund && npm run build)
        ok "frontend/dist built — main.py serves it at /"
    fi
fi

# ── summary ──────────────────────────────────────────────────────────────────

if [ "$CHECK_ONLY" -eq 1 ]; then
    printf '\n'
    if [ ${#MISSING[@]} -eq 0 ]; then
        printf '%sNothing missing.%s\n' "$GREEN" "$OFF"
    else
        printf '%sMissing:%s %s\n' "$YELLOW" "$OFF" "${MISSING[*]}"
        printf 'Run ./setup.sh to install them.\n'
    fi
    exit 0
fi

printf '\n%sReady.%s\n' "$BOLD" "$OFF"
printf '  uv run fastapi dev              http://localhost:8000  — API and the built UI\n'
printf '  cd frontend && npm run dev      http://localhost:5173  — UI work only\n'
printf '  uv run python -m app.cli --help                        — no server needed\n'

if [ ${#NOTES[@]} -gt 0 ]; then
    printf '\n'
    for note in "${NOTES[@]}"; do warn "$note"; done
fi
