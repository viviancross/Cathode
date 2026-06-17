#!/usr/bin/env bash
# Cathode — build & install as a Flatpak (from this source folder).
#
# ⚠️ EXPERIMENTAL: the manifest (io.github.viviancross.Cathode.yml) has not been
# built/tested by the author (it was written on Windows). Expect to iterate.
#
# This installs the freedesktop runtime/SDK + the host mpv Flatpak, then builds
# Cathode and installs it into your user Flatpak scope. No sudo required.
set -e

DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
APP="io.github.viviancross.Cathode"
RT_VER="23.08"

echo "=== Cathode Flatpak Installer ==="

if ! command -v flatpak >/dev/null 2>&1; then
    echo "  ERROR: flatpak is not installed. Install it from your distro first."
    exit 1
fi

# flatpak-builder may be a native binary or the org.flatpak.Builder Flatpak.
if command -v flatpak-builder >/dev/null 2>&1; then
    FB() { flatpak-builder "$@"; }
elif flatpak info org.flatpak.Builder >/dev/null 2>&1; then
    FB() { flatpak run org.flatpak.Builder "$@"; }
else
    echo "  ERROR: flatpak-builder not found. Install it with one of:"
    echo "    flatpak install -y flathub org.flatpak.Builder"
    echo "    (or your distro's 'flatpak-builder' package)"
    exit 1
fi

echo "[1/2] Installing runtime, SDK and host mpv (user scope)…"
flatpak --user remote-add --if-not-exists flathub \
    https://flathub.org/repo/flathub.flatpakrepo
flatpak --user install -y flathub \
    "org.freedesktop.Platform//${RT_VER}" \
    "org.freedesktop.Sdk//${RT_VER}" \
    io.mpv.Mpv

echo "[2/2] Building + installing ${APP}…"
FB --user --install --force-clean "$DIR/.flatpak-build" "$DIR/${APP}.yml"

echo
echo "=== Done. Launch with:  flatpak run ${APP}  ==="
echo "(or from your app menu — a 'Cathode' entry was installed)."
