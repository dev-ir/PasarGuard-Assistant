#!/bin/bash

SCRIPT_PATH="/usr/local/bin/ps-assis"
if [[ "$0" != "$SCRIPT_PATH" ]]; then
  echo -e "\033[0;33m[!] Installing ps-assis to /usr/local/bin ...\033[0m"
  cp "$0" "$SCRIPT_PATH" 2>/dev/null || {
    echo -e "\033[0;31m[X] Permission denied. Run with: sudo ./ps-assis\033[0m"
    exit 1
  }
  chmod +x "$SCRIPT_PATH"
  echo -e "\033[0;32m[✓] Installed! Now run with: sudo ps-assis\033[0m"
  exit 0
fi

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[0;33m'
CYAN='\033[0;36m'
NC='\033[0m'
VERSION="1.1"

RAW_URL="https://raw.githubusercontent.com/dev-ir/PasarGuard-Assistant/refs/heads/master/init.py"
PY_PATH="/usr/local/bin/ps-init.py"

if [[ $EUID -ne 0 ]]; then
  echo -e "${RED}Run as root: sudo ps-assis${NC}"
  exit 1
fi

dvhost_assis_install() {
    echo -e "${CYAN}[*] Installing / Updating PasarGuard Assistant...${NC}"

    command -v curl >/dev/null || {
        echo -e "${RED}[X] curl is not installed.${NC}"
        return 1
    }

    echo -e "${YELLOW}[>] Downloading init.py ...${NC}"

    if curl -s -L "$RAW_URL" -o "$PY_PATH"; then
        chmod +x "$PY_PATH"
        echo -e "${GREEN}[✓] Installed!${NC}"
    else
        echo -e "${RED}[X] Download failed.${NC}"
    fi
}

dvhost_assis_run() {
    if [[ ! -f "$PY_PATH" ]]; then
        echo -e "${RED}[X] Assistant not installed.${NC}"
        return
    fi

    python3 "$PY_PATH"
}

dvhost_assis_remove() {
    echo -e "${RED}[*] Removing PasarGuard Assistant...${NC}"

    [[ -f "$PY_PATH" ]] && rm -f "$PY_PATH"

    echo -e "${YELLOW}[>] Removing ps-assis command...${NC}"

    (sleep 1; rm -f "$SCRIPT_PATH") &
    
    echo -e "${GREEN}[✓] Removed successfully.${NC}"
    echo -e "${CYAN}Command will no longer exist after exit.${NC}"

    exit 0
}

dvhost_assis_draw_menu() {
    clear
    status="NOT INSTALLED"
    [[ -f "$PY_PATH" ]] && status="INSTALLED"

    cat << "EOF"
+---------------------------------------+
|  ___  ___      _   ___ ___ ___ ___    |
| | _ \/ __|___ /_\ / __/ __|_ _/ __|   |
| |  _/\__ \___/ _ \\__ \__ \| |\__ \   |
| |_|  |___/  /_/ \_\___/___/___|___/   |   
|                                       |
+---------------------------------------+
EOF
    echo -e "| PasarGuard Assistant CLI | Version: ${GREEN}${VERSION}${NC}"
    echo +---------------------------------------+
    echo -e "| Status: ${YELLOW}${status}${NC}"
    echo +---------------------------------------+
    echo -e "| 1 - Install / Update Assistant"
    echo -e "| 2 - Run Assistant"
    echo -e "| 3 - Remove Assistant (Full uninstall)"
    echo -e "| 0 - Exit"
    echo +---------------------------------------+
    echo -ne "${YELLOW}Select option: ${NC}"
}

dvhost_assis_main_menu() {
    while true; do
        dvhost_assis_draw_menu
        read -r choice
        case $choice in
            1) dvhost_assis_install ;;
            2) dvhost_assis_run ;;
            3) dvhost_assis_remove ;;
            0) exit ;;
            *) echo -e "${RED}Invalid option.${NC}" ;;
        esac

        echo -e "\nPress Enter to return..."
        read
    done
}

dvhost_assis_main_menu
