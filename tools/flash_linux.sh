#!/usr/bin/env bash
# Linux CLI flasher wrapper for Canaan Avalon Nano 3S (K230 SPI NAND)
# Uses official Canaan/Kendryte k230_flash_cli to flash .kdimg packages.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
DEFAULT_IMG="$REPO_DIR/firmware/Phosphor_OS_Nano3S_OC_v5.kdimg"
EXPECTED_SHA="b065f83ae0f8a124af9ec7141e52e77efb4e0ec9b3b358a3d5bd5802e424b29e"

IMG="${1:-$DEFAULT_IMG}"
TOOL_DIR="$SCRIPT_DIR/.k230_flash"

if [ ! -f "$IMG" ]; then
  echo "Error: firmware image not found: $IMG"
  echo "Usage: sudo $0 [path/to/Phosphor_OS_Nano3S_OC_v5.kdimg]"
  exit 1
fi

if [ "$IMG" = "$DEFAULT_IMG" ] && command -v sha256sum >/dev/null 2>&1; then
  ACTUAL_SHA="$(sha256sum "$IMG" | awk '{print $1}')"
  if [ "$ACTUAL_SHA" != "$EXPECTED_SHA" ]; then
    echo "Error: SHA-256 mismatch for $IMG"
    echo "  expected: $EXPECTED_SHA"
    echo "  actual:   $ACTUAL_SHA"
    exit 1
  fi
  echo "SHA-256 OK: $ACTUAL_SHA"
fi

ARCH="$(uname -m)"
case "$ARCH" in
  x86_64|amd64) ASSET_ARCH="x86_64" ;;
  aarch64|arm64) ASSET_ARCH="arm64" ;;
  *)
    echo "Unsupported architecture: $ARCH"
    echo "Download manually from https://github.com/kendryte/k230_flash/releases"
    exit 1
    ;;
esac

BIN="$(find "$TOOL_DIR" -maxdepth 3 -type f -name 'k230_flash_cli' 2>/dev/null | head -n 1 || true)"

if [ -z "$BIN" ]; then
  echo "Downloading official kendryte/k230_flash_cli for Linux ($ASSET_ARCH)..."
  mkdir -p "$TOOL_DIR"
  URL="$(curl -fsSL https://api.github.com/repos/kendryte/k230_flash/releases/latest \
    | grep -oE "https://[^\"]+k230_flash_cli-linux-${ASSET_ARCH}[^\"]*\.tar\.gz" \
    | head -n 1)"
  if [ -z "$URL" ]; then
    echo "Could not auto-detect release URL. Download manually from:"
    echo "  https://github.com/kendryte/k230_flash/releases"
    exit 1
  fi
  curl -fsSL "$URL" -o "$TOOL_DIR/k230_flash.tar.gz"
  tar -xzf "$TOOL_DIR/k230_flash.tar.gz" -C "$TOOL_DIR"
  rm -f "$TOOL_DIR/k230_flash.tar.gz"
  BIN="$(find "$TOOL_DIR" -maxdepth 3 -type f -name 'k230_flash_cli' | head -n 1)"
  chmod +x "$BIN"
fi

echo "Using flasher: $BIN"
echo "Connect your Avalon Nano 3S in USB upgrade mode (BootROM)..."

if [ "$(id -u)" -ne 0 ]; then
  echo "Note: USB flashing usually requires root privileges (re-run with sudo if permission is denied)."
fi

"$BIN" -m SPI_NAND -f "$IMG"
echo "Flashing complete. Power-cycle or wait for the miner to reboot."
