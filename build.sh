#!/bin/bash

set -e

#########################################
# Configuration
#########################################

APP_NAME="Video Converter"
EXEC_NAME="video_converter"

PROJECT_DIR="$(cd "$(dirname "$0")" && pwd)"

SOURCE_PY="$PROJECT_DIR/video_converter.py"
ICON="$PROJECT_DIR/icone.png"

INSTALL_DIR="$HOME/.local/bin"
ICON_DIR="$HOME/.local/share/icons"
DESKTOP_DIR="$HOME/.local/share/applications"

EXEC="$INSTALL_DIR/$EXEC_NAME"
DESKTOP_FILE="$DESKTOP_DIR/$EXEC_NAME.desktop"

#########################################
# Activation du venv
#########################################

if [ -f "$PROJECT_DIR/venv/bin/activate" ]; then
    echo "→ Activation du venv..."
    source "$PROJECT_DIR/venv/bin/activate"
fi

#########################################
# Vérification de PyInstaller
#########################################

if ! python -m PyInstaller --version >/dev/null 2>&1; then
    echo
    echo "❌ PyInstaller n'est pas installé."
    echo
    echo "Installe-le avec :"
    echo
    echo "pip install pyinstaller"
    exit 1
fi

#########################################
# Nettoyage
#########################################

echo "→ Nettoyage..."

rm -rf "$PROJECT_DIR/build"
rm -rf "$PROJECT_DIR/dist"
rm -f "$PROJECT_DIR/$EXEC_NAME.spec"

rm -f "$EXEC"
rm -f "$DESKTOP_FILE"
rm -f "$ICON_DIR/$EXEC_NAME.png"

mkdir -p "$INSTALL_DIR"
mkdir -p "$ICON_DIR"
mkdir -p "$DESKTOP_DIR"

#########################################
# Compilation
#########################################

echo "→ Compilation..."

python -m PyInstaller \
    --onefile \
    --icon="$ICON" \
    "$SOURCE_PY"

#########################################
# Installation
#########################################

echo "→ Installation..."

cp "$PROJECT_DIR/dist/$EXEC_NAME" "$EXEC"
chmod +x "$EXEC"

cp "$ICON" "$ICON_DIR/$EXEC_NAME.png"

cat > "$DESKTOP_FILE" << EOF
[Desktop Entry]
Version=1.0
Type=Application
Name=$APP_NAME
Comment=Convertisseur vidéo FFmpeg
Exec=$EXEC
Icon=$ICON_DIR/$EXEC_NAME.png
Terminal=true
Categories=AudioVideo;Video;
StartupNotify=true
EOF

chmod +x "$DESKTOP_FILE"

#########################################
# Rafraîchissement KDE
#########################################

echo "→ Mise à jour du menu..."

update-desktop-database "$DESKTOP_DIR" >/dev/null 2>&1 || true
kbuildsycoca6 >/dev/null 2>&1 || true

#########################################
# Notification
#########################################

notify-send \
    "Installation terminée" \
    "$APP_NAME a été compilé et installé."

echo
echo "======================================"
echo "Installation terminée avec succès."
echo "======================================"
