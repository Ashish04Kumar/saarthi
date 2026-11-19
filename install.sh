#!/usr/bin/env bash
# Saarthi installer for Linux and macOS.
#
#   ./install.sh               install (or update) and start Saarthi
#   ./install.sh --autostart   ...and start it with your computer
#   ./install.sh --uninstall   remove the app (your notes/reminders are kept)
#
# Nothing is installed system-wide and sudo is never used: everything goes in your home folder.
set -euo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
OS="$(uname -s)"
if [[ "$OS" == "Darwin" ]]; then
  APP_HOME="${SAARTHI_HOME:-$HOME/Library/Application Support/Saarthi/app}"
else
  APP_HOME="${SAARTHI_HOME:-${XDG_DATA_HOME:-$HOME/.local/share}/saarthi}"
fi
VENV="$APP_HOME/venv"
BIN_DIR="$HOME/.local/bin"
DESKTOP_FILE="${XDG_DATA_HOME:-$HOME/.local/share}/applications/saarthi.desktop"
ICON_FILE="${XDG_DATA_HOME:-$HOME/.local/share}/icons/hicolor/256x256/apps/saarthi.png"
MAC_APP="$HOME/Applications/Saarthi.app"

say()  { printf '\033[1;34m==>\033[0m %s\n' "$*"; }
warn() { printf '\033[1;33m!!\033[0m  %s\n' "$*"; }
die()  { printf '\033[1;31mxx\033[0m  %s\n' "$*" >&2; exit 1; }

AUTOSTART=0
for arg in "$@"; do
  case "$arg" in
    --autostart) AUTOSTART=1 ;;
    --uninstall)
      say "Removing Saarthi (your data in the config folder is kept)"
      pkill -f "$VENV/bin/python.*saarthi" 2>/dev/null || true
      rm -rf "$APP_HOME" "$BIN_DIR/saarthi" "$DESKTOP_FILE" "$ICON_FILE" "$MAC_APP" \
             "${XDG_CONFIG_HOME:-$HOME/.config}/autostart/saarthi.desktop" \
             "$HOME/Library/LaunchAgents/io.github.saarthi.plist"
      say "Done."
      exit 0 ;;
    -h|--help) sed -n '2,9p' "$0"; exit 0 ;;
    *) die "Unknown option: $arg" ;;
  esac
done

# ---------- Python ----------
PY=""
for cand in python3.13 python3.12 python3.11 python3.10 python3; do
  if command -v "$cand" >/dev/null 2>&1 && "$cand" -c 'import sys; sys.exit(sys.version_info < (3, 10))' 2>/dev/null; then
    PY="$(command -v "$cand")"; break
  fi
done
if [[ -z "$PY" ]]; then
  if [[ "$OS" == "Darwin" ]]; then
    die "Python 3.10+ is needed. Install it from https://www.python.org/downloads/ (or: brew install python), then run this again."
  fi
  die "Python 3.10+ is needed. Ubuntu/Debian: sudo apt install python3 python3-venv   Fedora: sudo dnf install python3"
fi
if ! "$PY" -c 'import venv, ensurepip' 2>/dev/null; then
  die "Python's venv module is missing. Ubuntu/Debian: sudo apt install python3-venv"
fi
say "Using $("$PY" --version) at $PY"

# ---------- Linux system libraries Qt needs ----------
if [[ "$OS" == "Linux" ]] && command -v ldconfig >/dev/null 2>&1; then
  missing=()
  libs="$(ldconfig -p 2>/dev/null || true)"  # read once: grep -q in a pipe trips pipefail
  for lib in libxcb-cursor.so.0 libxkbcommon-x11.so.0 libEGL.so.1; do
    [[ "$libs" == *"$lib"* ]] || missing+=("$lib")
  done
  if (( ${#missing[@]} )); then
    warn "Missing system libraries for the window: ${missing[*]}"
    warn "Ubuntu/Debian: sudo apt install libxcb-cursor0 libxkbcommon-x11-0 libegl1"
    warn "Fedora:        sudo dnf install xcb-util-cursor libxkbcommon-x11 mesa-libEGL"
    warn "Arch:          sudo pacman -S xcb-util-cursor libxkbcommon-x11"
  fi
fi

# ---------- remove the old "DeskBuddy" install (the app was renamed to Saarthi) ----------
OLD_HOME="${XDG_DATA_HOME:-$HOME/.local/share}/deskbuddy"
[[ "$OS" == "Darwin" ]] && OLD_HOME="$HOME/Library/Application Support/DeskBuddy/app"
if [[ -d "$OLD_HOME" || -e "$BIN_DIR/deskbuddy" || -d "$HOME/Applications/DeskBuddy.app" ]]; then
  say "Removing the old DeskBuddy install (your notes and settings move over to Saarthi)"
  [[ -x "$OLD_HOME/venv/bin/deskbuddy" ]] && "$OLD_HOME/venv/bin/deskbuddy" --quit >/dev/null 2>&1 || true
  rm -rf "$OLD_HOME" "$BIN_DIR/deskbuddy" "$HOME/Applications/DeskBuddy.app" \
         "${XDG_DATA_HOME:-$HOME/.local/share}/applications/deskbuddy.desktop" \
         "${XDG_DATA_HOME:-$HOME/.local/share}/icons/hicolor/256x256/apps/deskbuddy.png"
fi

# ---------- install into a private virtualenv ----------
say "Installing into $APP_HOME"
mkdir -p "$APP_HOME"
if [[ ! -x "$VENV/bin/python" ]]; then
  "$PY" -m venv "$VENV"
fi
"$VENV/bin/python" -m pip install --quiet --upgrade pip
"$VENV/bin/python" -m pip install --quiet --upgrade "$REPO"
"$VENV/bin/python" -c "import saarthi" || die "Install failed."

# ---------- launchers ----------
mkdir -p "$BIN_DIR"
ln -sf "$VENV/bin/saarthi" "$BIN_DIR/saarthi"

if [[ "$OS" == "Linux" ]]; then
  mkdir -p "$(dirname "$DESKTOP_FILE")" "$(dirname "$ICON_FILE")"
  cp "$REPO/src/saarthi/assets/icon.png" "$ICON_FILE"
  cat > "$DESKTOP_FILE" <<EOF
[Desktop Entry]
Type=Application
Name=Saarthi
Comment=Your animated desktop companion
Exec="$VENV/bin/saarthi"
Icon=saarthi
Terminal=false
Categories=Utility;
StartupWMClass=saarthi
EOF
  command -v update-desktop-database >/dev/null 2>&1 && update-desktop-database -q "$(dirname "$DESKTOP_FILE")" || true
  say "Added Saarthi to your app menu"
elif [[ "$OS" == "Darwin" ]]; then
  mkdir -p "$MAC_APP/Contents/MacOS" "$MAC_APP/Contents/Resources"
  cat > "$MAC_APP/Contents/MacOS/Saarthi" <<EOF
#!/bin/bash
exec "$VENV/bin/python" -m saarthi "\$@"
EOF
  chmod +x "$MAC_APP/Contents/MacOS/Saarthi"
  if command -v iconutil >/dev/null 2>&1 && command -v sips >/dev/null 2>&1; then
    ICONSET="$(mktemp -d)/Saarthi.iconset"; mkdir -p "$ICONSET"
    for s in 16 32 128 256 512; do
      sips -z $s $s "$REPO/src/saarthi/assets/icon-512.png" --out "$ICONSET/icon_${s}x${s}.png" >/dev/null
    done
    iconutil -c icns "$ICONSET" -o "$MAC_APP/Contents/Resources/Saarthi.icns" || true
  fi
  cat > "$MAC_APP/Contents/Info.plist" <<EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0"><dict>
  <key>CFBundleName</key><string>Saarthi</string>
  <key>CFBundleIdentifier</key><string>io.github.saarthi</string>
  <key>CFBundleExecutable</key><string>Saarthi</string>
  <key>CFBundleIconFile</key><string>Saarthi</string>
  <key>CFBundlePackageType</key><string>APPL</string>
  <key>LSUIElement</key><true/>
</dict></plist>
EOF
  say "Added Saarthi to ~/Applications"
fi

if (( AUTOSTART )); then
  "$VENV/bin/python" -c "from saarthi.system import set_autostart; set_autostart(True)"
  say "Saarthi will start with your computer"
fi

# ---------- typing detection on Linux Wayland ----------
if [[ "$OS" == "Linux" && "${XDG_SESSION_TYPE:-}" == "wayland" ]] && ! id -nG | grep -qw input; then
  echo
  warn "You're on Wayland, which hides keyboard activity from apps."
  warn "To let Saarthi see how fast you type (never what you type), run once:"
  echo "        sudo usermod -aG input \$USER"
  warn "then log out and back in. (Or pick 'Ubuntu on Xorg' at the login screen.)"
  warn "Everything else works without it."
fi
if [[ "$OS" == "Darwin" ]]; then
  echo
  warn "On first start macOS will ask for Accessibility / Input Monitoring permission."
  warn "Allow it so Saarthi can react to your typing (it never records what you type)."
fi

case ":$PATH:" in *":$BIN_DIR:"*) ;; *) warn "Add $BIN_DIR to your PATH to run 'saarthi' from a terminal." ;; esac

say "Starting Saarthi 🎉  (double-click it for reminders & notes, right-click for the menu)"
if [[ "$OS" == "Darwin" ]]; then
  open "$MAC_APP"
else
  nohup "$VENV/bin/saarthi" >/dev/null 2>&1 &
fi
