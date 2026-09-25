import base64
import ctypes
import ctypes.wintypes
import hashlib
import json
import os
import re
import secrets
import shutil
import struct
import subprocess
import sys
import threading
import tkinter as tk
import uuid
import zipfile
from pathlib import Path
from tkinter import colorchooser, filedialog, messagebox
from urllib.parse import quote, urlparse

import customtkinter as ctk
import minecraft_launcher_lib as mll
import requests
from PIL import Image, ImageDraw, ImageEnhance, ImageFilter

try:
    from cryptography.fernet import Fernet, InvalidToken
    _HAS_CRYPTO = True
except Exception:
    _HAS_CRYPTO = False

# ====================================================================
#  Пути
# ====================================================================
ROOT = Path(os.getenv("APPDATA") or Path.home()) / "NexoraLauncher"
MC_DIR = str(ROOT / "minecraft")
INSTANCES = ROOT / "instances"
WALLS = ROOT / "wallpapers"
FONTS = ROOT / "fonts"
DOWNLOADS = ROOT / "downloads"
CONFIG = ROOT / "config.json"
USERS_FILE = ROOT / "users.json"
KEY_FILE = ROOT / ".key"
UA = {"User-Agent": "NexoraLauncher/1.0"}

W, H, PLAY_W = 960, 640, 430
TITLE_H = 36
PAD_Y, PAD_H = (14 + TITLE_H) / H, (H - 28 - TITLE_H) / H
NAV = [("play", "Играть"), ("game", "Игра"), ("catalog", "Каталог"), ("library", "Библиотека"),
       ("servers", "Сервера"), ("skins", "Скины"), ("style", "Оформление"), ("settings", "Настройки")]
TYPES = {"Моды": "mod", "Ресурспаки": "resourcepack", "Шейдеры": "shader", "Сборки": "modpack"}
TYPE_LABEL = {v: k for k, v in TYPES.items()}
DIRS = {"mod": "mods", "resourcepack": "resourcepacks", "shader": "shaderpacks"}
IMG_EXT = (".png", ".jpg", ".jpeg", ".webp")

# Хосты, с которых разрешено тянуть обновления
ALLOWED_UPDATE_HOSTS = {"api.github.com", "github.com", "raw.githubusercontent.com", "objects.githubusercontent.com"}

THEMES = {
    "Nexora":       dict(mode="dark", bg="#090b10", card="#11151d", field="#171c26", accent="#756cff", text="#f2f4f8", muted="#7f899a"),
    "Зелёная ночь": dict(mode="dark", bg="#16161a", card="#1f1f25", field="#2a2a32", accent="#3ba55d", text="#e8e8ee", muted="#8b8b96"),
    "Полночь":      dict(mode="dark", bg="#0e1117", card="#161b22", field="#21262d", accent="#4c8dff", text="#e6edf3", muted="#7d8590"),
    "Фиолетовая":   dict(mode="dark", bg="#15111f", card="#1e1830", field="#2b2342", accent="#a06bff", text="#ece8f7", muted="#8f86a8"),
    "Розовая":      dict(mode="dark", bg="#1a1218", card="#26181f", field="#35222c", accent="#ff5fa2", text="#f5e8ee", muted="#a58593"),
    "AMOLED":       dict(mode="dark", bg="#000000", card="#0b0b0b", field="#181818", accent="#00d084", text="#f0f0f0", muted="#808080"),
    "Светлая":      dict(mode="light", bg="#f2f3f5", card="#ffffff", field="#e4e6ea", accent="#2e9d57", text="#1a1a1f", muted="#6b6b76"),
}

DEFAULTS = {
    "nick": "Player", "profile": "", "profiles": {},
    "ram": 4096, "ram_min": 512, "jvm_args": "", "java_path": "", "res_w": 0, "res_h": 0, "fullscreen": False,
    "verify_files": True, "show_snapshots": False, "close_on_launch": False,
    "cf_key": "",
    "theme": "Nexora", "accent": "", "radius": 14, "scale": 100,
    "anim": True, "anim_speed": 100,
    "wall_on": True, "wall_file": "", "wall_dim": 55, "wall_blur": 4,
    "font_title": "", "font_body": "", "font_auto_tried": False,
    "saturation": 100, "sharpness": 0, "motion_blur": False,
    "aspect": "16:9", "show_fps": True, "watermark": True, "opt_auto": True,
    "auth_email": "", "auth_nick": "", "auth_logged": False,
    "liquid_glass": False,
    "setup_done": False,
    "language": "ru",
    "heard_from": "",
    "launcher_icon": "",
    "display_name": "",
    "auth_provider": "local",
    "ely_uuid": "",
    "ely_access_token": "",   # хранится зашифрованным
    "cape_mod_ok": False,
    "custom_servers": [],
    "update_url": "https://api.github.com/repos/FigureOffic/Nexora/releases/latest",
    # --- расширенные ---
    "gc": "G1",
    "aikar_flags": True,
    "confirm_launch": False,
    "auto_join_server": True,
    "check_updates": True,
    "always_on_top": False,
    "window_opacity": 100,
    "start_page": "play",
    "download_timeout": 30,
    "parallel_downloads": 4,
    "keep_logs": True,
    "show_console": False,
    "demo_mode": False,
    "quick_play_singleplayer": False,
    "game_dir_override": "",
    "assets_index_force": "",
    "max_fps_arg": 0,
    "vsync_hint": False,
    "discord_rpc": False,
    "minimize_on_launch": False,
    "remember_last_server": True,
    "export_crash_reports": True,
    "mod_update_check": False,
    "safe_mode": False,
    "jvm_debug": False,
    "jvm_debug_port": 5005,
    "extra_classpath": "",
    "env_vars": "",
    "proxy_host": "",
    "proxy_port": 0,
    "launcher_lang": "ru",
    "sidebar_compact": False,
    "hide_status": False,
    "double_click_play": False,
    "backup_before_install": False,
    "auto_backup_days": 7,
    "sound_on_ready": False,
    "net_retries": 3,
    "prefer_loader": "fabric",
    "jvm_xms_percent": 0,
}

APPEARANCE_KEYS = ["theme", "accent", "radius", "scale", "anim", "anim_speed", "wall_on",
                   "wall_file", "wall_dim", "wall_blur", "font_title", "font_body", "liquid_glass"]

T = {}
FONT = {"title": "Segoe UI", "body": "Segoe UI", "loaded": []}
ANIM = {"on": True, "speed": 1.0}

# ====================================================================
#  Безопасность: ключ + шифрование
# ====================================================================
def get_or_create_key() -> bytes:
    """32-байтный ключ в %APPDATA%/NexoraLauncher/.key (вне репозитория)."""
    try:
        if KEY_FILE.exists():
            data = KEY_FILE.read_bytes()
            if len(data) in (32, 44):  # raw или urlsafe-b64
                return data
        ROOT.mkdir(parents=True, exist_ok=True)
        key = secrets.token_bytes(32)
        KEY_FILE.write_bytes(key)
        try:
            os.chmod(KEY_FILE, 0o600)
        except Exception:
            pass
        return key
    except Exception:
        # крайний случай — ключ в памяти (данные не переживут перезапуск)
        return secrets.token_bytes(32)


def _fernet() -> "Fernet":
    if not _HAS_CRYPTO:
        raise RuntimeError(
            "Не установлена библиотека cryptography.\n"
            "Выполни: pip install cryptography"
        )
    key = get_or_create_key()
    if len(key) == 44:
        return Fernet(key)
    return Fernet(base64.urlsafe_b64encode(key))


def enc_str(s: str) -> str:
    """Шифрует строку. Пустая строка → пустая."""
    if not s:
        return ""
    if not _HAS_CRYPTO:
        return ""
    try:
        return _fernet().encrypt(s.encode("utf-8")).decode("ascii")
    except Exception:
        return ""


def dec_str(s: str) -> str:
    """Расшифровывает строку. Битый/старый формат → ''."""
    if not s:
        return ""
    if not _HAS_CRYPTO:
        return ""
    try:
        return _fernet().decrypt(s.encode("ascii")).decode("utf-8")
    except (InvalidToken, Exception):
        return ""


def load_users() -> dict:
    if not USERS_FILE.exists():
        return {}
    try:
        raw = USERS_FILE.read_bytes()
        # новый формат
        try:
            data = _fernet().decrypt(raw)
            return json.loads(data.decode("utf-8"))
        except Exception:
            pass
        # старый XOR-формат — читаем и молча мигрируем при следующем save_users
        try:
            return json.loads(raw.decode("utf-8"))
        except Exception:
            return {}
    except Exception:
        return {}


def save_users(users: dict):
    ROOT.mkdir(parents=True, exist_ok=True)
    plain = json.dumps(users, ensure_ascii=False).encode("utf-8")
    USERS_FILE.write_bytes(_fernet().encrypt(plain))


# ====================================================================
#  Утилиты
# ====================================================================
def _norm_color(c):
    if c is None:
        return None
    if isinstance(c, (tuple, list)):
        c = c[-1] if c else None
    if not c or not isinstance(c, str):
        return None
    c = c.strip().lower()
    if c in ("transparent", "none", ""):
        return None
    if not c.startswith("#"):
        c = "#" + c
    if len(c) == 4:
        c = "#" + "".join(ch * 2 for ch in c[1:])
    if len(c) != 7:
        return None
    try:
        int(c[1:], 16)
    except ValueError:
        return None
    return c


def hex2rgb(h):
    h = _norm_color(h)
    if not h:
        return (0, 0, 0)
    h = h.lstrip("#")
    return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))


def lerp(c1, c2, t):
    a = _norm_color(c1)
    b = _norm_color(c2)
    if not a and not b:
        return "#000000"
    if not a:
        return b
    if not b:
        return a
    r1, g1, b1 = hex2rgb(a)
    r2, g2, b2 = hex2rgb(b)
    return "#%02x%02x%02x" % (
        round(r1 + (r2 - r1) * t),
        round(g1 + (g2 - g1) * t),
        round(b1 + (b2 - b1) * t),
    )


def ease(t):
    t = max(0.0, min(1.0, t))
    return t * t * (3.0 - 2.0 * t)


def tween(w, ms, fn, done=None, key=None):
    if not ANIM["on"] or ms <= 0:
        try:
            fn(1.0)
        except tk.TclError:
            return
        if done:
            done()
        return

    if key is not None:
        if not hasattr(w, "_tweens"):
            w._tweens = {}
        old = w._tweens.pop(key, None)
        if old:
            try:
                w.after_cancel(old)
            except (tk.TclError, ValueError):
                pass

    duration = max(40, int(ms / max(0.3, ANIM["speed"])))
    import time
    started = time.perf_counter()

    def tick():
        try:
            elapsed = (time.perf_counter() - started) * 1000.0
            p = min(1.0, elapsed / duration)
            fn(ease(p))
            if p < 1.0:
                token = w.after(16, tick)
                if key is not None:
                    w._tweens[key] = token
            else:
                if key is not None:
                    w._tweens.pop(key, None)
                if done:
                    done()
        except tk.TclError:
            if key is not None and hasattr(w, "_tweens"):
                w._tweens.pop(key, None)

    tick()


def folder_size(p):
    p = Path(p)
    return sum(f.stat().st_size for f in p.rglob("*") if f.is_file()) if p.exists() else 0


def fmt_num(n):
    return f"{n / 1e6:.1f}M" if n >= 1e6 else f"{n / 1e3:.0f}K" if n >= 1e3 else str(n)


def slug(name):
    return re.sub(r"[^\w\-]+", "_", name.strip())[:40] or "profile"


def unique_slug(name):
    base, i = slug(name), 1
    p = INSTANCES / base
    while p.exists():
        i += 1
        p = INSTANCES / f"{base}_{i}"
    return p.name


def _check_host(url: str, allowed: set) -> bool:
    try:
        return urlparse(url).hostname in allowed
    except Exception:
        return False


def download(url, dest, expected_sha512=None, expected_sha1=None, timeout=30):
    """Скачивает файл. Если передан хэш — проверяет и удаляет при несовпадении."""
    dest = Path(dest)
    with requests.get(url, headers=UA, stream=True, timeout=timeout) as r:
        r.raise_for_status()
        tmp = dest.with_suffix(dest.suffix + ".part")
        with open(tmp, "wb") as f:
            for chunk in r.iter_content(65536):
                f.write(chunk)
    if expected_sha512 or expected_sha1:
        data = tmp.read_bytes()
        if expected_sha512:
            h = hashlib.sha512(data).hexdigest()
            if h.lower() != expected_sha512.lower():
                tmp.unlink(missing_ok=True)
                raise RuntimeError("SHA-512 не совпал — файл удалён")
        if expected_sha1:
            h = hashlib.sha1(data).hexdigest()
            if h.lower() != expected_sha1.lower():
                tmp.unlink(missing_ok=True)
                raise RuntimeError("SHA-1 не совпал — файл удалён")
    tmp.replace(dest)


def loader_name(p):
    lid = (p.get("launch_id") or "")
    if lid:
        low = lid.lower()
        return ("Fabric" if low.startswith("fabric") else "Quilt" if low.startswith("quilt")
                else "Forge" if "forge" in low else "Сборка")
    return "Fabric" if p.get("fabric") else "Vanilla"


def find_fabric(mc):
    return next((v["id"] for v in mll.utils.get_installed_versions(MC_DIR)
                 if v["id"].startswith("fabric-loader-") and v["id"].endswith("-" + mc)), None)


def hash_password(password: str) -> dict:
    salt = secrets.token_bytes(16)
    key = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, 120000)
    return {"s": base64.b64encode(salt).decode(), "h": base64.b64encode(key).decode()}


def verify_password(password: str, data: dict) -> bool:
    try:
        salt = base64.b64decode(data["s"])
        expected = base64.b64decode(data["h"])
        key = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, 120000)
        return secrets.compare_digest(key, expected)
    except Exception:
        return False


def make_round_avatar(img: Image.Image, size=48):
    big = size * 2
    img = img.resize((big, big), Image.LANCZOS).convert("RGBA")
    mask = Image.new("L", (big, big), 0)
    ImageDraw.Draw(mask).ellipse((1, 1, big - 2, big - 2), fill=255)
    output = Image.new("RGBA", (big, big), (0, 0, 0, 0))
    output.paste(img, (0, 0))
    output.putalpha(mask)
    return output.resize((size, size), Image.LANCZOS)


def get_gravatar(email: str, size=48):
    try:
        h = hashlib.md5(email.strip().lower().encode()).hexdigest()
        r = requests.get(f"https://www.gravatar.com/avatar/{h}?s={size*2}&d=identicon", headers=UA, timeout=8)
        r.raise_for_status()
        from io import BytesIO
        return make_round_avatar(Image.open(BytesIO(r.content)).convert("RGB"), size)
    except Exception:
        img = Image.new("RGB", (size * 2, size * 2), hex2rgb(T.get("accent", "#3ba55d")))
        return make_round_avatar(img, size)


def create_liquid_glass_bg(width=W, height=H):
    img = Image.new("RGB", (width, height))
    draw = ImageDraw.Draw(img)
    for y in range(height):
        t = y / height
        r = int(14 + 32 * t)
        g = int(10 + 22 * t)
        b = int(38 + 58 * t)
        draw.line([(0, y), (width, y)], fill=(r, g, b))
    glow = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    gdraw = ImageDraw.Draw(glow)
    gdraw.ellipse((-220, -220, 520, 520), fill=(255, 50, 190, 145))
    gdraw.ellipse((width - 540, height - 540, width + 200, height + 200), fill=(30, 210, 255, 130))
    gdraw.ellipse((width // 2 - 150, -150, width // 2 + 350, 350), fill=(130, 50, 255, 80))
    glow = glow.filter(ImageFilter.GaussianBlur(100))
    return Image.alpha_composite(img.convert("RGBA"), glow).convert("RGB")


# ====================================================================
#  Конфиг / Тема / Шрифты
# ====================================================================
def ensure_profiles(cfg, legacy=None):
    legacy = legacy or {}
    if not cfg["profiles"]:
        cfg["profiles"]["Основной"] = {"mc": legacy.get("version", "1.21.4"), "fabric": bool(legacy.get("fabric")),
                                       "launch_id": None, "dir": str(INSTANCES / "main")}
    if cfg["profile"] not in cfg["profiles"]:
        cfg["profile"] = next(iter(cfg["profiles"]))


def load_config():
    try:
        data = json.loads(CONFIG.read_text(encoding="utf-8"))
    except Exception:
        data = {}
    cfg = {**DEFAULTS, **data}
    cfg["profiles"] = dict(cfg.get("profiles") or {})
    ensure_profiles(cfg, data)
    return cfg


def save_config(cfg):
    """Пишет config.json. Токен шифруется, наружу — только шифротекст."""
    ROOT.mkdir(parents=True, exist_ok=True)
    safe = dict(cfg)
    tok = safe.get("ely_access_token") or ""
    # если токен уже зашифрован (начинается с gAAAAA...) — не трогаем
    if tok and not tok.startswith("gAAAAA"):
        safe["ely_access_token"] = enc_str(tok)
    try:
        CONFIG.write_text(json.dumps(safe, ensure_ascii=False, indent=1), encoding="utf-8")
    except Exception:
        pass


def set_theme(cfg):
    T.update(THEMES.get(cfg["theme"], THEMES["Nexora"]))
    if cfg["accent"]:
        T["accent"] = cfg["accent"]
    T["accent_h"] = lerp(T["accent"], "#ffffff", 0.18) if cfg.get("theme") == "Nexora" else lerp(T["accent"], "#000000", 0.2)
    T["field_h"] = lerp(T["field"], T["text"], 0.14)
    T["sidebar"] = "#0d1017" if cfg.get("theme") == "Nexora" else T["card"]
    T["dim"] = "#4f5869"
    T["border"] = GLASS_BORDER
    T["danger"], T["danger_h"], T["on_accent"] = "#c0392b", "#a5281c", "#ffffff"
    T["radius"] = cfg["radius"]
    ANIM["on"] = bool(cfg["anim"])
    ANIM["speed"] = max(0.3, cfg["anim_speed"] / 100)

    if cfg.get("liquid_glass"):
        T["bg"]      = "#0c0a16"
        T["card"]    = "#18142c"
        T["field"]   = "#241e3d"
        T["field_h"] = "#2e274d"
        T["text"]    = "#f2f0fa"
        T["muted"]   = "#9b95b5"
        T["radius"]  = max(T["radius"], 18)


def font_family(path):
    try:
        data = Path(path).read_bytes()
        base = struct.unpack(">I", data[12:16])[0] if data[:4] == b"ttcf" else 0
        num = struct.unpack(">H", data[base + 4:base + 6])[0]
        for i in range(num):
            rec = base + 12 + i * 16
            if data[rec:rec + 4] != b"name":
                continue
            off = struct.unpack(">I", data[rec + 8:rec + 12])[0]
            _, count, str_off = struct.unpack(">HHH", data[off:off + 6])
            found = {}
            for j in range(count):
                r = off + 6 + j * 12
                pid, _, _, nid, ln, of = struct.unpack(">HHHHHH", data[r:r + 12])
                raw = data[off + str_off + of: off + str_off + of + ln]
                txt = raw.decode("utf-16-be", "ignore") if pid in (0, 3) else raw.decode("latin-1")
                if pid == 3 or nid not in found:
                    found[nid] = txt
            for nid in (1, 16, 4):
                if found.get(nid):
                    return found[nid]
    except Exception:
        pass
    return None


def apply_fonts(cfg):
    auto = next((f for f in FONT["loaded"] if "montserrat" in f.lower() or "ginto" in f.lower()), None)
    FONT["title"] = cfg["font_title"] or auto or "Segoe UI"
    FONT["body"] = cfg["font_body"] or auto or "Segoe UI"


def load_font_file(path):
    fam = font_family(path)
    if fam and ctk.FontManager.load_font(str(path)):
        if fam not in FONT["loaded"]:
            FONT["loaded"].append(fam)
        return fam
    return None


def init_fonts(cfg):
    if FONTS.exists():
        for f in sorted(FONTS.glob("*.ttf")) + sorted(FONTS.glob("*.otf")):
            load_font_file(f)
    apply_fonts(cfg)


def F(size=13, title=False):
    fam = FONT["title"] if title else FONT["body"]
    heavy = any(w in fam.lower() for w in ("black", "heavy", "bold"))
    return ctk.CTkFont(family=fam, size=size, weight="bold" if (title and not heavy) else "normal")


def R(k=1.0):
    return max(0, round(T["radius"] * k))


# ====================================================================
#  Обои / API
# ====================================================================
WALL_API = "https://api.github.com/repos/FigureOffic/oboi/contents/"
WALL_RAW = "https://raw.githubusercontent.com/FigureOffic/oboi/main/"
WALL_FALLBACK = ["BestMC.png", "PinkLife.png", "SakyraMC.png"]

ICON_API = "https://api.github.com/repos/FigureOffic/nexIcon/contents/"
ICON_RAW = "https://raw.githubusercontent.com/FigureOffic/nexIcon/main/"
ICONS_DIR = ROOT / "icons"


def list_wallpapers():
    try:
        r = requests.get(WALL_API, headers=UA, timeout=10)
        r.raise_for_status()
        names = [f["name"] for f in r.json() if f["type"] == "file" and f["name"].lower().endswith(IMG_EXT)]
        return names or list(WALL_FALLBACK)
    except Exception:
        return list(WALL_FALLBACK)


def fetch_wallpaper(name):
    WALLS.mkdir(parents=True, exist_ok=True)
    p = WALLS / name
    if not p.exists():
        download(WALL_RAW + quote(name), p)
    return p


def make_bg(path, w, h, dim, blur):
    img = Image.open(path).convert("RGB")
    r = max(w / img.width, h / img.height)
    img = img.resize((round(img.width * r), round(img.height * r)), Image.LANCZOS)
    left, top = (img.width - w) // 2, (img.height - h) // 2
    img = img.crop((left, top, left + w, top + h))
    if blur:
        img = img.filter(ImageFilter.GaussianBlur(blur))
    return ImageEnhance.Brightness(img).enhance(max(0.05, 1 - dim / 100))


def make_thumb(path):
    img = Image.open(path).convert("RGB")
    img.thumbnail((190, 107))
    return img


def list_icons():
    try:
        r = requests.get(ICON_API, headers=UA, timeout=10)
        r.raise_for_status()
        names = [f["name"] for f in r.json()
                 if f["type"] == "file" and f["name"].lower().endswith((".png", ".ico", ".jpg", ".jpeg", ".webp"))]
        return names
    except Exception:
        return []


def fetch_icon(name):
    ICONS_DIR.mkdir(parents=True, exist_ok=True)
    p = ICONS_DIR / name
    if not p.exists():
        download(ICON_RAW + quote(name), p)
    return p


def png_to_ico(src_path):
    src = Path(src_path)
    if not src.exists():
        return None
    if src.suffix.lower() == ".ico":
        return src
    ICONS_DIR.mkdir(parents=True, exist_ok=True)
    ico = ICONS_DIR / (src.stem + ".ico")
    try:
        if not ico.exists() or ico.stat().st_mtime < src.stat().st_mtime:
            img = Image.open(src).convert("RGBA")
            s = max(img.size)
            canvas = Image.new("RGBA", (s, s), (0, 0, 0, 0))
            canvas.paste(img, ((s - img.width) // 2, (s - img.height) // 2))
            canvas = canvas.resize((256, 256), Image.LANCZOS)
            canvas.save(ico, format="ICO", sizes=[(256, 256), (128, 128), (64, 64), (48, 48), (32, 32), (16, 16)])
        return ico
    except Exception:
        return None


def delete_desktop_shortcut():
    try:
        desktop = Path(os.path.expandvars(r"%USERPROFILE%\Desktop"))
        if not desktop.exists():
            desktop = Path.home() / "Desktop"
        lnk = desktop / "Nexora Launcher.lnk"
        lnk.unlink(missing_ok=True)
        return True
    except Exception:
        return False


def create_desktop_shortcut(icon_path=None):
    if os.name != "nt":
        return
    try:
        desktop = Path(os.path.expandvars(r"%USERPROFILE%\Desktop"))
        if not desktop.exists():
            desktop = Path.home() / "Desktop"
        script = Path(__file__).resolve()
        target = sys.executable
        args = f'"{script}"'
        lnk = desktop / "Nexora Launcher.lnk"

        def ps_esc(s):
            return str(s).replace("'", "''")

        icon_loc = ""
        if icon_path:
            ico = png_to_ico(icon_path)
            if ico and ico.exists():
                icon_loc = str(ico.resolve()) + ",0"

        ps = (
            "$s = New-Object -ComObject WScript.Shell; "
            f"$c = $s.CreateShortcut('{ps_esc(lnk)}'); "
            f"$c.TargetPath = '{ps_esc(target)}'; "
            f"$c.Arguments = '{ps_esc(args)}'; "
            f"$c.WorkingDirectory = '{ps_esc(script.parent)}'; "
            f"$c.Description = 'Nexora Launcher'; "
        )
        if icon_loc:
            ps += f"$c.IconLocation = '{ps_esc(icon_loc)}'; "
        ps += "$c.Save()"
        subprocess.run(
            ["powershell", "-NoProfile", "-Command", ps],
            check=False, capture_output=True, timeout=20
        )
    except Exception:
        pass


def ely_authenticate(username: str, password: str) -> dict:
    client_token = str(uuid.uuid4())
    r = requests.post(
        "https://authserver.ely.by/auth/authenticate",
        json={
            "username": username,
            "password": password,
            "clientToken": client_token,
            "requestUser": True,
        },
        headers={**UA, "Content-Type": "application/json"},
        timeout=20,
    )
    if r.status_code != 200:
        try:
            err = r.json().get("errorMessage") or r.json().get("error") or r.text
        except Exception:
            err = r.text
        raise RuntimeError(err or f"Ely.by HTTP {r.status_code}")
    data = r.json()
    selected = data.get("selectedProfile") or {}
    return {
        "accessToken": data.get("accessToken", ""),
        "clientToken": data.get("clientToken", client_token),
        "uuid": selected.get("id", ""),
        "name": selected.get("name") or username.split("@")[0],
    }


def ely_skin_url(nick: str) -> str:
    return f"https://skinsystem.ely.by/skins/{quote(nick)}.png"


def ely_cape_url(nick: str) -> str:
    return f"https://skinsystem.ely.by/capes/{quote(nick)}.png"


def ely_fetch_skin_image(nick: str):
    from io import BytesIO
    nick = (nick or "").strip()
    if not nick:
        raise ValueError("empty nick")
    try:
        r = requests.get(
            f"https://skinsystem.ely.by/textures/{quote(nick)}",
            headers=UA, timeout=12
        )
        if r.status_code == 200:
            data = r.json()
            skin = (data.get("SKIN") or data.get("skin") or {})
            url = skin.get("url") if isinstance(skin, dict) else None
            if url:
                r2 = requests.get(url, headers=UA, timeout=12)
                r2.raise_for_status()
                return Image.open(BytesIO(r2.content)).convert("RGBA")
    except Exception:
        pass
    r = requests.get(ely_skin_url(nick), headers=UA, timeout=12)
    r.raise_for_status()
    return Image.open(BytesIO(r.content)).convert("RGBA")


def local_skin_dirs(game_dir: Path):
    base = Path(game_dir) / "CustomSkinLoader" / "LocalSkin"
    skins = base / "skins"
    capes = base / "capes"
    elytras = base / "elytras"
    for d in (skins, capes, elytras):
        d.mkdir(parents=True, exist_ok=True)
    return skins, capes, elytras


def save_local_skin(game_dir: Path, nick: str, img: Image.Image):
    skins, _, _ = local_skin_dirs(game_dir)
    path = skins / f"{nick}.png"
    img.convert("RGBA").save(path, "PNG")
    return path


def save_local_cape(game_dir: Path, nick: str, img: Image.Image):
    _, capes, _ = local_skin_dirs(game_dir)
    path = capes / f"{nick}.png"
    img.convert("RGBA").save(path, "PNG")
    return path


def write_customskinloader_config(game_dir: Path):
    cfg_dir = Path(game_dir) / "CustomSkinLoader"
    cfg_dir.mkdir(parents=True, exist_ok=True)
    cfg_path = cfg_dir / "CustomSkinLoader.json"
    config = {
        "version": "14.25",
        "enable": True,
        "enableSkull": True,
        "enableDynamicSkull": True,
        "enableTransparentSkin": True,
        "forceLoadAllTextures": True,
        "enableCape": True,
        "threadPoolSize": 8,
        "enableLogStdOut": False,
        "loadlist": [
            {"name": "LocalSkin", "type": "Legacy", "checkPNG": False,
             "skin": "LocalSkin/skins/{USERNAME}.png", "model": "auto",
             "cape": "LocalSkin/capes/{USERNAME}.png",
             "elytra": "LocalSkin/elytras/{USERNAME}.png"},
            {"name": "ElyBy", "type": "ElyByAPI"},
            {"name": "Mojang", "type": "MojangAPI"},
        ],
    }
    cfg_path.write_text(json.dumps(config, ensure_ascii=False, indent=2), encoding="utf-8")
    return cfg_path


def ping_server(host: str, port: int = 25565, timeout: float = 2.0):
    import socket, time
    try:
        t0 = time.perf_counter()
        with socket.create_connection((host, int(port)), timeout=timeout):
            pass
        return int((time.perf_counter() - t0) * 1000)
    except Exception:
        return None


DEFAULT_SERVERS = [
    {"name": "Hypixel", "host": "mc.hypixel.net", "port": 25565},
    {"name": "Mineblaze", "host": "mineblaze.net", "port": 25565},
    {"name": "HolyWorld", "host": "play.holyworld.ru", "port": 25565},
    {"name": "ReallyWorld", "host": "mc.reallyworld.ru", "port": 25565},
    {"name": "Saturn", "host": "mc.saturn.space", "port": 25565},
]

FEATURED_PACKS = [
    {"title": "Fabulously Optimized", "id": "1KVo5zza", "desc": "Лёгкая оптимизация Fabric"},
    {"title": "Simply Optimized", "id": "BYfJw3Om", "desc": "Минимальный набор FPS-модов"},
    {"title": "Prominence II RPG", "id": "Hk6VQv3g", "desc": "RPG-сборка (тяжёлая)"},
]


def check_launcher_update(url: str):
    """Возвращает {tag, url, sha256} или None. Не скачивает, только метаданные."""
    if not _check_host(url, ALLOWED_UPDATE_HOSTS):
        return None
    try:
        r = requests.get(url, headers=UA, timeout=10)
        if r.status_code != 200:
            return None
        data = r.json()
        tag = data.get("tag_name") or data.get("name")
        html_url = data.get("html_url")
        body = data.get("body") or ""
        m = re.search(r"SHA256:\s*([0-9a-f]{64})", body, re.I)
        sha256 = m.group(1).lower() if m else None
        return {"tag": tag, "url": html_url, "sha256": sha256}
    except Exception:
        return None


CAPE_SKIN_MOD_SLUG = "customskinloader"


def m_get(path, **params):
    r = requests.get("https://api.modrinth.com/v2" + path, headers=UA, timeout=20, params=params)
    r.raise_for_status()
    return r.json()


def modrinth_search(query, ptype, mc):
    facets = [[f"project_type:{ptype}"]]
    if ptype == "mod":
        facets += [["categories:fabric"], [f"versions:{mc}"]]
    elif ptype in ("resourcepack", "shader"):
        facets.append([f"versions:{mc}"])
    else:
        facets.append(["categories:fabric"])
    data = m_get("/search", query=query, facets=json.dumps(facets), limit=20,
                 index="relevance" if query else "downloads")
    return [{"id": h["project_id"], "title": h["title"], "author": h["author"], "desc": h.get("description") or "",
             "downloads": h["downloads"], "icon": h.get("icon_url") or "", "src": "modrinth"} for h in data["hits"]]


def modrinth_pick(pid, ptype, mc):
    params = {"loaders": json.dumps(["fabric"])} if ptype in ("mod", "modpack") else {}
    versions = m_get(f"/project/{pid}/version", game_versions=json.dumps([mc]), **params) if ptype != "modpack" else []
    if not versions and ptype != "mod":
        versions = m_get(f"/project/{pid}/version", **params)
    if not versions:
        raise RuntimeError(f"Нет версии под {mc}")
    v = next((x for x in versions if x["version_type"] == "release"), versions[0])
    f = next((x for x in v["files"] if x.get("primary")), v["files"][0])
    return v, f


def modrinth_install(pid, ptype, mc, dest, seen=None):
    seen = seen if seen is not None else set()
    if pid in seen:
        return
    seen.add(pid)
    v, f = modrinth_pick(pid, ptype, mc)
    hashes = f.get("hashes") or {}
    download(
        f["url"], Path(dest) / f["filename"],
        expected_sha512=hashes.get("sha512"),
        expected_sha1=hashes.get("sha1"),
    )
    if ptype == "mod":
        for d in v.get("dependencies", []):
            if d["dependency_type"] == "required" and d.get("project_id"):
                try:
                    modrinth_install(d["project_id"], "mod", mc, dest, seen)
                except Exception:
                    pass


CF = "https://api.curseforge.com/v1"
CF_CLASS = {"mod": 6, "resourcepack": 12, "shader": 6552}


def cf_headers(key):
    return {"x-api-key": key, "Accept": "application/json", **UA}


def cf_search(query, ptype, mc, key):
    params = {"gameId": 432, "classId": CF_CLASS[ptype], "gameVersion": mc, "searchFilter": query,
              "sortField": 2, "sortOrder": "desc", "pageSize": 20}
    if ptype == "mod":
        params["modLoaderType"] = 4
    r = requests.get(f"{CF}/mods/search", headers=cf_headers(key), timeout=15, params=params)
    r.raise_for_status()
    out = []
    for m in r.json()["data"]:
        logo = ""
        try:
            logo = (m.get("logo") or {}).get("thumbnailUrl") or (m.get("logo") or {}).get("url") or ""
        except Exception:
            pass
        out.append({
            "id": m["id"], "title": m["name"], "desc": m.get("summary") or "",
            "downloads": m["downloadCount"],
            "author": (m.get("authors") or [{"name": "?"}])[0]["name"],
            "icon": logo, "src": "curseforge",
        })
    return out


def cf_install(mod_id, ptype, mc, dest, key, seen=None):
    seen = seen if seen is not None else set()
    if mod_id in seen:
        return
    seen.add(mod_id)
    params = {"gameVersion": mc, "pageSize": 20}
    if ptype == "mod":
        params["modLoaderType"] = 4
    r = requests.get(f"{CF}/mods/{mod_id}/files", headers=cf_headers(key), timeout=15, params=params)
    r.raise_for_status()
    files = r.json()["data"]
    if not files:
        raise RuntimeError(f"Нет файла под {mc}")
    files.sort(key=lambda x: x["fileDate"], reverse=True)
    f = next((x for x in files if x.get("releaseType") == 1), files[0])
    if not f.get("downloadUrl"):
        raise RuntimeError("Автор запретил скачивание.")
    sha1 = None
    for h in (f.get("hashes") or []):
        if h.get("algo") == 1:
            sha1 = h.get("value")
            break
    download(f["downloadUrl"], Path(dest) / f["fileName"], expected_sha1=sha1)
    if ptype == "mod":
        for d in f.get("dependencies", []):
            if d["relationType"] == 3:
                try:
                    cf_install(d["modId"], "mod", mc, dest, key, seen)
                except Exception:
                    pass


# ====================================================================
#  Виджеты
# ====================================================================
class FancyButton(ctk.CTkButton):
    def __init__(self, master, color, hover, **kw):
        super().__init__(master, fg_color=color, hover=False, **kw)
        self._c, self._h, self._cur = color, hover, color
        self.bind("<Enter>", lambda e: self._fade(self._h), add="+")
        self.bind("<Leave>", lambda e: self._fade(self._c), add="+")

    def _fade(self, target):
        start = self._cur
        if not _norm_color(start) or not _norm_color(target):
            self._cur = target
            try:
                self.configure(fg_color=target)
            except tk.TclError:
                pass
            return

        def step(t):
            self._cur = lerp(start, target, t)
            try:
                self.configure(fg_color=self._cur)
            except tk.TclError:
                pass

        tween(self, 180, step, key="hover")

    def set_color(self, c):
        self._c = c
        self._fade(c)


def lbl(parent, text="", size=13, muted=False, title=False, color=None, anchor="w", **kw):
    return ctk.CTkLabel(parent, text=text, font=F(size, title), anchor=anchor,
                        text_color=color or (T["muted"] if muted else T["text"]), **kw)


def entry(parent, **kw):
    return ctk.CTkEntry(parent, height=38, corner_radius=R(0.9), fg_color=T["field"],
                        border_width=1, border_color=GLASS_BORDER,
                        text_color=T["text"], font=F(), **kw)


def menu(parent, values, **kw):
    return ctk.CTkOptionMenu(parent, values=values, height=38, corner_radius=R(0.9), fg_color=T["field"],
                             button_color=T["field"], button_hover_color=T["field_h"],
                             dropdown_fg_color=T["card"], dropdown_hover_color=T["field"],
                             dropdown_text_color=T["text"], text_color=T["text"], font=F(), dropdown_font=F(), **kw)


def btn(parent, text, command=None, kind="accent", **kw):
    c, h = {"accent": (T["accent"], T["accent_h"]), "field": (T["field"], T["field_h"]),
            "danger": (T["danger"], T["danger_h"])}[kind]
    kw.setdefault("height", 38)
    kw.setdefault("font", F(13))
    kw.setdefault("corner_radius", R(0.9))
    return FancyButton(parent, c, h, text=text, command=command,
                       text_color=T["text"] if kind == "field" else T["on_accent"], **kw)


def seg(parent, values, command=None):
    return ctk.CTkSegmentedButton(parent, values=values, command=command, fg_color=T["field"],
                                  selected_color=T["accent"], selected_hover_color=T["accent_h"],
                                  unselected_color=T["field"], unselected_hover_color=T["field_h"],
                                  text_color=T["text"], font=F(12))


GLASS_BORDER = "#222936"

# ====================================================================
#  Первый запуск
# ====================================================================
class WelcomeSetup(ctk.CTk):
    def __init__(self, cfg):
        super().__init__()
        self.cfg = cfg
        self.title("Nexora Launcher — Настройка")
        self.geometry("520x640")
        self.resizable(False, False)
        self.configure(fg_color=T["bg"])
        self.selected_icon = cfg.get("launcher_icon") or ""
        self.icon_thumbs = {}
        self._finished = False

        root = ctk.CTkScrollableFrame(self, fg_color="transparent")
        root.pack(fill="both", expand=True, padx=28, pady=(20, 8))

        lbl(root, "Добро пожаловать в Nexora", 22, title=True).pack(anchor="w", pady=(0, 4))
        lbl(root, "Пара минут — и можно играть", 13, muted=True).pack(anchor="w", pady=(0, 18))

        lbl(root, "Язык", 12, muted=True).pack(anchor="w")
        self.lang = seg(root, ["Русский", "English"])
        self.lang.set("Русский" if cfg.get("language", "ru") == "ru" else "English")
        self.lang.pack(fill="x", pady=(4, 14))

        lbl(root, "Как тебя зовут?", 12, muted=True).pack(anchor="w")
        self.name_e = entry(root, placeholder_text="Имя (просто так)")
        if cfg.get("display_name"):
            self.name_e.insert(0, cfg["display_name"])
        self.name_e.pack(fill="x", pady=(4, 14))

        lbl(root, "Откуда узнали об этом лаунчере?", 12, muted=True).pack(anchor="w")
        self.source = seg(root, ["TikTok", "YouTube", "друн посоветовал"])
        heard = cfg.get("heard_from") or "TikTok"
        if heard in ("TikTok", "YouTube", "друн посоветовал"):
            self.source.set(heard)
        else:
            self.source.set("TikTok")
        self.source.pack(fill="x", pady=(4, 14))

        self.shortcut_sw = ctk.CTkSwitch(
            root, text="Создать ярлык на рабочем столе",
            font=F(), text_color=T["text"], progress_color=T["accent"]
        )
        self.shortcut_sw.select()
        self.shortcut_sw.pack(anchor="w", pady=(0, 14))

        lbl(root, "Иконка лаунчера", 12, muted=True).pack(anchor="w")
        self.icons_frame = ctk.CTkFrame(root, fg_color=T["card"], corner_radius=R(0.8))
        self.icons_frame.pack(fill="x", pady=(4, 8))
        self.icons_status = lbl(self.icons_frame, "Загрузка иконок...", 12, muted=True)
        self.icons_status.pack(pady=16)
        threading.Thread(target=self._load_icons, daemon=True).start()

        btn(self, "Ну что, начинаем", self.finish, height=48, font=F(15, True)).pack(
            fill="x", padx=28, pady=(8, 22)
        )
        self.protocol("WM_DELETE_WINDOW", self._on_close)

    def _load_icons(self):
        names = list_icons()
        items = []
        for n in names[:24]:
            try:
                path = fetch_icon(n)
                img = Image.open(path).convert("RGBA")
                img.thumbnail((56, 56), Image.LANCZOS)
                items.append((n, path, img))
            except Exception:
                pass
        self.after(0, lambda: self._show_icons(items))

    def _show_icons(self, items):
        try:
            for w in self.icons_frame.winfo_children():
                w.destroy()
        except Exception:
            return
        if not items:
            lbl(self.icons_frame, "Иконки недоступны (проверьте интернет)", 12, muted=True).pack(pady=16)
            return
        grid = ctk.CTkFrame(self.icons_frame, fg_color="transparent")
        grid.pack(fill="x", padx=10, pady=10)
        for i, (name, path, img) in enumerate(items):
            ci = ctk.CTkImage(light_image=img, dark_image=img, size=img.size)
            self.icon_thumbs[name] = ci
            sel = str(path) == self.selected_icon
            card = ctk.CTkFrame(
                grid, width=64, height=64, corner_radius=10,
                fg_color=T["field"],
                border_width=2 if sel else 1,
                border_color=T["accent"] if sel else GLASS_BORDER
            )
            card.grid(row=i // 6, column=i % 6, padx=4, pady=4)
            card.grid_propagate(False)
            lab = ctk.CTkLabel(card, text="", image=ci)
            lab.place(relx=0.5, rely=0.5, anchor="center")
            for w in (card, lab):
                w.bind("<Button-1>", lambda e, p=str(path), c=card: self._pick_icon(p, c))

    def _pick_icon(self, path, card):
        self.selected_icon = path
        for child in self.icons_frame.winfo_children():
            if isinstance(child, ctk.CTkFrame):
                for sub in child.winfo_children():
                    if isinstance(sub, ctk.CTkFrame):
                        sub.configure(border_width=1, border_color=GLASS_BORDER)
        try:
            card.configure(border_width=2, border_color=T["accent"])
        except Exception:
            pass

    def finish(self):
        lang = "ru" if self.lang.get() == "Русский" else "en"
        name = self.name_e.get().strip()
        heard = self.source.get()
        self.cfg["language"] = lang
        self.cfg["display_name"] = name
        self.cfg["heard_from"] = heard
        self.cfg["launcher_icon"] = self.selected_icon
        if name:
            self.cfg["nick"] = name
        self.cfg["setup_done"] = True
        save_config(self.cfg)
        if self.shortcut_sw.get():
            create_desktop_shortcut(self.selected_icon or None)
        self._finished = True
        self.destroy()

    def _on_close(self):
        self._finished = False
        self.destroy()


# ====================================================================
#  Приложение
# ====================================================================
class App(ctk.CTk):
    def __init__(self, cfg):
        super().__init__()
        self.cfg = cfg
        self.title("Nexora Launcher")
        self.geometry(f"{W}x{H}")
        self.resizable(False, False)
        self.overrideredirect(True)
        self.attributes("-alpha", 0.0)

        self._drag_x = self._drag_y = 0
        self._window_region = None

        self.target = self.shown = 0.0
        self.base, self.last_text, self.busy, self.n = "Готов к запуску", "", False, 0
        self.current, self.search_id, self.nav_token = "play", 0, 0
        self.catalog_loaded, self.cat_type, self.lib_type = False, "mod", "mod"
        self.all_versions, self.gal_items, self.gal_loading = [], [], False
        self.pages, self.nav = {}, {}
        self.avatar_img = None

        self.bind("<Map>", self._on_map)
        threading.Thread(target=self.fetch_versions, daemon=True).start()
        self.build_ui()
        self.protocol("WM_DELETE_WINDOW", self.on_close)
        op = max(0.6, min(1.0, (self.cfg.get("window_opacity") or 100) / 100))
        self.after(50, lambda: tween(self, 420, lambda t: self.attributes("-alpha", op * t), key="window_fade"))
        self.after(120, self._apply_rounded_corners)
        if self.cfg.get("always_on_top"):
            self.after(200, lambda: self.attributes("-topmost", True))
        sp = self.cfg.get("start_page") or "play"
        if sp in dict(NAV) and sp != "play":
            self.after(300, lambda: self.show(sp))
        self.loop()

    def _apply_rounded_corners(self, radius=None):
        try:
            if os.name != "nt":
                return
            radius = max(0, int(T.get("radius", 14) if radius is None else radius))
            hwnd = ctypes.windll.user32.GetParent(self.winfo_id()) or self.winfo_id()
            rect = ctypes.wintypes.RECT()
            ctypes.windll.user32.GetClientRect(hwnd, ctypes.byref(rect))
            width = max(1, rect.right - rect.left)
            height = max(1, rect.bottom - rect.top)
            region = ctypes.windll.gdi32.CreateRoundRectRgn(
                0, 0, width + 1, height + 1, radius * 2, radius * 2
            )
            if not region:
                return
            old = ctypes.windll.user32.SetWindowRgn(hwnd, region, True)
            if old:
                ctypes.windll.gdi32.DeleteObject(old)
        except Exception:
            pass

    def minimize_window(self):
        self.overrideredirect(False)
        self.iconify()

    def _on_map(self, event=None):
        if self.state() == "normal":
            self.overrideredirect(True)
            self.after(30, self._apply_rounded_corners)

    def _start_drag(self, e):
        self._drag_x = e.x_root - self.winfo_x()
        self._drag_y = e.y_root - self.winfo_y()

    def _do_drag(self, e):
        self.geometry(f"+{e.x_root - self._drag_x}+{e.y_root - self._drag_y}")

    def cur(self):
        return self.cfg["profiles"][self.cfg["profile"]]

    def put(self, key, val):
        self.cfg[key] = val
        self.save_cfg()

    def save_cfg(self):
        save_config(self.cfg)

    def fetch_versions(self):
        try:
            self.all_versions = mll.utils.get_version_list()
        except Exception:
            self.all_versions = []

    def version_ids(self):
        snap = self.cfg["show_snapshots"]
        return [v["id"] for v in self.all_versions if v["type"] == "release" or (snap and v["type"] == "snapshot")][:80]

    def err(self, e):
        self.after(0, lambda m=str(e): messagebox.showerror("Ошибка", m))

    def open_dir(self, p):
        Path(p).mkdir(parents=True, exist_ok=True)
        if hasattr(os, "startfile"):
            os.startfile(p)

    def run_bg(self, fn, label, ok="Готово", done=None):
        def work():
            self.busy, self.base = True, label
            success = False
            try:
                fn()
                self.base, success = ok, True
            except Exception as e:
                self.base = "Ошибка"
                self.err(e)
            finally:
                self.busy, self.target = False, 1
                self.after(1200, lambda: setattr(self, "target", 0))
                if done:
                    self.after(0, lambda s=success: done(s))
        threading.Thread(target=work, daemon=True).start()

    def loop(self):
        try:
            self.shown += (self.target - self.shown) * 0.15
            self.bar.set(self.shown)
            self.n += 1
            text = self.base + ("." * ((self.n // 24) % 4) if self.busy else "")
            if text != self.last_text:
                self.status.configure(text=text)
                self.last_text = text
        except Exception:
            pass
        self.after(16, self.loop)

    def callback(self):
        mx = {"v": 1}
        return {"setStatus": lambda t: setattr(self, "base", t),
                "setMax": lambda v: mx.update(v=v or 1),
                "setProgress": lambda v: setattr(self, "target", min(v / mx["v"], 1))}

    def rebuild(self, page):
        self.current = page
        self.catalog_loaded = False
        self.build_ui()
        self.after(50, self._apply_rounded_corners)

    def build_ui(self):
        for w in self.winfo_children():
            if not isinstance(w, tk.Toplevel):
                w.destroy()
        ctk.set_appearance_mode(T["mode"])
        self.configure(fg_color=T["bg"])
        self.last_text = ""

        self.build_titlebar()
        self._bg_canvas = None
        self._glow_phase = 0

        if self.cfg.get("liquid_glass"):
            try:
                img = create_liquid_glass_bg()
                bg = ctk.CTkImage(light_image=img, dark_image=img, size=(W, H))
                ctk.CTkLabel(self, text="", image=bg).place(x=0, y=TITLE_H, relwidth=1, relheight=1)
            except Exception:
                pass
        else:
            wf = self.cfg.get("wall_file")
            if self.cfg.get("wall_on") and wf and Path(wf).exists():
                try:
                    s = self.cfg["scale"] / 100
                    img = make_bg(wf, int(W * s), int((H - TITLE_H) * s), self.cfg["wall_dim"], self.cfg["wall_blur"])
                    bg = ctk.CTkImage(light_image=img, dark_image=img, size=(W, H - TITLE_H))
                    ctk.CTkLabel(self, text="", image=bg).place(x=0, y=TITLE_H, relwidth=1, relheight=1)
                except Exception:
                    pass

        if self.cfg.get("theme") == "Nexora" and not self.cfg.get("liquid_glass") and not (
            self.cfg.get("wall_on") and self.cfg.get("wall_file") and Path(self.cfg.get("wall_file") or "").exists()
        ):
            try:
                self._bg_canvas = tk.Canvas(self, bg=T["bg"], highlightthickness=0, bd=0)
                self._bg_canvas.place(x=0, y=TITLE_H, relwidth=1, relheight=1)
                self._create_bg_glow()
                self.after(30, self._animate_bg_glow)
            except Exception:
                self._bg_canvas = None

        self.build_sidebar()
        self.pages = {k: ctk.CTkFrame(self, width=PLAY_W if k == "play" else 200, corner_radius=0,
                                      fg_color="transparent") for k, _ in NAV}
        self.pages["play"].grid_propagate(False)

        self.build_play(self.pages["play"])
        self.build_game(self.pages["game"])
        self.build_catalog(self.pages["catalog"])
        self.build_library(self.pages["library"])
        self.build_servers(self.pages["servers"])
        self.build_skins(self.pages["skins"])
        self.build_style(self.pages["style"])
        self.build_settings(self.pages["settings"])

        self.place_page(self.current)
        self.build_user_panel()
        self.side.lift()
        self.titlebar.lift()
        self.on_page_shown(self.current)
        self.after(800, self.check_for_updates)

    def _create_bg_glow(self):
        if not self._bg_canvas:
            return
        c = self._bg_canvas
        c.delete("all")
        w = max(self.winfo_width(), W)
        h = max(self.winfo_height() - TITLE_H, H - TITLE_H)
        self._glow1 = c.create_oval(-220, 40, 230, 460, fill="#17143b", outline="")
        self._glow2 = c.create_oval(w - 330, 120, w + 160, 620, fill="#111c3b", outline="")
        self._glow3 = c.create_oval(w // 2 - 100, -120, w // 2 + 330, 220, fill="#17162f", outline="")

    def _animate_bg_glow(self):
        if not self.winfo_exists() or not self._bg_canvas:
            return
        try:
            import math
            self._glow_phase = getattr(self, "_glow_phase", 0) + 0.012
            w = max(self.winfo_width(), W)
            m1 = math.sin(self._glow_phase) * 90
            m2 = math.cos(self._glow_phase * 0.7) * 100
            m3 = math.sin(self._glow_phase * 0.5) * 120
            self._bg_canvas.coords(self._glow1, -220 + m1, 40, 230 + m1, 460)
            self._bg_canvas.coords(self._glow2, w - 330 + m2, 120, w + 160 + m2, 620)
            self._bg_canvas.coords(self._glow3, w // 2 - 100 + m3, -120, w // 2 + 330 + m3, 220)
            self.after(16, self._animate_bg_glow)
        except Exception:
            pass

    def build_titlebar(self):
        bar = ctk.CTkFrame(self, height=TITLE_H, corner_radius=0, fg_color=T["card"])
        bar.place(x=0, y=0, relwidth=1)
        bar.pack_propagate(False)
        self.titlebar = bar

        title = lbl(bar, "Nexora Launcher", 13, title=True)
        title.pack(side="left", padx=14)

        close_btn = ctk.CTkButton(bar, text="✕", width=42, height=TITLE_H, corner_radius=R(0.75),
                                  fg_color="transparent", hover_color="#c0392b",
                                  text_color=T["text"], font=F(14), command=self.on_close)
        close_btn.pack(side="right")

        min_btn = ctk.CTkButton(bar, text="—", width=42, height=TITLE_H, corner_radius=R(0.75),
                                fg_color="transparent", hover_color=T["field"],
                                text_color=T["text"], font=F(16), command=self.minimize_window)
        min_btn.pack(side="right")

        for w in (bar, title):
            w.bind("<Button-1>", self._start_drag)
            w.bind("<B1-Motion>", self._do_drag)

    def build_sidebar(self):
        side_bg = T.get("sidebar", T["card"])
        side = ctk.CTkFrame(self, width=210,
                            corner_radius=R(1.0),
                            fg_color=side_bg,
                            border_width=1,
                            border_color=T.get("border", GLASS_BORDER))
        side.pack_propagate(False)
        side.place(x=12, rely=PAD_Y, relheight=PAD_H)
        self.side = side

        logo = ctk.CTkFrame(side, height=82, fg_color="transparent")
        logo.pack(fill="x", padx=14, pady=(16, 10))
        logo.pack_propagate(False)
        ctk.CTkLabel(
            logo, text="N", width=44, height=44, corner_radius=12,
            fg_color=T["accent"], text_color="#ffffff",
            font=F(22, title=True)
        ).place(x=0, y=12)
        ctk.CTkLabel(
            logo, text="NEXORA", text_color=T["text"],
            font=F(20, title=True)
        ).place(x=54, y=10)
        ctk.CTkLabel(
            logo, text="Launcher", text_color=T.get("dim", T["muted"]),
            font=F(12)
        ).place(x=54, y=40)

        self.nav = {}
        for key, label in NAV:
            active = key == self.current
            side_bg = T.get("sidebar", T["card"])
            fg = "#202442" if active and self.cfg.get("theme") == "Nexora" else (T["field"] if active else side_bg)
            txt = T["text"] if active else T["muted"]
            b = FancyButton(
                side, fg, T["field_h"],
                text=f"  {label}",
                height=44, anchor="w", corner_radius=10, font=F(15),
                text_color=txt, command=lambda k=key: self.show(k)
            )
            b.pack(fill="x", padx=12, pady=3)
            self.nav[key] = b

        self.bar = ctk.CTkProgressBar(side, height=5, progress_color=T["accent"], fg_color=T["field"])
        self.bar.set(0)
        self.bar.pack(side="bottom", fill="x", padx=14, pady=(0, 14))
        self.status = lbl(side, self.base, 11, muted=True, wraplength=170, justify="left")
        self.status.pack(side="bottom", fill="x", padx=14, pady=(0, 6))

    def build_user_panel(self):
        self.user_frame = ctk.CTkFrame(self, fg_color=T["card"], corner_radius=R(1.0),
                                       border_width=1, border_color=GLASS_BORDER)
        self.user_frame.place(relx=1.0, rely=1.0, x=-18, y=-18, anchor="se")

        if self.cfg.get("auth_logged") and self.cfg.get("auth_email"):
            def load_av():
                try:
                    av = get_gravatar(self.cfg["auth_email"], 42)
                    self.avatar_img = ctk.CTkImage(light_image=av, dark_image=av, size=(42, 42))
                    self.after(0, self._update_user_panel)
                except Exception:
                    self.after(0, self._update_user_panel)
            threading.Thread(target=load_av, daemon=True).start()
            self._update_user_panel()
        else:
            inner = ctk.CTkFrame(self.user_frame, fg_color="transparent")
            inner.pack(padx=12, pady=10)
            btn(inner, "Войти", self.show_login, width=90, height=32).pack(side="left", padx=(0, 6))
            btn(inner, "Регистрация", self.show_register, kind="field", width=110, height=32).pack(side="left")

    def _update_user_panel(self):
        try:
            for w in self.user_frame.winfo_children():
                w.destroy()
        except Exception:
            return
        if not (self.cfg.get("auth_logged") and self.cfg.get("auth_email")):
            inner = ctk.CTkFrame(self.user_frame, fg_color="transparent")
            inner.pack(padx=12, pady=10)
            btn(inner, "Войти", self.show_login, width=90, height=32).pack(side="left", padx=(0, 6))
            btn(inner, "Регистрация", self.show_register, kind="field", width=110, height=32).pack(side="left")
            return

        row = ctk.CTkFrame(self.user_frame, fg_color="transparent")
        row.pack(padx=12, pady=10)
        text_col = ctk.CTkFrame(row, fg_color="transparent")
        text_col.pack(side="left", padx=(0, 10))
        nick = self.cfg.get("auth_nick") or "Player"
        email = self.cfg.get("auth_email", "")
        lbl(text_col, nick, 14, title=True, anchor="e").pack(anchor="e")
        lbl(text_col, email, 11, muted=True, anchor="e").pack(anchor="e")
        if self.avatar_img:
            av = ctk.CTkLabel(row, text="", image=self.avatar_img, width=42, height=42)
            av.pack(side="right")
            av.bind("<Button-1>", lambda e: self.logout())
        for w in (row, text_col):
            w.bind("<Button-1>", lambda e: self.logout())

    def show_login(self):
        self._auth_window("Вход", True)

    def show_register(self):
        self._auth_window("Регистрация", False)

    def _auth_window(self, title, login=True):
        top = ctk.CTkToplevel(self)
        top.title(title)
        top.geometry("400x420" if not login else "400x380")
        top.resizable(False, False)
        top.configure(fg_color=T["card"])
        top.transient(self)
        top.grab_set()
        top.after(80, top.lift)
        top.grid_columnconfigure(0, weight=1)

        lbl(top, title, 22, title=True).grid(row=0, column=0, sticky="ew", padx=28, pady=(18, 8))
        lbl(top, "Способ входа", muted=True).grid(row=1, column=0, sticky="ew", padx=28)
        provider = seg(top, ["Локальный", "Ely.by"])
        provider.set("Ely.by" if self.cfg.get("auth_provider") == "ely" else "Локальный")
        provider.grid(row=2, column=0, sticky="ew", padx=28, pady=(4, 10))

        lbl(top, "Email / логин Ely.by", muted=True).grid(row=3, column=0, sticky="ew", padx=28)
        email_e = entry(top)
        email_e.grid(row=4, column=0, sticky="ew", padx=28, pady=(4, 8))
        lbl(top, "Пароль", muted=True).grid(row=5, column=0, sticky="ew", padx=28)
        pass_e = entry(top, show="•")
        pass_e.grid(row=6, column=0, sticky="ew", padx=28, pady=(4, 8))
        nick_e = None
        if not login:
            lbl(top, "Ник (только локальный)", muted=True).grid(row=7, column=0, sticky="ew", padx=28)
            nick_e = entry(top)
            nick_e.grid(row=8, column=0, sticky="ew", padx=28, pady=(4, 8))

        def do():
            email = email_e.get().strip()
            password = pass_e.get()
            use_ely = provider.get() == "Ely.by"
            if use_ely:
                if not email or len(password) < 3:
                    return messagebox.showerror("Ошибка", "Введите логин и пароль Ely.by", parent=top)
                try:
                    data = ely_authenticate(email, password)
                except Exception as e:
                    return messagebox.showerror("Ely.by", str(e), parent=top)
                nick = data["name"]
                self.cfg.update({
                    "auth_email": email, "auth_nick": nick, "auth_logged": True, "nick": nick,
                    "auth_provider": "ely", "ely_uuid": data["uuid"],
                    "ely_access_token": enc_str(data["accessToken"]),
                })
            else:
                email_l = email.lower()
                if not email_l or "@" not in email_l:
                    return messagebox.showerror("Ошибка", "Некорректный email", parent=top)
                if len(password) < 4:
                    return messagebox.showerror("Ошибка", "Пароль минимум 4 символа", parent=top)
                users = load_users()
                if login:
                    if email_l not in users or not verify_password(password, users[email_l]):
                        return messagebox.showerror("Ошибка", "Неверный email или пароль", parent=top)
                    nick = users[email_l].get("nick", email_l.split("@")[0])
                else:
                    if email_l in users:
                        return messagebox.showerror("Ошибка", "Email уже занят", parent=top)
                    nick = (nick_e.get().strip() if nick_e else "") or email_l.split("@")[0]
                    users[email_l] = {**hash_password(password), "nick": nick}
                    save_users(users)
                self.cfg.update({
                    "auth_email": email_l, "auth_nick": nick, "auth_logged": True, "nick": nick,
                    "auth_provider": "local", "ely_uuid": "", "ely_access_token": "",
                })
            self.save_cfg()
            try:
                self.nick.delete(0, "end")
                self.nick.insert(0, nick)
            except Exception:
                pass
            top.destroy()
            self.build_user_panel()
            messagebox.showinfo("Готово", f"Добро пожаловать, {nick}!")

        btn(top, "Войти" if login else "Зарегистрироваться", do, height=44).grid(
            row=9 if not login else 7, column=0, sticky="ew", padx=28, pady=(10, 18))

    def logout(self):
        if messagebox.askyesno("Выход", "Выйти из аккаунта?"):
            self.cfg.update({
                "auth_email": "", "auth_nick": "", "auth_logged": False,
                "auth_provider": "local", "ely_uuid": "", "ely_access_token": "",
            })
            self.avatar_img = None
            self.save_cfg()
            self.build_user_panel()

    def place_page(self, name, dx=0):
        pg = self.pages[name]
        if name == "play":
            pg.place(x=228 + dx, rely=PAD_Y, relheight=PAD_H)
        else:
            pg.place(x=228 + dx, rely=PAD_Y, relheight=PAD_H, relwidth=(W - 242) / W)

    def show(self, name):
        if name == self.current:
            return
        order = [k for k, _ in NAV]
        d = 1 if order.index(name) > order.index(self.current) else -1
        keep_old = name != "play" and self.current != "play"
        for k, pg in self.pages.items():
            if k not in (self.current, name):
                pg.place_forget()
        old, new = self.pages[self.current], self.pages[name]
        if not keep_old:
            old.place_forget()
        self.current = name
        for k, b in self.nav.items():
            if self.cfg.get("theme") == "Nexora":
                b.set_color("#202442" if k == name else T.get("sidebar", T["card"]))
                try:
                    b.configure(text_color=T["text"] if k == name else T["muted"])
                except Exception:
                    pass
            else:
                b.set_color(T["field"] if k == name else T["card"])
        self.on_page_shown(name)
        self.nav_token += 1
        tok = self.nav_token
        self.place_page(name, d * 100)
        new.lift()
        self.side.lift()
        self.titlebar.lift()
        if hasattr(self, "user_frame"):
            self.user_frame.lift()

        def step(t):
            if tok == self.nav_token:
                self.place_page(name, d * 100 * (1 - t))
                self.side.lift()
                self.titlebar.lift()
                if hasattr(self, "user_frame"):
                    self.user_frame.lift()

        def finish():
            if tok == self.nav_token and keep_old:
                old.place_forget()
        tween(self, 280, step, finish)

    def on_page_shown(self, name):
        self.update_info()
        if name == "catalog" and not self.catalog_loaded:
            self.catalog_loaded = True
            self.search()
        elif name == "library":
            self.refresh_library()
        elif name == "style":
            if self.gal_items:
                self.fill_gallery()
            elif not self.gal_loading:
                self.load_gallery()
        elif name == "game":
            self.update_watermark_preview()
        elif name == "servers":
            self.refresh_servers()
        elif name == "skins":
            self.refresh_skins()

    # ====================== ИГРАТЬ ======================
    def build_play(self, p):
        p.grid_columnconfigure(0, weight=1)
        p.grid_rowconfigure(7, weight=1)
        lbl(p, "Играть", 30, title=True).grid(row=0, column=0, sticky="ew", padx=28, pady=(26, 14))
        lbl(p, "Ник", muted=True).grid(row=1, column=0, sticky="ew", padx=28)
        self.nick = entry(p)
        self.nick.insert(0, self.cfg["nick"])
        self.nick.grid(row=2, column=0, sticky="ew", padx=28, pady=(4, 14))
        lbl(p, "Профиль / сборка", muted=True).grid(row=3, column=0, sticky="ew", padx=28)
        self.prof_menu = menu(p, list(self.cfg["profiles"]), command=self.on_profile)
        self.prof_menu.set(self.cfg["profile"])
        self.prof_menu.grid(row=4, column=0, sticky="ew", padx=28, pady=(4, 8))
        tools = ctk.CTkFrame(p, fg_color="transparent")
        tools.grid(row=5, column=0, sticky="ew", padx=24)
        tools.grid_columnconfigure((0, 1, 2, 3), weight=1)
        for i, (t, cmd, kind) in enumerate([("Новая", self.new_profile, "field"), ("Импорт", self.import_file, "field"),
                                            ("Папка", lambda: self.open_dir(self.cur()["dir"]), "field"),
                                            ("Удалить", self.delete_profile, "danger")]):
            btn(tools, t, cmd, kind, height=34).grid(row=0, column=i, sticky="ew", padx=4)
        self.info = lbl(p, "", 12, muted=True, wraplength=PLAY_W - 56, justify="left")
        self.info.grid(row=6, column=0, sticky="ew", padx=28, pady=(12, 0))
        self.play_btn = btn(p, "ИГРАТЬ", self.play, height=58, font=F(18, True))
        self.play_btn.grid(row=8, column=0, sticky="sew", padx=28, pady=(0, 26))

    def update_info(self):
        try:
            p = self.cur()
            mods = Path(p["dir"]) / "mods"
            n = len(list(mods.glob("*.jar"))) if mods.exists() else 0
            self.info.configure(text=f'{p["mc"]}  •  {loader_name(p)}  •  модов: {n}')
            self.cat_info.configure(text=f'Профиль: {self.cfg["profile"]}  •  {p["mc"]}  •  {loader_name(p)}')
        except Exception:
            pass

    def refresh_profiles(self):
        try:
            self.prof_menu.configure(values=list(self.cfg["profiles"]))
            self.prof_menu.set(self.cfg["profile"])
        except Exception:
            pass
        self.update_info()
        self.catalog_loaded = False
        if self.current == "library":
            self.refresh_library()

    def on_profile(self, name):
        self.put("profile", name)
        self.refresh_profiles()

    def unique_profile(self, name):
        base, i = name, 1
        while name in self.cfg["profiles"]:
            i += 1
            name = f"{base} ({i})"
        return name

    def new_profile(self):
        ids = self.version_ids()
        if not ids:
            return messagebox.showinfo("Версии", "Список версий ещё загружается")
        top = ctk.CTkToplevel(self)
        top.title("Новая сборка")
        top.geometry("380x320")
        top.resizable(False, False)
        top.configure(fg_color=T["card"])
        top.after(100, top.lift)
        top.grid_columnconfigure(0, weight=1)
        lbl(top, "Название", muted=True).grid(row=0, column=0, sticky="ew", padx=24, pady=(20, 0))
        name = entry(top)
        name.insert(0, "Моя сборка")
        name.grid(row=1, column=0, sticky="ew", padx=24, pady=(4, 10))
        lbl(top, "Версия Minecraft", muted=True).grid(row=2, column=0, sticky="ew", padx=24)
        ver = menu(top, ids)
        ver.set(self.cur()["mc"] if self.cur()["mc"] in ids else ids[0])
        ver.grid(row=3, column=0, sticky="ew", padx=24, pady=(4, 10))
        fab = ctk.CTkSwitch(top, text="Fabric", font=F(), text_color=T["text"], progress_color=T["accent"])
        fab.select()
        fab.grid(row=4, column=0, sticky="w", padx=24, pady=(0, 16))

        def create():
            nm = name.get().strip()
            if not nm or nm in self.cfg["profiles"]:
                return messagebox.showerror("Ошибка", "Уникальное название", parent=top)
            self.cfg["profiles"][nm] = {"mc": ver.get(), "fabric": bool(fab.get()), "launch_id": None,
                                        "dir": str(INSTANCES / unique_slug(nm))}
            self.cfg["profile"] = nm
            self.save_cfg()
            self.refresh_profiles()
            top.destroy()
        btn(top, "Создать", create, height=42).grid(row=5, column=0, sticky="ew", padx=24)

    def delete_profile(self):
        if len(self.cfg["profiles"]) <= 1:
            return messagebox.showinfo("Профиль", "Нельзя удалить последний")
        name = self.cfg["profile"]
        if messagebox.askyesno("Удалить", f"Удалить «{name}»?"):
            shutil.rmtree(self.cur()["dir"], ignore_errors=True)
            del self.cfg["profiles"][name]
            self.cfg["profile"] = next(iter(self.cfg["profiles"]))
            self.save_cfg()
            self.refresh_profiles()

    def import_file(self):
        path = filedialog.askopenfilename(filetypes=[("Modrinth", "*.mrpack")])
        if path:
            self.run_bg(lambda: self.import_pack_sync(path), "Установка сборки", "Готово")

    def install_pack_files(self, pack, inst, cb):
        mll.mrpack.install_mrpack(str(pack), MC_DIR, modpack_directory=str(inst), callback=cb)

    def import_pack_sync(self, path, title=None):
        with zipfile.ZipFile(path) as z:
            idx = json.loads(z.read("modrinth.index.json"))
        name = self.unique_profile(title or idx.get("name") or "Сборка")
        mc = idx.get("dependencies", {}).get("minecraft", "?")
        inst = INSTANCES / unique_slug(name)
        inst.mkdir(parents=True, exist_ok=True)
        pack = inst / "pack.mrpack"
        shutil.copy(path, pack)
        self.install_pack_files(pack, inst, self.callback())
        launch_id = mll.mrpack.get_mrpack_launch_version(str(pack))
        self.cfg["profiles"][name] = {"mc": mc, "fabric": False, "launch_id": launch_id, "dir": str(inst), "pack": str(pack)}
        self.cfg["profile"] = name
        self.save_cfg()
        self.after(0, self.refresh_profiles)

    def play(self):
        self.cfg["nick"] = self.nick.get().strip() or "Player"
        self.save_cfg()
        if self.cfg.get("confirm_launch"):
            if not messagebox.askyesno("Запуск", f"Запустить Minecraft как {self.cfg['nick']}?"):
                return
        self.play_btn.configure(state="disabled", text="ЗАГРУЗКА")
        self.busy = True
        threading.Thread(target=self.run, args=(dict(self.cfg), dict(self.cur())), daemon=True).start()

    def reset_play(self):
        try:
            self.play_btn.configure(state="normal", text="ИГРАТЬ")
        except Exception:
            pass

    def run(self, c, p):
        try:
            cb = self.callback()
            mc, inst = p["mc"], Path(p["dir"])
            inst.mkdir(parents=True, exist_ok=True)
            installed = {v["id"] for v in mll.utils.get_installed_versions(MC_DIR)}
            launch_id = p.get("launch_id")
            if launch_id:
                if launch_id not in installed:
                    self.base = "Установка сборки"
                    self.install_pack_files(Path(p["pack"]), inst, cb)
            else:
                if c["verify_files"] or mc not in installed:
                    mll.install.install_minecraft_version(mc, MC_DIR, callback=cb)
                launch_id = mc
                if p.get("fabric") or c.get("opt_auto"):
                    launch_id = find_fabric(mc)
                    if not launch_id:
                        mll.fabric.install_fabric(mc, MC_DIR, callback=cb)
                        launch_id = find_fabric(mc)
                    if not launch_id:
                        raise RuntimeError("Fabric не установлен")

            if c.get("opt_auto") and not c.get("safe_mode") and not p.get("launch_id"):
                self.base = "Оптимизация"
                mods = inst / "mods"
                mods.mkdir(exist_ok=True)
                seen = set()
                for s in PERF_MODS:
                    try:
                        modrinth_install(s, "mod", mc, mods, seen)
                    except Exception:
                        pass
                p["fabric"] = True
                self.save_cfg()

            if c.get("cape_mod_ok"):
                self.base = "Мод скинов/плащей"
                mods = inst / "mods"
                mods.mkdir(exist_ok=True)
                try:
                    modrinth_install(CAPE_SKIN_MOD_SLUG, "mod", mc, mods, set())
                except Exception:
                    pass
                try:
                    write_customskinloader_config(inst)
                except Exception:
                    pass

            name = c.get("auth_nick") or c["nick"]
            xmx = int(c.get("ram") or 4096)
            xms = int(c.get("ram_min") or min(512, xmx))
            if xms > xmx:
                xms = xmx
            jvm = [f"-Xmx{xmx}M", f"-Xms{xms}M"]
            gc = (c.get("gc") or "G1").upper()
            if c.get("aikar_flags") and gc == "G1":
                jvm += [
                    "-XX:+UseG1GC", "-XX:+ParallelRefProcEnabled", "-XX:MaxGCPauseMillis=200",
                    "-XX:+UnlockExperimentalVMOptions", "-XX:+DisableExplicitGC", "-XX:+AlwaysPreTouch",
                    "-XX:G1NewSizePercent=30", "-XX:G1MaxNewSizePercent=40", "-XX:G1HeapRegionSize=8M",
                    "-XX:G1ReservePercent=20", "-XX:G1HeapWastePercent=5", "-XX:G1MixedGCCountTarget=4",
                    "-XX:InitiatingHeapOccupancyPercent=15", "-XX:G1MixedGCLiveThresholdPercent=90",
                    "-XX:G1RSetUpdatingPauseTimePercent=5", "-XX:SurvivorRatio=32", "-XX:+PerfDisableSharedMem",
                    "-XX:MaxTenuringThreshold=1",
                ]
                if c.get("ultra_opt", True):
                    bad = {"-XX:+UseFastAccessorMethods", "-XX:+UseFastEmptyMethods",
                           "-XX:+AggressiveOpts", "-XX:+CMSClassUnloadingEnabled"}
                    for flag in ULTRA_JVM:
                        if flag in bad:
                            continue
                        if flag not in jvm:
                            jvm.append(flag)
            elif gc == "G1":
                jvm += ["-XX:+UseG1GC"]
            elif gc == "ZGC":
                jvm += ["-XX:+UseZGC"]
            elif gc == "PARALLEL":
                jvm += ["-XX:+UseParallelGC"]
            elif gc == "SHENANDOAH":
                jvm += ["-XX:+UseShenandoahGC"]
            if c.get("jvm_debug"):
                port = int(c.get("jvm_debug_port") or 5005)
                jvm.append(f"-agentlib:jdwp=transport=dt_socket,server=y,suspend=n,address=*:{port}")
            jvm += [x for x in (c.get("jvm_args") or "").split() if x]

            if c.get("auth_provider") == "ely" and c.get("ely_access_token") and c.get("ely_uuid"):
                token = dec_str(c["ely_access_token"])
                uid = c["ely_uuid"].replace("-", "")
                if len(uid) == 32:
                    uid = f"{uid[:8]}-{uid[8:12]}-{uid[12:16]}-{uid[16:20]}-{uid[20:]}"
                opts = {"username": name, "uuid": uid, "token": token,
                        "gameDirectory": str(Path(c["game_dir_override"]) if c.get("game_dir_override") else inst), "jvmArguments": jvm}
            else:
                gdir = str(Path(c["game_dir_override"]) if c.get("game_dir_override") else inst)
                opts = {"username": name, "uuid": str(uuid.uuid3(uuid.NAMESPACE_DNS, "OfflinePlayer:" + name)),
                        "token": "", "gameDirectory": gdir, "jvmArguments": jvm}
            if c["java_path"]:
                opts["executablePath"] = c["java_path"]
            aspect = c.get("aspect", "16:9")
            if aspect != "Авто" and not (c["res_w"] and c["res_h"]):
                ratios = {"16:9": (1920, 1080), "16:10": (1920, 1200), "4:3": (1600, 1200), "21:9": (2560, 1080), "1:1": (1080, 1080)}
                if aspect in ratios:
                    opts.update(customResolution=True, resolutionWidth=str(ratios[aspect][0]), resolutionHeight=str(ratios[aspect][1]))
            elif c["res_w"] and c["res_h"]:
                opts.update(customResolution=True, resolutionWidth=str(c["res_w"]), resolutionHeight=str(c["res_h"]))

            cmd = mll.command.get_minecraft_command(launch_id, MC_DIR, opts)
            if c["fullscreen"]:
                cmd.append("--fullscreen")
            if c.get("auto_join_server") and c.get("last_server") and c.get("remember_last_server", True):
                parts = str(c["last_server"]).split(":")
                cmd.extend(["--server", parts[0]])
                if len(parts) > 1:
                    cmd.extend(["--port", parts[1]])
            if c.get("demo_mode"):
                cmd.append("--demo")
            self.base = "Запуск..."
            subprocess.Popen(cmd, cwd=str(inst))
            self.base = "Игра запущена"
            if c.get("minimize_on_launch") and not c.get("close_on_launch"):
                self.after(800, self.minimize_window)
            if c.get("close_on_launch"):
                self.after(1500, self.on_close)
        except Exception as e:
            self.base = "Ошибка"
            self.err(e)
        finally:
            self.busy = False
            self.target = 1
            self.after(0, self.reset_play)
            self.after(1200, lambda: setattr(self, "target", 0))

    def build_game(self, p):
        p.grid_columnconfigure(0, weight=1)
        p.grid_rowconfigure(1, weight=1)
        lbl(p, "Игра", 28, title=True).grid(row=0, column=0, sticky="ew", padx=28, pady=(24, 6))
        is_glass = self.cfg.get("liquid_glass")
        sc = ctk.CTkScrollableFrame(p, fg_color=T["card"], corner_radius=R(0.8),
                                    border_width=1 if is_glass else 0, border_color=GLASS_BORDER)
        sc.grid(row=1, column=0, sticky="nsew", padx=(20, 16), pady=(0, 16))
        self.sec(sc, "Оптимизация")
        self.row_switch(sc, "Авто-установка оптимизационных модов", "opt_auto")
        self.row_switch(sc, "Ультра-оптимизация JVM + расширенный набор модов", "ultra_opt")
        btn(sc, "Установить оптимизацию сейчас", self.install_optimization, width=260).pack(anchor="w", padx=8, pady=8)
        self.sec(sc, "Графика")
        self.row_slider(sc, "Насыщенность", "saturation", 0, 200, 40, lambda v: f"{v}%")
        self.row_slider(sc, "Резкость", "sharpness", 0, 100, 20, lambda v: f"{v}%")
        self.row_switch(sc, "Motion Blur", "motion_blur")
        self.sec(sc, "Экран")
        f = ctk.CTkFrame(sc, fg_color="transparent")
        f.pack(fill="x", padx=8, pady=4)
        lbl(f, "Aspect Ratio").pack(side="left")
        m = menu(f, ["Авто", "16:9", "16:10", "4:3", "21:9", "1:1"], width=140, command=lambda v: self.put("aspect", v))
        m.set(self.cfg.get("aspect", "16:9"))
        m.pack(side="right")
        self.sec(sc, "Оверлей")
        self.row_switch(sc, "Показывать FPS", "show_fps")
        self.row_switch(sc, "Watermark", "watermark")
        self.wm_preview = lbl(sc, "", 13, color=T["accent"])
        self.wm_preview.pack(anchor="w", padx=8, pady=8)

    def update_watermark_preview(self):
        try:
            nick = self.cfg.get("auth_nick") or self.cfg.get("nick", "Player")
            fps = "120" if self.cfg.get("show_fps") else "—"
            text = f"Nexora | fps {fps} | {nick} | Server | ping" if self.cfg.get("watermark") else "(выкл)"
            self.wm_preview.configure(text=text)
        except Exception:
            pass

    def install_optimization(self):
        self.run_bg(lambda: self._do_opt(self.cur()["mc"], Path(self.cur()["dir"])), "Оптимизация", "Готово")

    def _do_opt(self, mc, inst):
        mods = inst / "mods"
        mods.mkdir(exist_ok=True)
        seen = set()
        for s in PERF_MODS:
            try:
                modrinth_install(s, "mod", mc, mods, seen)
            except Exception:
                pass
        if not self.cur().get("launch_id"):
            self.cur()["fabric"] = True
            self.save_cfg()

    def build_catalog(self, p):
        p.grid_columnconfigure(0, weight=1)
        p.grid_rowconfigure(4, weight=1)
        lbl(p, "Каталог", 28, title=True).grid(row=0, column=0, sticky="ew", padx=28, pady=(24, 0))
        self.cat_info = lbl(p, "", 12, muted=True)
        self.cat_info.grid(row=1, column=0, sticky="ew", padx=28, pady=(0, 8))
        top = ctk.CTkFrame(p, fg_color="transparent")
        top.grid(row=2, column=0, sticky="ew", padx=28, pady=(0, 8))
        self.type_seg = seg(top, list(TYPES), self.on_type)
        self.type_seg.set(TYPE_LABEL[self.cat_type])
        self.type_seg.grid(row=0, column=0, sticky="w")
        self.source_seg = seg(top, ["Modrinth", "CurseForge"], lambda v: self.search())
        self.source_seg.set("Modrinth")
        self.source_seg.grid(row=0, column=1)
        btn(top, "Сборки ⚡", self.show_featured_packs, kind="field", width=100).grid(row=0, column=2, padx=(8, 0))
        row = ctk.CTkFrame(p, fg_color="transparent")
        row.grid(row=3, column=0, sticky="ew", padx=28, pady=(0, 8))
        row.grid_columnconfigure(0, weight=1)
        self.query = entry(row, placeholder_text="Поиск...")
        self.query.grid(row=0, column=0, sticky="ew")
        self.query.bind("<Return>", lambda e: self.search())
        btn(row, "Найти", self.search, width=80).grid(row=0, column=1, padx=(8, 0))
        is_glass = self.cfg.get("liquid_glass")
        self.results = ctk.CTkScrollableFrame(p, fg_color=T["card"], corner_radius=R(0.8),
                                              border_width=1 if is_glass else 0, border_color=GLASS_BORDER)
        self.results.grid(row=4, column=0, sticky="nsew", padx=(20, 16), pady=(0, 16))

    def on_type(self, label):
        self.cat_type = TYPES[label]
        self.search()

    def clear_results(self):
        for w in self.results.winfo_children():
            w.destroy()

    def message(self, sid, text):
        if sid != self.search_id:
            return
        self.clear_results()
        lbl(self.results, text, muted=True, wraplength=500, anchor="center").pack(pady=30)

    def search(self):
        self.search_id += 1
        sid = self.search_id
        q = self.query.get().strip()
        src = self.source_seg.get()
        ptype = self.cat_type
        mc = self.cur()["mc"]
        key = self.cfg["cf_key"].strip()
        self.update_info()
        if src == "CurseForge" and ptype == "modpack":
            return self.message(sid, "Сборки только через Modrinth")
        if src == "CurseForge" and not key:
            return self.message(sid, "Нужен API-ключ CurseForge (Настройки)")
        self.message(sid, "Поиск...")

        def work():
            try:
                items = modrinth_search(q, ptype, mc) if src == "Modrinth" else cf_search(q, ptype, mc, key)
            except Exception as e:
                self.after(0, lambda: self.message(sid, f"Ошибка: {e}"))
                return
            self.after(0, lambda: self.show_results(sid, items))
        threading.Thread(target=work, daemon=True).start()

    def show_results(self, sid, items):
        if sid != self.search_id:
            return
        self.clear_results()
        if not items:
            return self.message(sid, "Ничего не найдено")
        for i, m in enumerate(items):
            self.add_card(m, i, sid)

    def add_card(self, m, i, sid):
        card = ctk.CTkFrame(
            self.results, fg_color="#1a1e28", corner_radius=16,
            border_width=1, border_color=GLASS_BORDER, height=100,
        )
        card.pack_propagate(False)

        bg_lbl = ctk.CTkLabel(card, text="", fg_color="#1a1e28")
        bg_lbl.place(x=0, y=0, relwidth=1, relheight=1)

        icon_lbl = ctk.CTkLabel(card, text="", width=56, height=56, fg_color="transparent")
        icon_lbl.place(x=14, y=22)

        title = (m.get("title") or "").strip() or "Без названия"
        author = (m.get("author") or "?").strip()
        desc = (m.get("desc") or "").replace("\n", " ").strip()
        desc = "".join(ch for ch in desc if ch.isprintable())
        if len(desc) > 100:
            desc = desc[:100].rstrip() + "…"

        title_l = ctk.CTkLabel(
            card, text=title, anchor="w",
            font=F(15, title=True), text_color="#f5f7fb", fg_color="transparent",
        )
        title_l.place(x=84, y=12)

        meta_l = ctk.CTkLabel(
            card, text=f"{author}  ·  {fmt_num(m.get('downloads') or 0)}",
            anchor="w", font=F(11), text_color="#b8c0d0", fg_color="transparent",
        )
        meta_l.place(x=84, y=38)

        desc_l = ctk.CTkLabel(
            card, text=desc, anchor="w", justify="left",
            font=F(12), text_color="#d4dae6", fg_color="transparent", wraplength=380,
        )
        desc_l.place(x=84, y=58)

        b = FancyButton(
            card, T["accent"], T.get("accent_h", T["accent"]),
            text="Установить", width=118, height=36, corner_radius=18,
            font=F(12), text_color="#ffffff",
        )
        b.configure(command=lambda: self.install_item(m, b))
        b.place(relx=1.0, x=-132, y=32)

        icon_url = (m.get("icon") or "").strip()
        card._bg_img = None
        card._icon_img = None

        def build_bg(raw: Image.Image, w: int, h: int):
            w, h = max(w, 320), max(h, 90)
            src = raw.convert("RGB")
            sw, sh = src.size
            scale = max(w / sw, h / sh)
            nw, nh = int(sw * scale) + 1, int(sh * scale) + 1
            src = src.resize((nw, nh), Image.LANCZOS)
            left, top = (nw - w) // 2, (nh - h) // 2
            src = src.crop((left, top, left + w, top + h))
            src = src.filter(ImageFilter.GaussianBlur(22))
            src = ImageEnhance.Brightness(src).enhance(0.55)
            src = ImageEnhance.Color(src).enhance(1.25)
            avg = sum(src.resize((1, 1)).getpixel((0, 0))) / 3
            if avg < 40:
                tint = Image.new("RGB", (w, h), hex2rgb(T.get("accent", "#756cff")))
                src = Image.blend(src, tint, 0.35)
                src = ImageEnhance.Brightness(src).enhance(0.7)
            overlay = Image.new("RGB", (w, h), (12, 14, 20))
            src = Image.blend(src, overlay, 0.28)
            mask = Image.new("L", (w, h), 0)
            ImageDraw.Draw(mask).rounded_rectangle((0, 0, w - 1, h - 1), radius=16, fill=255)
            out = src.convert("RGBA")
            out.putalpha(mask)
            return out

        def load():
            try:
                from io import BytesIO
                if not icon_url:
                    return
                r = requests.get(icon_url, headers=UA, timeout=12)
                r.raise_for_status()
                raw = Image.open(BytesIO(r.content))
                def apply_when_ready(tries=0):
                    try:
                        cw = max(card.winfo_width(), 400)
                        ch = max(card.winfo_height(), 100)
                        if cw < 50 and tries < 15:
                            self.after(40, lambda: apply_when_ready(tries + 1))
                            return
                        bg = build_bg(raw, cw, ch)
                        bg_ci = ctk.CTkImage(light_image=bg, dark_image=bg, size=(cw, ch))
                        ic = raw.convert("RGBA").resize((56, 56), Image.LANCZOS)
                        imask = Image.new("L", (56, 56), 0)
                        ImageDraw.Draw(imask).rounded_rectangle((0, 0, 55, 55), radius=14, fill=255)
                        ic.putalpha(imask)
                        ic_ci = ctk.CTkImage(light_image=ic, dark_image=ic, size=(56, 56))
                        card._bg_img = bg_ci
                        card._icon_img = ic_ci
                        bg_lbl.configure(image=bg_ci)
                        icon_lbl.configure(image=ic_ci)
                        bg_lbl.lower()
                        for wdg in (icon_lbl, title_l, meta_l, desc_l, b):
                            try:
                                wdg.lift()
                            except Exception:
                                pass
                    except Exception:
                        pass
                self.after(0, apply_when_ready)
            except Exception:
                pass

        if icon_url:
            threading.Thread(target=load, daemon=True).start()

        def reveal():
            if sid == self.search_id:
                try:
                    card.pack(fill="x", pady=5, padx=6)
                    card.configure(height=100)
                except Exception:
                    pass
        self.after(i * 25 if ANIM["on"] else 0, reveal)

    def show_featured_packs(self):
        top = ctk.CTkToplevel(self)
        top.title("Готовые сборки")
        top.geometry("420x360")
        top.configure(fg_color=T["card"])
        top.transient(self)
        top.grab_set()
        lbl(top, "Сборки одной кнопкой", 18, title=True).pack(anchor="w", padx=20, pady=(16, 8))
        for pack in FEATURED_PACKS:
            card = ctk.CTkFrame(top, fg_color=T["field"], corner_radius=R())
            card.pack(fill="x", padx=16, pady=6)
            lbl(card, pack["title"], 14, title=True).pack(anchor="w", padx=12, pady=(8, 0))
            lbl(card, pack["desc"], 11, muted=True).pack(anchor="w", padx=12)
            btn(card, "Установить", lambda p=pack: (top.destroy(), self.install_featured_pack(p)),
                width=120, height=30).pack(anchor="e", padx=12, pady=8)

    def install_featured_pack(self, pack):
        def work():
            v, f = modrinth_pick(pack["id"], "modpack", self.cur()["mc"])
            DOWNLOADS.mkdir(exist_ok=True)
            path = DOWNLOADS / f["filename"]
            hashes = f.get("hashes") or {}
            download(f["url"], path, expected_sha512=hashes.get("sha512"), expected_sha1=hashes.get("sha1"))
            self.import_pack_sync(path, pack["title"])
        self.run_bg(work, f"Сборка: {pack['title']}", "Готово")

    def install_item(self, m, b):
        prof = self.cur()
        ptype = self.cat_type
        key = self.cfg["cf_key"].strip()
        mc = prof["mc"]
        b.configure(state="disabled", text="...")

        def work():
            if ptype == "modpack":
                v, f = modrinth_pick(m["id"], "modpack", mc)
                DOWNLOADS.mkdir(exist_ok=True)
                path = DOWNLOADS / f["filename"]
                hashes = f.get("hashes") or {}
                download(f["url"], path, expected_sha512=hashes.get("sha512"), expected_sha1=hashes.get("sha1"))
                self.import_pack_sync(path, m["title"])
                return
            dest = Path(prof["dir"]) / DIRS[ptype]
            dest.mkdir(parents=True, exist_ok=True)
            if m["src"] == "modrinth":
                modrinth_install(m["id"], ptype, mc, dest)
            else:
                cf_install(m["id"], ptype, mc, dest, key)
            if ptype == "mod" and not prof.get("fabric"):
                prof["fabric"] = True
                self.save_cfg()

        def done(ok):
            try:
                if ok:
                    b.configure(state="disabled", text="Готово", fg_color="#3ecf8e", text_color="#0b1a12")
                    if hasattr(b, "_c"):
                        b._c = "#3ecf8e"
                else:
                    b.configure(state="normal", text="Установить")
            except Exception:
                pass
            self.update_info()
        self.run_bg(work, f"Установка {m['title']}", "Готово", done)

    def build_library(self, p):
        p.grid_columnconfigure(0, weight=1)
        p.grid_rowconfigure(3, weight=1)
        lbl(p, "Библиотека", 28, title=True).grid(row=0, column=0, sticky="ew", padx=28, pady=(24, 0))
        self.lib_info = lbl(p, "", 12, muted=True)
        self.lib_info.grid(row=1, column=0, sticky="ew", padx=28, pady=(0, 8))
        top = ctk.CTkFrame(p, fg_color="transparent")
        top.grid(row=2, column=0, sticky="ew", padx=28, pady=(0, 8))
        s = seg(top, ["Моды", "Ресурспаки", "Шейдеры"], self.on_lib_type)
        s.set(TYPE_LABEL[self.lib_type])
        s.grid(row=0, column=0, sticky="w")
        btn(top, "Папка", lambda: self.open_dir(self.lib_dir()), kind="field", width=100).grid(row=0, column=1)
        is_glass = self.cfg.get("liquid_glass")
        self.lib_list = ctk.CTkScrollableFrame(p, fg_color=T["card"], corner_radius=R(0.8),
                                               border_width=1 if is_glass else 0, border_color=GLASS_BORDER)
        self.lib_list.grid(row=3, column=0, sticky="nsew", padx=(20, 16), pady=(0, 16))

    def lib_dir(self):
        return Path(self.cur()["dir"]) / DIRS[self.lib_type]

    def on_lib_type(self, label):
        self.lib_type = TYPES[label]
        self.refresh_library()

    def refresh_library(self):
        try:
            for w in self.lib_list.winfo_children():
                w.destroy()
        except Exception:
            return
        d = self.lib_dir()
        self.lib_info.configure(text=str(d))
        files = sorted(d.iterdir(), key=lambda f: f.name.lower()) if d.exists() else []
        if not files:
            lbl(self.lib_list, "Пусто", muted=True, anchor="center").pack(pady=30)
            return
        for f in files:
            self.lib_row(f)

    def lib_row(self, f):
        row = ctk.CTkFrame(self.lib_list, fg_color=T["field"], corner_radius=R(),
                           border_width=1, border_color=GLASS_BORDER)
        row.pack(fill="x", pady=3, padx=4)
        row.grid_columnconfigure(0, weight=1)
        disabled = f.name.endswith(".disabled")
        size = (f.stat().st_size if f.is_file() else folder_size(f)) / 1048576
        lbl(row, f.name.removesuffix(".disabled"), 13).grid(row=0, column=0, sticky="ew", padx=12, pady=(6, 0))
        lbl(row, f"{size:.1f} МБ" + (" • выкл" if disabled else ""), 11, muted=True).grid(row=1, column=0, sticky="ew", padx=12, pady=(0, 6))
        if self.lib_type == "mod":
            sw = ctk.CTkSwitch(row, text="", width=42, progress_color=T["accent"], command=lambda: self.toggle_file(f))
            if not disabled:
                sw.select()
            sw.grid(row=0, column=1, rowspan=2, padx=4)
        btn(row, "×", lambda: self.remove_file(f), kind="danger", width=36, height=28).grid(row=0, column=2, rowspan=2, padx=(0, 8))

    def toggle_file(self, f):
        new = f.with_name(f.name.removesuffix(".disabled") if f.name.endswith(".disabled") else f.name + ".disabled")
        f.rename(new)
        self.refresh_library()

    def remove_file(self, f):
        if f.is_dir():
            shutil.rmtree(f, ignore_errors=True)
        else:
            f.unlink(missing_ok=True)
        self.refresh_library()
        self.update_info()

    def sec(self, parent, title):
        lbl(parent, title, 16, title=True).pack(anchor="w", padx=8, pady=(16, 4))

    def row_switch(self, parent, text, key):
        sw = ctk.CTkSwitch(parent, text=text, font=F(), text_color=T["text"], progress_color=T["accent"],
                           command=lambda: self.put(key, bool(sw.get())))
        if self.cfg.get(key):
            sw.select()
        sw.pack(anchor="w", padx=8, pady=5)

    def row_slider(self, parent, text, key, lo, hi, steps, fmt=lambda v: str(v)):
        f = ctk.CTkFrame(parent, fg_color="transparent")
        f.pack(fill="x", padx=8, pady=3)
        head = lbl(f, f"{text}: {fmt(self.cfg.get(key, lo))}")
        head.pack(anchor="w")
        def on(v):
            v = int(round(v))
            self.put(key, v)
            head.configure(text=f"{text}: {fmt(v)}")
        s = ctk.CTkSlider(f, from_=lo, to=hi, number_of_steps=steps, fg_color=T["field"],
                          progress_color=T["accent"], button_color=T["accent"], command=on)
        s.set(self.cfg.get(key, lo))
        s.pack(fill="x", pady=(3, 0))

    def row_entry(self, parent, text, key, width=260, num=False, show=None, browse=False):
        f = ctk.CTkFrame(parent, fg_color="transparent")
        f.pack(fill="x", padx=8, pady=3)
        lbl(f, text).pack(side="left")
        e = entry(f, width=width, **({"show": show} if show else {}))
        e.pack(side="right")
        if self.cfg.get(key):
            e.insert(0, str(self.cfg[key]))
        def commit(_=None):
            val = e.get().strip()
            if num:
                try:
                    val = int(val)
                except Exception:
                    val = 0
            self.put(key, val)
        e.bind("<FocusOut>", commit)
        e.bind("<Return>", commit)
        if browse:
            def pick():
                path = filedialog.askopenfilename()
                if path:
                    e.delete(0, "end")
                    e.insert(0, path)
                    commit()
            btn(f, "...", pick, kind="field", width=36).pack(side="right", padx=(0, 4))

    def row_menu(self, parent, text, key, values, width=180):
        f = ctk.CTkFrame(parent, fg_color="transparent")
        f.pack(fill="x", padx=8, pady=4)
        lbl(f, text).pack(side="left")
        m = menu(f, values, width=width, command=lambda v: self.put(key, v))
        cur = str(self.cfg.get(key, values[0]))
        if cur in values:
            m.set(cur)
        else:
            m.set(values[0])
        m.pack(side="right")
        return m

    # ====================== СЕРВЕРА ======================
    def build_servers(self, p):
        p.grid_columnconfigure(0, weight=1)
        p.grid_rowconfigure(2, weight=1)
        lbl(p, "Сервера", 28, title=True).grid(row=0, column=0, sticky="ew", padx=28, pady=(24, 6))
        bar = ctk.CTkFrame(p, fg_color="transparent")
        bar.grid(row=1, column=0, sticky="ew", padx=28, pady=(0, 8))
        btn(bar, "Обновить пинг", self.refresh_servers, kind="field", width=130).pack(side="left")
        btn(bar, "Добавить", self.add_custom_server, kind="field", width=100).pack(side="left", padx=6)
        self.servers_list = ctk.CTkScrollableFrame(p, fg_color=T["card"], corner_radius=R(0.8),
                                                   border_width=1, border_color=GLASS_BORDER)
        self.servers_list.grid(row=2, column=0, sticky="nsew", padx=(20, 16), pady=(0, 16))

    def refresh_servers(self):
        try:
            for w in self.servers_list.winfo_children():
                w.destroy()
        except Exception:
            return
        lbl(self.servers_list, "Проверка...", muted=True).pack(pady=12)
        servers = list(DEFAULT_SERVERS) + list(self.cfg.get("custom_servers") or [])

        def work():
            results = []
            for s in servers:
                ms = ping_server(s["host"], s.get("port", 25565))
                results.append((s, ms))
            self.after(0, lambda: self._fill_servers(results))
        threading.Thread(target=work, daemon=True).start()

    def _fill_servers(self, results):
        try:
            for w in self.servers_list.winfo_children():
                w.destroy()
        except Exception:
            return
        if not results:
            lbl(self.servers_list, "Пусто", muted=True).pack(pady=20)
            return
        for s, ms in results:
            row = ctk.CTkFrame(self.servers_list, fg_color=T["field"], corner_radius=R(),
                               border_width=1, border_color=GLASS_BORDER)
            row.pack(fill="x", padx=6, pady=4)
            row.grid_columnconfigure(0, weight=1)
            ping_txt = f"{ms} мс" if ms is not None else "оффлайн"
            color = T["accent"] if ms is not None and ms < 150 else (T["text"] if ms is not None else T["muted"])
            lbl(row, s["name"], 14, title=True).grid(row=0, column=0, sticky="w", padx=12, pady=(8, 0))
            lbl(row, f'{s["host"]}:{s.get("port", 25565)}  •  {ping_txt}', 11, muted=True, color=color).grid(
                row=1, column=0, sticky="w", padx=12, pady=(0, 8))
            addr = f'{s["host"]}:{s.get("port", 25565)}'
            btn(row, "Играть", lambda a=addr: self.join_server(a), width=90, height=32).grid(
                row=0, column=1, rowspan=2, padx=10)

    def join_server(self, address: str):
        self.cfg["last_server"] = address
        self.save_cfg()
        messagebox.showinfo("Сервер", f"Адрес сохранён: {address}\nНажми ИГРАТЬ — сервер подставится при запуске.")
        self.show("play")

    def add_custom_server(self):
        top = ctk.CTkToplevel(self)
        top.title("Сервер")
        top.geometry("360x240")
        top.configure(fg_color=T["card"])
        top.transient(self)
        top.grab_set()
        lbl(top, "Название", muted=True).pack(anchor="w", padx=20, pady=(16, 0))
        name_e = entry(top)
        name_e.pack(fill="x", padx=20, pady=4)
        lbl(top, "Хост", muted=True).pack(anchor="w", padx=20)
        host_e = entry(top)
        host_e.pack(fill="x", padx=20, pady=4)
        lbl(top, "Порт", muted=True).pack(anchor="w", padx=20)
        port_e = entry(top)
        port_e.insert(0, "25565")
        port_e.pack(fill="x", padx=20, pady=4)

        def save():
            n, h = name_e.get().strip(), host_e.get().strip()
            try:
                port = int(port_e.get().strip() or "25565")
            except Exception:
                port = 25565
            if not n or not h:
                return messagebox.showerror("Ошибка", "Заполни название и хост", parent=top)
            lst = list(self.cfg.get("custom_servers") or [])
            lst.append({"name": n, "host": h, "port": port})
            self.cfg["custom_servers"] = lst
            self.save_cfg()
            top.destroy()
            self.refresh_servers()
        btn(top, "Сохранить", save).pack(fill="x", padx=20, pady=14)

    # ====================== СКИНЫ ======================
    def build_skins(self, p):
        p.grid_columnconfigure(0, weight=1)
        p.grid_rowconfigure(1, weight=1)
        lbl(p, "Скины и плащи", 28, title=True).grid(row=0, column=0, sticky="ew", padx=28, pady=(24, 6))
        sc = ctk.CTkScrollableFrame(p, fg_color=T["card"], corner_radius=R(0.8),
                                    border_width=1, border_color=GLASS_BORDER)
        sc.grid(row=1, column=0, sticky="nsew", padx=(20, 16), pady=(0, 16))
        self.skins_box = sc

        self.sec(sc, "Ник (должен совпадать с ником при запуске)")
        row = ctk.CTkFrame(sc, fg_color="transparent")
        row.pack(fill="x", padx=8, pady=4)
        self.skin_nick_e = entry(row, width=180)
        self.skin_nick_e.insert(0, self.cfg.get("auth_nick") or self.cfg.get("nick", "Player"))
        self.skin_nick_e.pack(side="left")
        btn(row, "Превью", self.refresh_skins, kind="field", width=90).pack(side="left", padx=6)
        btn(row, "Скачать с Ely.by", self.apply_ely_skin, kind="field", width=140).pack(side="left")

        self.sec(sc, "Превью")
        self.skin_preview = lbl(sc, "Укажи ник и нажми «Превью» или «Скачать с Ely.by»", muted=True)
        self.skin_preview.pack(anchor="w", padx=8, pady=4)
        prev_row = ctk.CTkFrame(sc, fg_color="transparent")
        prev_row.pack(pady=8)
        self.skin_img_label = ctk.CTkLabel(prev_row, text="")
        self.skin_img_label.pack(side="left", padx=8)
        self.cape_img_label = ctk.CTkLabel(prev_row, text="")
        self.cape_img_label.pack(side="left", padx=8)

        self.sec(sc, "Свой скин / плащ")
        lbl(sc, "Файлы сохраняются в профиль и имеют приоритет над Ely.by.\n"
                "Скин: 64×64 (или HD). Плащ: обычно 64×32.", 12, muted=True, wraplength=480).pack(
            anchor="w", padx=8, pady=4)
        br = ctk.CTkFrame(sc, fg_color="transparent")
        br.pack(fill="x", padx=8, pady=6)
        btn(br, "Загрузить скин…", self.upload_skin, width=150).pack(side="left")
        btn(br, "Загрузить плащ…", self.upload_cape, width=150).pack(side="left", padx=8)
        btn(br, "Удалить локальные", self.clear_local_cosmetics, kind="danger", width=150).pack(side="left")

        self.sec(sc, "Мод в игре")
        lbl(sc, "Чтобы скин и плащ были видны в Minecraft, нужен CustomSkinLoader\n"
                "(ставится только с твоего согласия).", 12, muted=True, wraplength=480).pack(
            anchor="w", padx=8, pady=4)
        self.cape_sw = ctk.CTkSwitch(
            sc, text="Разрешить установку мода скинов/плащей при запуске",
            font=F(), text_color=T["text"], progress_color=T["accent"],
            command=self._toggle_cape_mod
        )
        if self.cfg.get("cape_mod_ok"):
            self.cape_sw.select()
        self.cape_sw.pack(anchor="w", padx=8, pady=8)

        def open_ely():
            import webbrowser
            webbrowser.open("https://ely.by")
        btn(sc, "Открыть Ely.by", open_ely, kind="field", width=140).pack(anchor="w", padx=8, pady=4)

    def _skin_nick(self):
        try:
            n = self.skin_nick_e.get().strip()
        except Exception:
            n = ""
        return n or self.cfg.get("auth_nick") or self.cfg.get("nick", "Player")

    def _toggle_cape_mod(self):
        if self.cape_sw.get():
            ok = messagebox.askyesno(
                "Согласие",
                "Будет установлен актуальный CustomSkinLoader и прописан Ely.by / локальные файлы как источники скинов и плащей.\n\n"
                "Продолжить?"
            )
            if not ok:
                self.cape_sw.deselect()
                self.cfg["cape_mod_ok"] = False
                self.save_cfg()
                return
            self.cfg["cape_mod_ok"] = True
            try:
                d = Path(self.cur()["dir"])
                write_customskinloader_config(d)
                local_skin_dirs(d)
            except Exception:
                pass
        else:
            self.cfg["cape_mod_ok"] = False
        self.save_cfg()

    def apply_ely_skin(self):
        nick = self._skin_nick()
        inst = Path(self.cur()["dir"])

        def work():
            try:
                write_customskinloader_config(inst)
                img = ely_fetch_skin_image(nick)
                save_local_skin(inst, nick, img)
                try:
                    r = requests.get(ely_cape_url(nick), headers=UA, timeout=12)
                    if r.status_code == 200 and r.headers.get("content-type", "").startswith("image"):
                        from io import BytesIO
                        cape = Image.open(BytesIO(r.content)).convert("RGBA")
                        save_local_cape(inst, nick, cape)
                except Exception:
                    pass
                self.cfg["nick"] = nick
                if self.cfg.get("auth_provider") != "ely":
                    self.cfg["auth_nick"] = nick
                self.save_cfg()
                self.after(0, lambda: (
                    self.refresh_skins(),
                    messagebox.showinfo(
                        "Готово",
                        f"Скин «{nick}» сохранён в профиль.\n"
                        f"Включи мод скинов/плащей и запускай с ником «{nick}»."
                    )
                ))
            except Exception as e:
                self.after(0, lambda: messagebox.showerror("Ely.by", f"Не удалось скачать скин: {e}"))
        threading.Thread(target=work, daemon=True).start()

    def upload_skin(self):
        path = filedialog.askopenfilename(filetypes=[("PNG", "*.png")])
        if not path:
            return
        nick = self._skin_nick()
        try:
            img = Image.open(path).convert("RGBA")
            inst = Path(self.cur()["dir"])
            write_customskinloader_config(inst)
            save_local_skin(inst, nick, img)
            self.cfg["nick"] = nick
            self.save_cfg()
            try:
                self.nick.delete(0, "end")
                self.nick.insert(0, nick)
            except Exception:
                pass
            self.refresh_skins()
            messagebox.showinfo("Скин", f"Скин сохранён для ника «{nick}».\nВключи мод и запускай с этим ником.")
        except Exception as e:
            messagebox.showerror("Ошибка", str(e))

    def upload_cape(self):
        path = filedialog.askopenfilename(filetypes=[("PNG", "*.png")])
        if not path:
            return
        nick = self._skin_nick()
        try:
            img = Image.open(path).convert("RGBA")
            inst = Path(self.cur()["dir"])
            write_customskinloader_config(inst)
            save_local_cape(inst, nick, img)
            self.cfg["nick"] = nick
            self.save_cfg()
            self.refresh_skins()
            messagebox.showinfo("Плащ", f"Плащ сохранён для ника «{nick}».")
        except Exception as e:
            messagebox.showerror("Ошибка", str(e))

    def clear_local_cosmetics(self):
        nick = self._skin_nick()
        inst = Path(self.cur()["dir"])
        skins, capes, _ = local_skin_dirs(inst)
        for f in (skins / f"{nick}.png", capes / f"{nick}.png"):
            f.unlink(missing_ok=True)
        self.refresh_skins()
        messagebox.showinfo("Очищено", f"Локальные скин/плащ для «{nick}» удалены.")

    def refresh_skins(self):
        nick = self._skin_nick()
        inst = Path(self.cur()["dir"])

        def work(n=nick):
            skin_img = cape_img = None
            try:
                skins, capes, _ = local_skin_dirs(inst)
                sp = skins / f"{n}.png"
                cp = capes / f"{n}.png"
                if sp.exists():
                    skin_img = Image.open(sp).convert("RGBA")
                if cp.exists():
                    cape_img = Image.open(cp).convert("RGBA")
            except Exception:
                pass
            if skin_img is None:
                try:
                    skin_img = ely_fetch_skin_image(n)
                except Exception:
                    pass
            if cape_img is None:
                try:
                    from io import BytesIO
                    r = requests.get(ely_cape_url(n), headers=UA, timeout=10)
                    if r.status_code == 200:
                        cape_img = Image.open(BytesIO(r.content)).convert("RGBA")
                except Exception:
                    pass

            def show():
                try:
                    if skin_img:
                        s = skin_img.copy()
                        sc = max(4, 128 // max(1, s.width))
                        s = s.resize((s.width * sc, s.height * sc), Image.NEAREST)
                        ci = ctk.CTkImage(light_image=s, dark_image=s, size=s.size)
                        self.skin_img_label.configure(image=ci, text="")
                        self.skin_img_label.image = ci
                    else:
                        self.skin_img_label.configure(image=None, text="нет скина")
                    if cape_img:
                        c = cape_img.copy()
                        sc = max(3, 96 // max(1, c.width))
                        c = c.resize((c.width * sc, c.height * sc), Image.NEAREST)
                        ci = ctk.CTkImage(light_image=c, dark_image=c, size=c.size)
                        self.cape_img_label.configure(image=ci, text="")
                        self.cape_img_label.image = ci
                    else:
                        self.cape_img_label.configure(image=None, text="нет плаща")
                    src = "локальный" if (inst / "CustomSkinLoader" / "LocalSkin" / "skins" / f"{n}.png").exists() else "Ely.by"
                    self.skin_preview.configure(text=f"{n}  •  источник: {src}")
                except Exception:
                    pass
            self.after(0, show)
        threading.Thread(target=work, daemon=True).start()

    def check_for_updates(self):
        if not self.cfg.get("check_updates", True):
            return
        url = self.cfg.get("update_url") or DEFAULTS.get("update_url")

        def work():
            info = check_launcher_update(url)
            if info and info.get("tag"):
                self.after(0, lambda: self._offer_update(info))
        threading.Thread(target=work, daemon=True).start()

    def _offer_update(self, info):
        """Показываем только страницу релиза. Файлы не скачиваем автоматически."""
        msg = f"Доступна версия: {info.get('tag')}\n\nОткрыть страницу загрузки?"
        if info.get("sha256"):
            msg += f"\n\nSHA-256: {info['sha256'][:16]}…"
        if messagebox.askyesno("Обновление", msg):
            try:
                import webbrowser
                url = info.get("url") or ""
                if _check_host(url, ALLOWED_UPDATE_HOSTS):
                    webbrowser.open(url)
            except Exception:
                pass

    def build_style(self, p):
        p.grid_columnconfigure(0, weight=1)
        p.grid_rowconfigure(1, weight=1)
        head = ctk.CTkFrame(p, fg_color="transparent")
        head.grid(row=0, column=0, sticky="ew", padx=28, pady=(24, 6))
        head.grid_columnconfigure(0, weight=1)
        lbl(head, "Оформление", 28, title=True).grid(row=0, column=0, sticky="w")
        btn(head, "Применить", self.apply_style, width=130).grid(row=0, column=1)
        is_glass = self.cfg.get("liquid_glass")
        sc = ctk.CTkScrollableFrame(p, fg_color=T["card"], corner_radius=R(0.8),
                                    border_width=1 if is_glass else 0, border_color=GLASS_BORDER)
        sc.grid(row=1, column=0, sticky="nsew", padx=(20, 16), pady=(0, 16))

        self.sec(sc, "Тема")
        f = ctk.CTkFrame(sc, fg_color="transparent")
        f.pack(fill="x", padx=8, pady=4)
        lbl(f, "Цветовая схема").pack(side="left")
        m = menu(f, list(THEMES), width=200, command=self.on_theme)
        m.set(self.cfg["theme"])
        m.pack(side="right")

        self.row_switch(sc, "Liquid Glass (ультра-стекло)", "liquid_glass")

        f = ctk.CTkFrame(sc, fg_color="transparent")
        f.pack(fill="x", padx=8, pady=4)
        lbl(f, "Цвет акцента").pack(side="left")
        btn(f, "Сброс", self.reset_accent, kind="field", width=70).pack(side="right")
        btn(f, "Выбрать", self.pick_accent, kind="field", width=90).pack(side="right", padx=6)
        self.swatch = ctk.CTkFrame(f, width=28, height=28, corner_radius=8, fg_color=T["accent"])
        self.swatch.pack(side="right")

        self.row_slider(sc, "Скругление", "radius", 0, 28, 28, lambda v: f"{v}px")
        self.row_slider(sc, "Масштаб", "scale", 80, 130, 10, lambda v: f"{v}%")
        self.row_switch(sc, "Анимации", "anim")
        self.row_slider(sc, "Скорость анимаций", "anim_speed", 50, 200, 15, lambda v: f"{v}%")

        self.sec(sc, "Шрифт")
        fonts = sorted(set(FONT["loaded"] + ["Segoe UI", "Arial", "Calibri", "Consolas"]))
        self.ft_cb = self.font_row(sc, "Заголовки", fonts, FONT["title"])
        self.fb_cb = self.font_row(sc, "Текст", fonts, FONT["body"])
        fb = ctk.CTkFrame(sc, fg_color="transparent")
        fb.pack(fill="x", padx=8, pady=4)
        btn(fb, "Выбрать шрифт...", self.pick_font, kind="field", width=160).pack(side="left")

        self.sec(sc, "Обои")
        self.row_switch(sc, "Показывать обои", "wall_on")
        self.row_slider(sc, "Затемнение", "wall_dim", 0, 90, 90, lambda v: f"{v}%")
        self.row_slider(sc, "Размытие", "wall_blur", 0, 20, 20, lambda v: f"{v}px")
        bar = ctk.CTkFrame(sc, fg_color="transparent")
        bar.pack(fill="x", padx=8, pady=6)
        btn(bar, "Свой файл", self.pick_local_wall, kind="field", width=110).pack(side="left")
        btn(bar, "Обновить", lambda: self.load_gallery(True), kind="field", width=100).pack(side="left", padx=6)
        btn(bar, "Убрать", lambda: self.pick_wall(""), kind="field", width=90).pack(side="left")
        self.gallery = ctk.CTkFrame(sc, fg_color="transparent")
        self.gallery.pack(fill="x", padx=2, pady=4)

    def font_row(self, parent, text, values, current):
        f = ctk.CTkFrame(parent, fg_color="transparent")
        f.pack(fill="x", padx=8, pady=3)
        lbl(f, text).pack(side="left")
        cb = ctk.CTkComboBox(f, values=values, width=220, height=36, corner_radius=R(0.9),
                             fg_color=T["field"], border_width=1, border_color=GLASS_BORDER,
                             button_color=T["field"], dropdown_fg_color=T["card"], text_color=T["text"], font=F())
        cb.set(current)
        cb.pack(side="right")
        return cb

    def on_theme(self, name):
        self.put("theme", name)
        self.put("accent", "")
        self.swatch.configure(fg_color=THEMES[name]["accent"])

    def pick_accent(self):
        c = colorchooser.askcolor(color=self.cfg.get("accent") or T["accent"])
        if c and c[1]:
            self.put("accent", c[1])
            self.swatch.configure(fg_color=c[1])

    def reset_accent(self):
        self.put("accent", "")
        self.swatch.configure(fg_color=THEMES[self.cfg["theme"]]["accent"])

    def pick_font(self):
        path = filedialog.askopenfilename(filetypes=[("Шрифты", "*.ttf *.otf")])
        if not path:
            return
        FONTS.mkdir(exist_ok=True)
        dst = FONTS / Path(path).name
        if not dst.exists() or dst.resolve() != Path(path).resolve():
            shutil.copy(path, dst)
        fam = load_font_file(dst)
        if fam:
            self.ft_cb.set(fam)
            self.fb_cb.set(fam)

    def apply_style(self):
        self.cfg["font_title"] = self.ft_cb.get().strip()
        self.cfg["font_body"] = self.fb_cb.get().strip()
        self.cfg["radius"] = max(0, min(28, int(self.cfg.get("radius", DEFAULTS["radius"]))))
        self.save_cfg()
        set_theme(self.cfg)
        apply_fonts(self.cfg)
        s = self.cfg["scale"] / 100
        ctk.set_widget_scaling(s)
        ctk.set_window_scaling(s)
        self.geometry(f"{W}x{H}")
        self.after(20, lambda: self.rebuild("style"))
        self.after(100, self._apply_rounded_corners)

    def load_gallery(self, force=False):
        if self.gal_loading:
            return
        self.gal_loading = True
        if force:
            self.gal_items = []
        try:
            for w in self.gallery.winfo_children():
                w.destroy()
            lbl(self.gallery, "Загрузка...", muted=True).pack(padx=8, pady=8)
        except Exception:
            pass

        def work():
            names = list_wallpapers()
            WALLS.mkdir(exist_ok=True)
            local = [f.name for f in WALLS.iterdir() if f.suffix.lower() in IMG_EXT and f.name not in names]
            items = []
            for n in names + local:
                try:
                    path = fetch_wallpaper(n) if n in names else WALLS / n
                    items.append((n, path, make_thumb(path)))
                except Exception:
                    pass
            self.gal_items = items
            self.gal_loading = False
            self.after(0, self.fill_gallery)
        threading.Thread(target=work, daemon=True).start()

    def fill_gallery(self):
        try:
            for w in self.gallery.winfo_children():
                w.destroy()
            if not self.gal_items:
                lbl(self.gallery, "Нет обоев", muted=True).pack(padx=8, pady=8)
                return
            for n, path, th in self.gal_items:
                ci = ctk.CTkImage(light_image=th, dark_image=th, size=th.size)
                sel = str(path) == self.cfg.get("wall_file")
                card = ctk.CTkFrame(self.gallery, fg_color=T["field"], corner_radius=R(0.9),
                                    border_width=2 if sel else 1,
                                    border_color=T["accent"] if sel else GLASS_BORDER)
                card.pack(fill="x", padx=6, pady=5)
                im = ctk.CTkLabel(card, text="", image=ci)
                im.pack(padx=6, pady=(6, 2))
                cap = lbl(card, Path(n).stem, 11, anchor="center")
                cap.pack(pady=(0, 6))
                selected_path = str(path)
                for w in (card, im, cap):
                    w.bind("<Button-1>", lambda e, pp=selected_path: self.pick_wall(pp))
        except Exception:
            pass

    def pick_wall(self, path):
        self.cfg["wall_file"] = path
        self.cfg["wall_on"] = bool(path)
        self.save_cfg()
        self.fill_gallery()

    def pick_local_wall(self):
        path = filedialog.askopenfilename(filetypes=[("Изображения", "*.png *.jpg *.jpeg *.webp")])
        if not path:
            return
        WALLS.mkdir(exist_ok=True)
        dst = WALLS / Path(path).name
        if not dst.exists() or dst.resolve() != Path(path).resolve():
            shutil.copy(path, dst)
        self.cfg["wall_file"] = str(dst)
        self.cfg["wall_on"] = True
        self.save_cfg()
        self.load_gallery(True)

    def install_shortcut(self):
        icon = self.cfg.get("launcher_icon") or None
        create_desktop_shortcut(icon)
        messagebox.showinfo("Ярлык", "Ярлык установлен на рабочий стол.")

    def update_shortcut(self):
        delete_desktop_shortcut()
        create_desktop_shortcut(self.cfg.get("launcher_icon") or None)
        messagebox.showinfo("Ярлык", "Ярлык обновлён (иконка и путь).")

    def remove_shortcut(self):
        if delete_desktop_shortcut():
            messagebox.showinfo("Ярлык", "Ярлык удалён.")
        else:
            messagebox.showwarning("Ярлык", "Ярлык не найден или не удалось удалить.")

    def build_settings(self, p):
        p.grid_columnconfigure(0, weight=1)
        p.grid_rowconfigure(1, weight=1)
        lbl(p, "Настройки", 28, title=True).grid(row=0, column=0, sticky="ew", padx=28, pady=(24, 6))
        is_glass = self.cfg.get("liquid_glass")
        sc = ctk.CTkScrollableFrame(p, fg_color=T["card"], corner_radius=R(0.8),
                                    border_width=1 if is_glass else 0, border_color=GLASS_BORDER)
        sc.grid(row=1, column=0, sticky="nsew", padx=(20, 16), pady=(0, 16))

        self.sec(sc, "Память и JVM")
        self.row_slider(sc, "ОЗУ (макс)", "ram", 1024, 32768, 62, lambda v: f"{v/1024:.1f} ГБ")
        self.row_slider(sc, "ОЗУ (мин)", "ram_min", 256, 8192, 30, lambda v: f"{v/1024:.2f} ГБ")
        self.row_menu(sc, "Сборщик мусора", "gc", ["G1", "ZGC", "Parallel", "Shenandoah", "Off"])
        self.row_switch(sc, "Флаги Aikar (оптимизация GC)", "aikar_flags")
        self.row_switch(sc, "JVM debug (-agentlib:jdwp)", "jvm_debug")
        self.row_entry(sc, "Debug порт", "jvm_debug_port", 90, num=True)
        self.row_entry(sc, "Доп. JVM аргументы", "jvm_args")
        self.row_entry(sc, "Путь к Java", "java_path", browse=True)
        self.row_entry(sc, "Extra classpath", "extra_classpath")
        self.row_entry(sc, "ENV (KEY=VAL;KEY2=VAL2)", "env_vars")

        self.sec(sc, "Экран и запуск игры")
        self.row_entry(sc, "Ширина окна", "res_w", 90, num=True)
        self.row_entry(sc, "Высота окна", "res_h", 90, num=True)
        self.row_switch(sc, "Полный экран", "fullscreen")
        self.row_slider(sc, "Лимит FPS (0 = выкл)", "max_fps_arg", 0, 360, 36, lambda v: str(v) if v else "выкл")
        self.row_switch(sc, "Подсказка VSync", "vsync_hint")
        self.row_switch(sc, "Демо-режим Minecraft", "demo_mode")
        self.row_switch(sc, "Quick Play: одиночная", "quick_play_singleplayer")
        self.row_switch(sc, "Подтверждать перед запуском", "confirm_launch")
        self.row_switch(sc, "Авто-вход на последний сервер", "auto_join_server")
        self.row_switch(sc, "Запоминать последний сервер", "remember_last_server")
        self.row_switch(sc, "Закрывать лаунчер после запуска", "close_on_launch")
        self.row_switch(sc, "Сворачивать при запуске", "minimize_on_launch")

        self.sec(sc, "Файлы, сеть, загрузки")
        self.row_switch(sc, "Проверять файлы игры", "verify_files")
        self.row_switch(sc, "Показывать снапшоты", "show_snapshots")
        self.row_switch(sc, "Безопасный режим (без авто-модов)", "safe_mode")
        self.row_switch(sc, "Бэкап перед установкой модов", "backup_before_install")
        self.row_slider(sc, "Хранить бэкапы (дней)", "auto_backup_days", 0, 30, 30, lambda v: str(v))
        self.row_slider(sc, "Таймаут загрузки (сек)", "download_timeout", 5, 120, 23, lambda v: f"{v} с")
        self.row_slider(sc, "Параллельные загрузки", "parallel_downloads", 1, 16, 15, lambda v: str(v))
        self.row_slider(sc, "Повторы сети", "net_retries", 0, 10, 10, lambda v: str(v))
        self.row_entry(sc, "Прокси хост", "proxy_host", 160)
        self.row_entry(sc, "Прокси порт", "proxy_port", 90, num=True)
        self.row_entry(sc, "Свой game directory", "game_dir_override", browse=False)
        self.row_menu(sc, "Предпочитаемый лоадер", "prefer_loader", ["fabric", "quilt", "forge", "vanilla"])

        self.sec(sc, "Поведение лаунчера")
        self.row_menu(sc, "Стартовая вкладка", "start_page",
                      ["play", "game", "catalog", "library", "servers", "skins", "style", "settings"])
        self.row_menu(sc, "Язык UI", "launcher_lang", ["ru", "en"])
        self.row_switch(sc, "Поверх всех окон", "always_on_top")
        self.row_slider(sc, "Прозрачность окна", "window_opacity", 60, 100, 40, lambda v: f"{v}%")
        self.row_switch(sc, "Компактный сайдбар", "sidebar_compact")
        self.row_switch(sc, "Скрыть статус внизу", "hide_status")
        self.row_switch(sc, "Двойной клик = Играть", "double_click_play")
        self.row_switch(sc, "Проверять обновления лаунчера", "check_updates")
        self.row_switch(sc, "Звук когда готово", "sound_on_ready")
        self.row_switch(sc, "Discord RPC (заглушка)", "discord_rpc")
        self.row_switch(sc, "Хранить логи", "keep_logs")
        self.row_switch(sc, "Показывать консоль игры", "show_console")
        self.row_switch(sc, "Проверка обновлений модов", "mod_update_check")
        self.row_switch(sc, "Экспорт crash-reports", "export_crash_reports")
        self.row_entry(sc, "CurseForge API-ключ", "cf_key", show="•")
        self.row_entry(sc, "URL обновлений", "update_url")

        self.sec(sc, "Ярлык на рабочем столе")
        sc_bar = ctk.CTkFrame(sc, fg_color="transparent")
        sc_bar.pack(fill="x", padx=8, pady=6)
        btn(sc_bar, "Установить", self.install_shortcut, kind="field", width=120).pack(side="left")
        btn(sc_bar, "Обновить", self.update_shortcut, kind="field", width=120).pack(side="left", padx=6)
        btn(sc_bar, "Удалить", self.remove_shortcut, kind="danger", width=120).pack(side="left")

        self.sec(sc, "Данные и обслуживание")
        lbl(sc, f"Папка: {ROOT}", 11, muted=True).pack(anchor="w", padx=8)
        bar = ctk.CTkFrame(sc, fg_color="transparent")
        bar.pack(fill="x", padx=8, pady=8)
        btn(bar, "Открыть папку", lambda: self.open_dir(ROOT), kind="field", width=120).pack(side="left")
        btn(bar, "Экспорт конфига", self.export_config, kind="field", width=130).pack(side="left", padx=6)
        btn(bar, "Импорт конфига", self.import_config, kind="field", width=130).pack(side="left")
        bar2 = ctk.CTkFrame(sc, fg_color="transparent")
        bar2.pack(fill="x", padx=8, pady=4)
        btn(bar2, "Очистить кэш загрузок", self.clear_downloads, kind="field", width=170).pack(side="left")
        btn(bar2, "Сбросить стиль", self.reset_style, kind="field", width=130).pack(side="left", padx=6)
        btn(sc, "Применить окно (поверх / прозрачность)", self.apply_window_prefs, width=280).pack(anchor="w", padx=8, pady=8)
        btn(sc, "Удалить всё", self.wipe, kind="danger", width=180).pack(anchor="w", padx=8, pady=8)

    def export_config(self):
        path = filedialog.asksaveasfilename(defaultextension=".json", filetypes=[("JSON", "*.json")])
        if not path:
            return
        try:
            export = dict(self.cfg)
            # токен в экспорт не отдаём
            export["ely_access_token"] = ""
            Path(path).write_text(json.dumps(export, ensure_ascii=False, indent=2), encoding="utf-8")
            messagebox.showinfo("Экспорт", "Конфиг сохранён (без токена).")
        except Exception as e:
            messagebox.showerror("Ошибка", str(e))

    def import_config(self):
        path = filedialog.askopenfilename(filetypes=[("JSON", "*.json")])
        if not path:
            return
        try:
            data = json.loads(Path(path).read_text(encoding="utf-8"))
            if not isinstance(data, dict):
                raise ValueError("Неверный формат")
            keep = dict(self.cfg.get("profiles") or {})
            keep_token = self.cfg.get("ely_access_token", "")
            self.cfg.update({**DEFAULTS, **data})
            # токен из импорта не подхватываем
            self.cfg["ely_access_token"] = keep_token
            if not self.cfg.get("profiles"):
                self.cfg["profiles"] = keep
            ensure_profiles(self.cfg)
            self.save_cfg()
            set_theme(self.cfg)
            self.rebuild("settings")
            messagebox.showinfo("Импорт", "Конфиг загружен.")
        except Exception as e:
            messagebox.showerror("Ошибка", str(e))

    def clear_downloads(self):
        if messagebox.askyesno("Кэш", "Удалить папку downloads?"):
            shutil.rmtree(DOWNLOADS, ignore_errors=True)
            DOWNLOADS.mkdir(parents=True, exist_ok=True)
            messagebox.showinfo("Готово", "Кэш очищен.")

    def apply_window_prefs(self):
        try:
            op = max(0.6, min(1.0, (self.cfg.get("window_opacity") or 100) / 100))
            self.attributes("-alpha", op)
        except Exception:
            pass
        try:
            self.attributes("-topmost", bool(self.cfg.get("always_on_top")))
        except Exception:
            pass
        messagebox.showinfo("Окно", "Параметры окна применены.")

    def reset_style(self):
        if messagebox.askyesno("Сброс", "Сбросить оформление?"):
            for k in APPEARANCE_KEYS:
                self.cfg[k] = DEFAULTS[k]
            self.save_cfg()
            set_theme(self.cfg)
            apply_fonts(self.cfg)
            ctk.set_widget_scaling(1.0)
            ctk.set_window_scaling(1.0)
            self.after(20, lambda: self.rebuild("settings"))
            self.after(80, self._apply_rounded_corners)

    def wipe(self):
        if messagebox.askyesno("Удалить", "Удалить все данные лаунчера?\n\n"
                                          "config.json, users.json и .key будут сохранены."):
            for child in ROOT.iterdir():
                if child.name in ("config.json", "fonts", "users.json", ".key"):
                    continue
                if child.is_dir():
                    shutil.rmtree(child, ignore_errors=True)
                else:
                    child.unlink(missing_ok=True)
            self.cfg["profiles"] = {}
            ensure_profiles(self.cfg)
            self.save_cfg()
            self.rebuild("settings")
            messagebox.showinfo("Готово", "Очищено")

    def on_close(self):
        try:
            if os.name == "nt":
                hwnd = ctypes.windll.user32.GetParent(self.winfo_id()) or self.winfo_id()
                ctypes.windll.user32.SetWindowRgn(hwnd, 0, True)
        except Exception:
            pass
        try:
            self.cfg["nick"] = self.nick.get().strip() or "Player"
        except Exception:
            pass
        self.save_cfg()
        self.destroy()


# ====================================================================
#  Запуск
# ====================================================================
if __name__ == "__main__":
    ROOT.mkdir(parents=True, exist_ok=True)
    if not _HAS_CRYPTO:
        try:
            import tkinter.messagebox as _mb
            _mb.showwarning(
                "Nexora Launcher",
                "Не установлена библиотека cryptography.\n"
                "Локальные пароли и токен Ely.by не будут зашифрованы.\n\n"
                "Установи: pip install cryptography"
            )
        except Exception:
            pass

    conf = load_config()
    set_theme(conf)
    init_fonts(conf)
    ctk.set_widget_scaling(conf["scale"] / 100)
    ctk.set_window_scaling(conf["scale"] / 100)

    if not conf.get("setup_done"):
        welcome = WelcomeSetup(conf)
        welcome.mainloop()
        if not getattr(welcome, "_finished", False):
            sys.exit(0)
        conf = load_config()
        set_theme(conf)

    App(conf).mainloop()
