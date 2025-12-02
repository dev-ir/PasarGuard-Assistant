#!/bin/bash

SCRIPT_PATH="/usr/local/bin/ps-assis"
if [[ "$0" != "$SCRIPT_PATH" ]]; then
  echo -e "\033[0;33m[!] Installing ps-assis to /usr/local/bin ...\033[0m"
  cp "$0" "$SCRIPT_PATH" 2>/dev/null || {
    echo -e "\033[0;31m[X] Permission denied. Run this script with: sudo ./ps-assis\033[0m"
    exit 1
  }
  chmod +x "$SCRIPT_PATH"
  echo -e "\033[0;32m[✓] Installed! Now run with: sudo ps-assis\033[0m"
  exit 0
fi

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[0;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
NC='\033[0m'
VERSION="1.0"

RAW_URL="https://raw.githubusercontent.com/dev-ir/PasarGuard-Assistant/refs/heads/master/init.py"
PY_PATH="/usr/local/bin/ps-assistant-init.py"

if [[ $EUID -ne 0 ]]; then
  echo -e "${RED}Please run this script as root (sudo ps-assis).${NC}"
  exit 1
fi

dvhost_assis_install() {
    echo -e "${CYAN}[*] Installing / Updating PasarGuard Assistant...${NC}"

    command -v curl >/dev/null 2>&1 || {
        echo -e "${RED}[X] curl is not installed. Please install curl first.${NC}"
        return 1
    }

    echo -e "${YELLOW}[>] Downloading init.py from GitHub...${NC}"
    if curl -s -L "$RAW_URL" -o "$PY_PATH"; then
        chmod +x "$PY_PATH" 2>/dev/null
        echo -e "${GREEN}[✓] Installed at: ${PY_PATH}${NC}"
        echo -e "${GREEN}[✓] You can run it from menu (option 2).${NC}"
    else
        echo -e "${RED}[X] Failed to download init.py${NC}"
        return 1
    fi
}

dvhost_assis_run() {
    if [[ ! -f "$PY_PATH" ]]; then
        echo -e "${RED}[X] Assistant is not installed yet.${NC}"
        echo -e "${YELLOW}[*] Please install first (option 1).${NC}"
        return 1
    fi

    command -v python3 >/dev/null 2>&1 || {
        echo -e "${RED}[X] python3 is not installed.${NC}"
        return 1
    }

    echo -e "${CYAN}[*] Running PasarGuard Assistant...${NC}"
    python3 "$PY_PATH"
}

dvhost_assis_remove() {
    echo -e "${RED}[*] Removing PasarGuard Assistant...${NC}"
    if [[ -f "$PY_PATH" ]]; then
        rm -f "$PY_PATH"
        echo -e "${GREEN}[✓] Removed: ${PY_PATH}${NC}"
    else
        echo -e "${YELLOW}[!] No installed assistant found at ${PY_PATH}${NC}"
    fi
}

dvhost_assis_draw_menu() {
    clear
    local status="NOT INSTALLED"
    [[ -f "$PY_PATH" ]] && status="INSTALLED"

    cat << "EOF"
+-------------------------------------------------------------------+
|   ██████╗  █████╗ ███████╗ █████╗ ██████╗  ██████╗  █████╗ ██████╗|
|   ██╔══██╗██╔══██╗██╔════╝██╔══██╗██╔══██╗██╔════╝ ██╔══██╗██╔══██╗|
|   ██████╔╝███████║███████╗███████║██████╔╝██║  ███╗███████║██████╔╝|
|   ██╔══██╗██╔══██║╚════██║██╔══██║██╔══██╗██║   ██║██╔══██║██╔══██╗|
|   ██████╔╝██║  ██║███████║██║  ██║██║  ██║╚██████╔╝██║  ██║██║  ██║|
|   ╚═════╝ ╚═╝  ╚═╝╚══════╝╚═╝  ╚═╝╚═╝  ╚═╝ ╚═════╝ ╚═╝  ╚═╝╚═╝  ╚═╝|
+-------------------------------------------------------------------+
EOF
    echo -e "| PasarGuard Assistant CLI         | Version: ${GREEN}${VERSION}${NC}"
    echo +-------------------------------------------------------------------+
    echo -e "| Status: ${YELLOW}${status}${NC}"
    echo -e "| Python entry: ${CYAN}${PY_PATH}${NC}"
    echo +-------------------------------------------------------------------+
    echo -e "| ${YELLOW}Choose an option:${NC}"
    echo +-------------------------------------------------------------------+
    echo -e "| 1 - Install / Update Assistant"
    echo -e "| 2 - Run Assistant"
    echo -e "| 4 - Remove Assistant"
    echo -e "| 0 - Exit"
    echo +-------------------------------------------------------------------+
    echo -ne "${YELLOW}Select option: ${NC}"
}

dvhost_assis_main_menu() {
    while true; do
        dvhost_assis_draw_menu
        read -r choice
        case $choice in
            1) dvhost_assis_install ;;
            2) dvhost_assis_run ;;
            4) dvhost_assis_remove ;;
            0) echo -e "${GREEN}Exiting...${NC}"; exit ;;
            *) echo -e "${RED}Invalid choice. Try again.${NC}" ;;
        esac
        echo -e "\nPress Enter to return to menu..."
        read -r
    done
}

dvhost_assis_main_menu
