#!/usr/bin/env python3
import os
import re
import sys
import subprocess
import time
from datetime import datetime, timezone
import urllib.request
import urllib.parse

ENV_PATHS = [
    "/opt/marzban/.env",
    "/opt/pasarguard/.env",
]

KEY = "SQLALCHEMY_DATABASE_URL"
THRESHOLD_GIB = 5.0
GIB = 1024 ** 3

TELEGRAM_TOKEN = None
TELEGRAM_CHAT_ID = None
TELEGRAM_INTERVAL_H = None

TELEGRAM_CONFIG_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "telegram_config.env")


class C:
    HEADER = "\033[95m"
    OKBLUE = "\033[94m"
    OKCYAN = "\033[96m"
    OKGREEN = "\033[92m"
    WARNING = "\033[93m"
    FAIL = "\033[91m"
    ENDC = "\033[0m"
    BOLD = "\033[1m"


def clear_screen():
    os.system("cls" if os.name == "nt" else "clear")


def read_env_value(key=KEY, paths=ENV_PATHS):
    for path in paths:
        if not os.path.exists(path):
            continue
        try:
            with open(path, "r", encoding="utf-8", errors="ignore") as f:
                for line in f:
                    line = line.strip()
                    if not line or line.startswith("#"):
                        continue
                    if line.startswith(key):
                        val = line.split("=", 1)[1].strip()
                        if (val.startswith('"') and val.endswith('"')) or (val.startswith("'") and val.endswith("'")):
                            val = val[1:-1]
                        print(f"{C.OKGREEN}ENV file found: {path}{C.ENDC}")
                        return val
        except:
            pass
    return None


def parse_mysql_url(url):
    pattern = r"mysql[^:]*://(?P<user>[^:]+):(?P<pwd>[^@]+)@(?P<host>[^/:]+)(:(?P<port>\d+))?/(?P<db>.+)"
    m = re.match(pattern, url)
    if not m:
        raise ValueError("Invalid DB URL")
    return {
        "user": m.group("user"),
        "pwd": m.group("pwd"),
        "host": m.group("host"),
        "port": int(m.group("port")) if m.group("port") else None,
        "db": m.group("db"),
    }


def get_db_config():
    env = read_env_value()
    if not env:
        print(f"{C.FAIL}{KEY} not found in:{C.ENDC}")
        for p in ENV_PATHS:
            print(" - " + p)
        sys.exit(1)
    try:
        return parse_mysql_url(env)
    except Exception as e:
        print(f"{C.FAIL}Failed to parse DB URL: {e}{C.ENDC}")
        sys.exit(1)


def fmt_gb(bytes_val):
    try:
        b = float(bytes_val)
    except:
        return "N/A"
    return f"{b / GIB:.2f} GB"


def print_user_table(rows, second_col_title, title=None):
    if title:
        print(f"{C.BOLD}{title}{C.ENDC}\n")
    if not rows:
        print(f"{C.OKGREEN}No results.{C.ENDC}")
        input("\nPress Enter to return...")
        return

    no_w = 3
    username_w = max([len(r[0]) for r in rows] + [8])
    val_w = max([len(r[1]) for r in rows] + [len(second_col_title)])

    header = f"{'No.':<{no_w}}  {'Username':<{username_w}}  {second_col_title:<{val_w}}"
    sep = "=" * len(header)

    print(header)
    print(sep)
    for i, (username, val) in enumerate(rows, start=1):
        print(f"{i:<{no_w}}  {username:<{username_w}}  {val:<{val_w}}")

    print()
    input("Press Enter to return...")


def with_db(cfg, connector_fn, cli_fn):
    try:
        return connector_fn(cfg)
    except ImportError:
        try:
            return cli_fn(cfg)
        except Exception as e:
            print(f"{C.FAIL}{e}{C.ENDC}")
            sys.exit(1)
    except Exception:
        try:
            return cli_fn(cfg)
        except Exception as e:
            print(f"{C.FAIL}{e}{C.ENDC}")
            sys.exit(1)


def mysql_connect(cfg_inner):
    import mysql.connector

    conn_args = {
        "host": cfg_inner["host"],
        "user": cfg_inner["user"],
        "password": cfg_inner["pwd"],
        "database": cfg_inner["db"],
    }
    if cfg_inner.get("port"):
        conn_args["port"] = cfg_inner["port"]
    return mysql.connector.connect(**conn_args)


def mysql_cli(cfg_inner, sql):
    cmd = ["mysql", "-N", "-s", "-u", cfg_inner["user"], "-h", cfg_inner["host"]]
    if cfg_inner.get("port"):
        cmd += ["-P", str(cfg_inner["port"])]
    cmd += [cfg_inner["db"], "-e", sql]

    env = os.environ.copy()
    env["MYSQL_PWD"] = cfg_inner["pwd"]

    proc = subprocess.run(cmd, capture_output=True, text=True, env=env)
    if proc.returncode != 0:
        raise RuntimeError(proc.stderr)
    return proc.stdout.strip().splitlines()


def get_low_volume_rows(cfg):
    def process(username, dl_raw, used_raw):
        if dl_raw in (None, "", 0, "0"):
            return str(username), "∞"
        try:
            dl_n = int(dl_raw)
        except:
            return None
        try:
            used_n = int(used_raw)
        except:
            used_n = 0
        remaining = max(0, dl_n - used_n)
        if remaining < THRESHOLD_GIB * GIB:
            return str(username), fmt_gb(remaining)
        return None

    def connector_part(cfg_inner):
        cnx = mysql_connect(cfg_inner)
        cur = cnx.cursor(dictionary=True)
        cur.execute("SELECT username, data_limit, used_traffic FROM users")
        rows_out = []
        for r in cur:
            res = process(r.get("username") or "", r.get("data_limit"), r.get("used_traffic") or 0)
            if res:
                rows_out.append(res)
        cur.close()
        cnx.close()
        return rows_out

    def cli_part(cfg_inner):
        lines = mysql_cli(cfg_inner, "SELECT username, data_limit, used_traffic FROM users;")
        rows_out = []
        for line in lines:
            if not line:
                continue
            parts = line.split("\t")
            if not parts:
                continue
            username = parts[0]
            dl_raw = parts[1] if len(parts) > 1 else ""
            used_raw = parts[2] if len(parts) > 2 else "0"
            res = process(username, dl_raw, used_raw)
            if res:
                rows_out.append(res)
        return rows_out

    return with_db(cfg, connector_part, cli_part)


def pretty_time_left(delta_seconds):
    if delta_seconds < 0:
        return "expired"
    s = int(delta_seconds)
    d = s // 86400
    h = (s % 86400) // 3600
    return f"{d} days {h} hours"


def pretty_time_since(delta_seconds):
    if delta_seconds < 0:
        return "in the future"
    s = int(delta_seconds)
    d = s // 86400
    h = (s % 86400) // 3600
    return f"{d} days {h} hours ago"


def normalize_expire_value(val):
    if val is None:
        return None
    if hasattr(val, "tzinfo"):
        if val.tzinfo:
            return val.astimezone(timezone.utc).replace(tzinfo=None)
        return val
    s = str(val).strip()
    if s == "":
        return None
    if re.fullmatch(r"\d+", s):
        n = int(s)
        if n > 10**12:
            n //= 1000
        return datetime.fromtimestamp(n, tz=timezone.utc).replace(tzinfo=None)

    fmts = ["%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d"]
    for fmt in fmts:
        try:
            return datetime.strptime(s, fmt)
        except:
            pass

    try:
        dt = datetime.fromisoformat(s)
        if dt.tzinfo:
            return dt.astimezone(timezone.utc).replace(tzinfo=None)
        return dt
    except:
        return None


ROBUST_WHERE = """
(
  (expire BETWEEN UNIX_TIMESTAMP() AND UNIX_TIMESTAMP() + 172800)
  OR (expire/1000 BETWEEN UNIX_TIMESTAMP() AND UNIX_TIMESTAMP() + 172800)
  OR (UNIX_TIMESTAMP(expire) BETWEEN UNIX_TIMESTAMP() AND UNIX_TIMESTAMP() + 172800)
)
"""

ROBUST_SELECT = f"SELECT username, expire FROM users WHERE {ROBUST_WHERE} ORDER BY expire ASC;"


def get_expiring_rows(cfg):
    def process(username, exp_raw, now):
        exp_dt = normalize_expire_value(exp_raw)
        if exp_dt is None:
            return None
        delta = (exp_dt - now).total_seconds()
        return str(username), pretty_time_left(delta)

    def connector_part(cfg_inner):
        cnx = mysql_connect(cfg_inner)
        cur = cnx.cursor(dictionary=True)
        cur.execute(ROBUST_SELECT)
        now = datetime.utcnow()
        rows = []
        for r in cur:
            res = process(r.get("username") or "", r.get("expire"), now)
            if res:
                rows.append(res)
        cur.close()
        cnx.close()
        return rows

    def cli_part(cfg_inner):
        lines = mysql_cli(cfg_inner, ROBUST_SELECT)
        now = datetime.utcnow()
        rows = []
        for line in lines:
            if not line:
                continue
            parts = line.split("\t")
            if not parts:
                continue
            username = parts[0]
            exp_raw = parts[1] if len(parts) > 1 else ""
            res = process(username, exp_raw, now)
            if res:
                rows.append(res)
        return rows

    return with_db(cfg, connector_part, cli_part)


def get_inactive_rows(cfg):
    THREE_DAYS = 3 * 86400

    def parse_online(val):
        if val is None:
            return None
        if isinstance(val, datetime):
            return val
        s = str(val).strip()
        if not s:
            return None
        try:
            return datetime.strptime(s, "%Y-%m-%d %H:%M:%S")
        except:
            return None

    def process(username, online_raw, now):
        online_dt = parse_online(online_raw)
        if online_dt is None:
            return None
        delta = (now - online_dt).total_seconds()
        if delta < THREE_DAYS:
            return None
        last_str = online_dt.strftime("%Y-%m-%d %H:%M:%S")
        return str(username), f"{last_str} ({pretty_time_since(delta)})"

    def connector_part(cfg_inner):
        cnx = mysql_connect(cfg_inner)
        cur = cnx.cursor(dictionary=True)
        cur.execute("SELECT username, online_at FROM users WHERE online_at IS NOT NULL")
        now = datetime.utcnow()
        rows = []
        for r in cur:
            res = process(r.get("username") or "", r.get("online_at"), now)
            if res:
                rows.append(res)
        cur.close()
        cnx.close()
        return rows

    def cli_part(cfg_inner):
        lines = mysql_cli(cfg_inner, "SELECT username, online_at FROM users WHERE online_at IS NOT NULL;")
        now = datetime.utcnow()
        rows = []
        for line in lines:
            if not line:
                continue
            parts = line.split("\t")
            if not parts:
                continue
            username = parts[0]
            online_raw = parts[1] if len(parts) > 1 else ""
            res = process(username, online_raw, now)
            if res:
                rows.append(res)
        return rows

    return with_db(cfg, connector_part, cli_part)


def build_report_text(cfg):
    low_rows = get_low_volume_rows(cfg)
    exp_rows = get_expiring_rows(cfg)
    inactive_rows = get_inactive_rows(cfg)

    parts = []
    parts.append("Low volume users (< {:.1f} GiB):".format(THRESHOLD_GIB))
    if not low_rows:
        parts.append("  None")
    else:
        for i, (u, r) in enumerate(low_rows, start=1):
            parts.append(f"  {i}. {u} - {r}")

    parts.append("")
    parts.append("Users expiring within 48 hours:")
    if not exp_rows:
        parts.append("  None")
    else:
        for i, (u, t) in enumerate(exp_rows, start=1):
            parts.append(f"  {i}. {u} - {t}")

    parts.append("")
    parts.append("Users inactive for more than 3 days:")
    if not inactive_rows:
        parts.append("  None")
    else:
        for i, (u, t) in enumerate(inactive_rows, start=1):
            parts.append(f"  {i}. {u} - {t}")

    return "\n".join(parts)


def send_telegram_message(token, chat_id, text):
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    data = urllib.parse.urlencode({"chat_id": chat_id, "text": text}).encode("utf-8")
    req = urllib.request.Request(url, data=data)
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            if resp.status != 200:
                raise RuntimeError(f"HTTP {resp.status}")
    except Exception as e:
        print(f"{C.FAIL}Telegram send error: {e}{C.ENDC}")
        return False
    return True


def load_telegram_config():
    global TELEGRAM_TOKEN, TELEGRAM_CHAT_ID, TELEGRAM_INTERVAL_H
    if not os.path.exists(TELEGRAM_CONFIG_FILE):
        try:
            with open(TELEGRAM_CONFIG_FILE, "w", encoding="utf-8") as f:
                f.write("# Telegram config\n")
        except:
            return
        return
    try:
        with open(TELEGRAM_CONFIG_FILE, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                k, v = line.split("=", 1)
                k = k.strip().upper()
                v = v.strip()
                if k == "TOKEN":
                    TELEGRAM_TOKEN = v
                elif k == "CHAT_ID":
                    TELEGRAM_CHAT_ID = v
                elif k == "INTERVAL_H":
                    try:
                        TELEGRAM_INTERVAL_H = float(v)
                    except:
                        TELEGRAM_INTERVAL_H = None
    except:
        pass


def save_telegram_config():
    global TELEGRAM_TOKEN, TELEGRAM_CHAT_ID, TELEGRAM_INTERVAL_H
    try:
        with open(TELEGRAM_CONFIG_FILE, "w", encoding="utf-8") as f:
            if TELEGRAM_TOKEN:
                f.write(f"TOKEN={TELEGRAM_TOKEN}\n")
            if TELEGRAM_CHAT_ID:
                f.write(f"CHAT_ID={TELEGRAM_CHAT_ID}\n")
            if TELEGRAM_INTERVAL_H is not None:
                f.write(f"INTERVAL_H={TELEGRAM_INTERVAL_H}\n")
    except Exception as e:
        print(f"{C.WARNING}Failed to save Telegram config: {e}{C.ENDC}")


def telegram_send_once(cfg):
    global TELEGRAM_TOKEN, TELEGRAM_CHAT_ID
    if not TELEGRAM_TOKEN or not TELEGRAM_CHAT_ID:
        print(f"{C.FAIL}Telegram is not configured. Configure it first.{C.ENDC}")
        input("Press Enter to return...")
        return
    text = build_report_text(cfg)
    ok = send_telegram_message(TELEGRAM_TOKEN, TELEGRAM_CHAT_ID, text)
    if ok:
        print(f"{C.OKGREEN}Report sent to Telegram.{C.ENDC}")
    else:
        print(f"{C.FAIL}Failed to send report to Telegram.{C.ENDC}")
    input("Press Enter to return...")


def telegram_auto_scheduler(cfg):
    global TELEGRAM_TOKEN, TELEGRAM_CHAT_ID, TELEGRAM_INTERVAL_H
    if not TELEGRAM_TOKEN or not TELEGRAM_CHAT_ID or TELEGRAM_INTERVAL_H is None:
        print(f"{C.FAIL}Telegram is not fully configured.{C.ENDC}")
        input("Press Enter to return...")
        return
    interval_s = int(TELEGRAM_INTERVAL_H * 3600)
    if interval_s <= 0:
        print(f"{C.FAIL}Invalid interval.{C.ENDC}")
        input("Press Enter to return...")
        return
    print(f"{C.OKGREEN}Auto sending every {TELEGRAM_INTERVAL_H} hours. Press Ctrl+C to stop.{C.ENDC}")
    time.sleep(1)
    while True:
        try:
            text = build_report_text(cfg)
            ok = send_telegram_message(TELEGRAM_TOKEN, TELEGRAM_CHAT_ID, text)
            now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            if ok:
                print(f"[{now}] Report sent.")
            else:
                print(f"[{now}] Failed to send report.")
            time.sleep(interval_s)
        except KeyboardInterrupt:
            print("\nStopped auto sending.")
            time.sleep(1)
            break


def configure_telegram():
    global TELEGRAM_TOKEN, TELEGRAM_CHAT_ID, TELEGRAM_INTERVAL_H
    clear_screen()
    print(f"{C.HEADER}{C.BOLD}Telegram configuration{C.ENDC}\n")

    if TELEGRAM_TOKEN:
        print(f"Current bot token: {TELEGRAM_TOKEN}")
    token = input("Bot token (leave empty to keep current): ").strip()
    if token:
        TELEGRAM_TOKEN = token

    if TELEGRAM_CHAT_ID:
        print(f"Current chat ID: {TELEGRAM_CHAT_ID}")
    chat = input("Chat ID (leave empty to keep current): ").strip()
    if chat:
        TELEGRAM_CHAT_ID = chat

    if TELEGRAM_INTERVAL_H is not None:
        print(f"Current interval hours: {TELEGRAM_INTERVAL_H}")
    interval_str = input("Interval (hours, leave empty to keep current): ").strip()
    if interval_str:
        try:
            h = float(interval_str)
            if h <= 0:
                print(f"{C.FAIL}Interval must be > 0.{C.ENDC}")
            else:
                TELEGRAM_INTERVAL_H = h
        except:
            print(f"{C.FAIL}Invalid interval value.{C.ENDC}")

    save_telegram_config()

    if TELEGRAM_TOKEN and TELEGRAM_CHAT_ID and TELEGRAM_INTERVAL_H is not None:
        print(f"{C.OKGREEN}Telegram configuration saved.{C.ENDC}")
    else:
        print(f"{C.WARNING}Telegram configuration is incomplete.{C.ENDC}")
    input("Press Enter to return...")


def telegram_menu(cfg):
    while True:
        clear_screen()
        print(f"{C.HEADER}{C.BOLD}=== Telegram Tools ==={C.ENDC}\n")
        print(f"{C.OKCYAN}1){C.ENDC} Configure / edit settings")
        print(f"{C.OKCYAN}2){C.ENDC} Send report now")
        print(f"{C.OKCYAN}3){C.ENDC} Start auto send every N hours")
        print(f"{C.OKCYAN}0){C.ENDC} Back\n")
        c = input("Select: ").strip()
        if c == "1":
            configure_telegram()
        elif c == "2":
            telegram_send_once(cfg)
        elif c == "3":
            telegram_auto_scheduler(cfg)
        elif c == "0":
            break
        else:
            print(f"{C.WARNING}Invalid option{C.ENDC}")
            input("Press Enter...")


def run_ssl_manager():
    clear_screen()
    print(f"{C.HEADER}{C.BOLD}PasarGuard SSL Manager{C.ENDC}\n")
    print("Loading external SSL wizard...\n")
    cmd = [
        "bash",
        "-lc",
        "bash <(curl -Ls https://raw.githubusercontent.com/dev-ir/PasarGuard-SSL-Manager/refs/heads/main/main.sh)"
    ]
    try:
        subprocess.run(cmd, check=True)
    except subprocess.CalledProcessError as e:
        print(f"{C.FAIL}SSL manager exited with error code {e.returncode}.{C.ENDC}")
    except Exception as e:
        print(f"{C.FAIL}SSL manager error: {e}{C.ENDC}")
    input("\nPress Enter to return to menu...")


def menu():
    cfg = get_db_config()
    load_telegram_config()

    while True:
        clear_screen()
        print(f"{C.HEADER}{C.BOLD}=== Marzban/PasarGuard Tools ==={C.ENDC}\n")
        print(f"{C.OKCYAN}1){C.ENDC} Low remaining volume (< {THRESHOLD_GIB} GiB)")
        print(f"{C.OKCYAN}2){C.ENDC} Users expiring in next 48 hours")
        print(f"{C.OKCYAN}3){C.ENDC} Users inactive for more than 3 days")
        print(f"{C.OKCYAN}4){C.ENDC} Telegram tools")
        print(f"{C.OKCYAN}5){C.ENDC} SSL manager")
        print(f"{C.OKCYAN}0){C.ENDC} Exit\n")

        c = input("Select: ").strip()

        if c == "1":
            clear_screen()
            rows = get_low_volume_rows(cfg)
            print_user_table(rows, "Remaining", title="Low Volume Users")
        elif c == "2":
            clear_screen()
            rows = get_expiring_rows(cfg)
            print_user_table(rows, "Time Left", title="Expiring Users (48h)")
        elif c == "3":
            clear_screen()
            rows = get_inactive_rows(cfg)
            print_user_table(rows, "Last Online", title="Inactive Users (> 3 days)")
        elif c == "4":
            telegram_menu(cfg)
        elif c == "5":
            run_ssl_manager()
        elif c == "0":
            sys.exit(0)
        else:
            print(f"{C.WARNING}Invalid option{C.ENDC}")
            input("Press Enter...")


if __name__ == "__main__":
    try:
        menu()
    except KeyboardInterrupt:
        print("\nCanceled by user. Exiting...")
        sys.exit(0)
