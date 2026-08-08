import asyncio
import html
import json
import logging
import os
import platform
import secrets
import socket
import subprocess
import time
import urllib.request
from collections import Counter
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

import docker
import psutil
from docker.errors import DockerException, NotFound
from telegram import BotCommand, InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.constants import ParseMode
from telegram.error import BadRequest, TelegramError
from telegram.ext import (
    Application,
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    Defaults,
)

# ============================================================
# Pi Assistant Loruv V3
# Raspberry Pi + Docker Telegram yönetim botu
# ============================================================
#
# Tasarım ilkeleri:
# - Bot sadece ALLOWED_USER_ID kullanıcısına cevap verir.
# - Docker işlemleri Docker SDK üzerinden yapılır.
# - Host reboot/shutdown gibi kritik işlemler, rastgele shell yerine
#   yalnızca allowlist içindeki SSH komutları üzerinden çalışır.
# - Kritik işlemler tek kullanımlık ve süreli onay anahtarı ister.
# - Ağ/psutil/Docker gibi bloklayıcı işler asyncio.to_thread ile
#   event-loop dışında çalıştırılır.
# - Bot hiçbir ekranda container environment değişkenlerini göstermez;
#   böylece token/parola gibi sırların Telegram'a sızması önlenir.
# ============================================================


# ------------------------------------------------------------
# Zorunlu ayarlar
# ------------------------------------------------------------
BOT_TOKEN = os.environ["BOT_TOKEN"]
ALLOWED_USER_ID = int(os.environ["ALLOWED_USER_ID"])


# ------------------------------------------------------------
# İzleme eşikleri
# ------------------------------------------------------------
CHECK_INTERVAL = int(os.getenv("CHECK_INTERVAL", "60"))
CPU_LIMIT = float(os.getenv("CPU_LIMIT", "90"))
RAM_LIMIT = float(os.getenv("RAM_LIMIT", "90"))
DISK_LIMIT = float(os.getenv("DISK_LIMIT", "90"))
TEMP_LIMIT = float(os.getenv("TEMP_LIMIT", "75"))
SWAP_LIMIT = float(os.getenv("SWAP_LIMIT", "80"))

# 0 ise load alarmı kapalıdır. Örneğin 8 thread'li Pi için 8 veya 10
# gibi bir değer verilebilir.
LOAD_LIMIT = float(os.getenv("LOAD_LIMIT", "0"))

PUBLIC_IP_CHECK_URL = os.getenv(
    "PUBLIC_IP_CHECK_URL",
    "https://api.ipify.org",
)
PUBLIC_IP_TIMEOUT = float(os.getenv("PUBLIC_IP_TIMEOUT", "5"))

SELF_CONTAINER_NAME = os.getenv("SELF_CONTAINER_NAME", "pi-assistant-loruv")


# ------------------------------------------------------------
# Host mount noktaları
# ------------------------------------------------------------
# docker-compose.yml içinde tipik olarak:
#   - /:/host/root:ro
#   - /sys:/host/sys:ro
#   - pid: host
#   - network_mode: host
HOST_ROOT = Path(os.getenv("HOST_ROOT", "/host/root"))
HOST_SYS = Path(os.getenv("HOST_SYS", "/host/sys"))
STATE_DIR = Path(os.getenv("STATE_DIR", "/app/data"))
STATE_DIR.mkdir(parents=True, exist_ok=True)


# ------------------------------------------------------------
# Host kontrolü - opsiyonel ve allowlist tabanlı SSH
# ------------------------------------------------------------
HOST_CONTROL_ENABLED = os.getenv("HOST_CONTROL_ENABLED", "false").lower() == "true"
HOST_SSH_TARGET = os.getenv("HOST_SSH_TARGET", "piassistant@127.0.0.1")
HOST_SSH_KEY = os.getenv("HOST_SSH_KEY", "/run/secrets/host_ssh_key")
HOST_KNOWN_HOSTS = os.getenv("HOST_KNOWN_HOSTS", "/run/secrets/known_hosts")


# ------------------------------------------------------------
# Arayüz / liste ayarları
# ------------------------------------------------------------
DOCKER_PAGE_SIZE = int(os.getenv("DOCKER_PAGE_SIZE", "7"))
PROCESS_PAGE_SIZE = int(os.getenv("PROCESS_PAGE_SIZE", "7"))
DOCKER_LOG_LINES = int(os.getenv("DOCKER_LOG_LINES", "100"))
MAX_MESSAGE = 3900

# Kritik işlem onayı kaç saniye geçerli olsun?
CONFIRM_TTL = int(os.getenv("CONFIRM_TTL", "45"))


# ------------------------------------------------------------
# Loglama
# ------------------------------------------------------------
logging.basicConfig(
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    level=os.getenv("LOG_LEVEL", "INFO").upper(),
)
logger = logging.getLogger("pi-assistant-loruv-v3")


# ------------------------------------------------------------
# Docker bağlantısı
# ------------------------------------------------------------
try:
    docker_client = docker.from_env()
    docker_client.ping()
except DockerException as exc:
    logger.error("Docker bağlantısı kurulamadı: %s", exc)
    docker_client = None


# ------------------------------------------------------------
# Runtime durumları
# ------------------------------------------------------------
alert_state: dict[str, bool] = {
    "cpu": False,
    "ram": False,
    "disk": False,
    "temp": False,
    "swap": False,
    "load": False,
    "internet": False,
}

docker_monitor_state: dict[str, dict[str, Any]] = {}

# token -> {kind, target, back, expires}
confirmation_tokens: dict[str, dict[str, Any]] = {}


# ============================================================
# GENEL YARDIMCILAR
# ============================================================


def clip(text: str, limit: int = MAX_MESSAGE) -> str:
    """Telegram mesaj limitine yaklaşan metni güvenli biçimde kısaltır."""
    if len(text) <= limit:
        return text
    return text[: max(0, limit - 90)] + "\n\n… çıktı kısaltıldı."



def fmt_bytes(value: float | int) -> str:
    """Byte değerini okunabilir forma çevirir."""
    units = ("B", "KB", "MB", "GB", "TB", "PB")
    number = float(value)
    for unit in units:
        if abs(number) < 1024.0 or unit == units[-1]:
            return f"{number:.2f} {unit}"
        number /= 1024.0
    return f"{number:.2f} PB"



def fmt_seconds(seconds: float | int) -> str:
    """Saniyeyi kısa Türkçe süreye çevirir."""
    seconds = max(0, int(seconds))
    days, seconds = divmod(seconds, 86400)
    hours, seconds = divmod(seconds, 3600)
    minutes, seconds = divmod(seconds, 60)

    parts: list[str] = []
    if days:
        parts.append(f"{days} gün")
    if hours or days:
        parts.append(f"{hours} sa")
    if minutes or hours or days:
        parts.append(f"{minutes} dk")
    if not parts:
        parts.append(f"{seconds} sn")
    return " ".join(parts)



def read_text(path: Path, default: str = "") -> str:
    """Dosyayı hata vermeden okur."""
    try:
        return path.read_text(errors="ignore").replace("\x00", "").strip()
    except OSError:
        return default



def host_path(relative: str) -> Path:
    """Host root mount'u altında gerçek host yolunu üretir."""
    return HOST_ROOT / relative.lstrip("/")



def host_hostname() -> str:
    value = read_text(host_path("/etc/hostname"))
    return value or socket.gethostname()



def raspberry_model() -> str:
    candidates = [
        HOST_SYS / "firmware/devicetree/base/model",
        Path("/sys/firmware/devicetree/base/model"),
    ]
    for path in candidates:
        value = read_text(path)
        if value:
            return value
    return "Bilinmiyor"



def os_pretty_name() -> str:
    """Host işletim sistemi adını /etc/os-release üzerinden okur."""
    raw = read_text(host_path("/etc/os-release"))
    if not raw:
        return "Bilinmiyor"

    values: dict[str, str] = {}
    for line in raw.splitlines():
        if "=" not in line:
            continue
        key, value = line.split("=", 1)
        values[key] = value.strip().strip('"')
    return values.get("PRETTY_NAME", values.get("NAME", "Bilinmiyor"))



def cpu_temp() -> Optional[float]:
    """Raspberry Pi CPU sıcaklığını sysfs üzerinden okur."""
    candidates = [
        HOST_SYS / "class/thermal/thermal_zone0/temp",
        Path("/sys/class/thermal/thermal_zone0/temp"),
    ]
    for path in candidates:
        try:
            return int(path.read_text().strip()) / 1000
        except (OSError, ValueError):
            continue
    return None



def boot_time_text() -> str:
    try:
        return datetime.fromtimestamp(psutil.boot_time()).strftime("%d.%m.%Y %H:%M:%S")
    except Exception:
        return "Okunamadı"



def uptime_text() -> str:
    return fmt_seconds(time.time() - psutil.boot_time())



def local_ip() -> str:
    """Varsayılan rota üzerinden cihazın ana IPv4 adresini bulur."""
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        sock.connect(("1.1.1.1", 80))
        return sock.getsockname()[0]
    except OSError:
        return "Bulunamadı"
    finally:
        sock.close()



def read_public_ip() -> Optional[str]:
    """Dış/genel IP adresini ipify benzeri bir servisten okur."""
    try:
        request = urllib.request.Request(
            PUBLIC_IP_CHECK_URL,
            headers={"User-Agent": "Pi-Assistant-Loruv/3.0"},
        )
        with urllib.request.urlopen(request, timeout=PUBLIC_IP_TIMEOUT) as response:
            value = response.read().decode().strip()
            return value or None
    except Exception:
        return None



def internet_latency_ms() -> Optional[float]:
    """
    ICMP ping gerektirmeden TCP bağlantı süresini ölçer.
    Container image'ında ping binary'si olmasa da çalışır.
    """
    started = time.perf_counter()
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.settimeout(3.0)
    try:
        sock.connect(("1.1.1.1", 443))
        return (time.perf_counter() - started) * 1000
    except OSError:
        return None
    finally:
        sock.close()



def dns_servers() -> list[str]:
    """Host resolv.conf içindeki DNS sunucularını döndürür."""
    raw = read_text(host_path("/etc/resolv.conf"))
    result: list[str] = []
    for line in raw.splitlines():
        line = line.strip()
        if line.startswith("nameserver "):
            value = line.split(None, 1)[1].strip()
            if value and value not in result:
                result.append(value)
    return result[:5]



def load_alerts_enabled() -> bool:
    path = STATE_DIR / "alerts_enabled.json"
    try:
        return bool(json.loads(path.read_text()).get("enabled", True))
    except Exception:
        return True



def save_alerts_enabled(enabled: bool) -> None:
    path = STATE_DIR / "alerts_enabled.json"
    path.write_text(json.dumps({"enabled": enabled}))



def is_authorized(update: Update) -> bool:
    user = update.effective_user
    return bool(user and user.id == ALLOWED_USER_ID)


async def reject_if_unauthorized(update: Update) -> bool:
    """Yetkisiz kullanıcıların botu kullanmasını engeller."""
    if is_authorized(update):
        return False

    if update.callback_query:
        await update.callback_query.answer(
            "Bu botu kullanma yetkin yok.",
            show_alert=True,
        )
    elif update.effective_message:
        await update.effective_message.reply_text("Bu botu kullanma yetkin yok.")
    return True


async def safe_edit(
    query,
    text: str,
    reply_markup: InlineKeyboardMarkup | None = None,
) -> None:
    """Telegram'da aynı mesajı düzenler; 'not modified' hatasını yutar."""
    try:
        await query.edit_message_text(
            clip(text),
            reply_markup=reply_markup,
            parse_mode=ParseMode.HTML,
            disable_web_page_preview=True,
        )
    except BadRequest as exc:
        if "Message is not modified" not in str(exc):
            raise


# ============================================================
# KRİTİK İŞLEM ONAY SİSTEMİ
# ============================================================


def prune_confirmation_tokens() -> None:
    now = time.time()
    expired = [
        token
        for token, data in confirmation_tokens.items()
        if float(data.get("expires", 0)) < now
    ]
    for token in expired:
        confirmation_tokens.pop(token, None)



def create_confirmation(kind: str, target: str, back: str) -> str:
    """Tek kullanımlık, süreli bir onay token'ı üretir."""
    prune_confirmation_tokens()
    token = secrets.token_urlsafe(6)
    confirmation_tokens[token] = {
        "kind": kind,
        "target": target,
        "back": back,
        "expires": time.time() + CONFIRM_TTL,
    }
    return token



def consume_confirmation(token: str) -> Optional[dict[str, Any]]:
    """Token'ı bir kez tüketir; süresi dolmuşsa None döndürür."""
    prune_confirmation_tokens()
    data = confirmation_tokens.pop(token, None)
    if not data:
        return None
    if float(data.get("expires", 0)) < time.time():
        return None
    return data



def confirmation_markup(token: str, back_callback: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton("✅ Onayla", callback_data=f"cf:{token}"),
                InlineKeyboardButton("❌ Vazgeç", callback_data=back_callback),
            ]
        ]
    )


# ============================================================
# ANA MENÜLER
# ============================================================


def main_menu() -> InlineKeyboardMarkup:
    rows = [
        [
            InlineKeyboardButton("📊 Sistem", callback_data="s:overview"),
            InlineKeyboardButton("🐳 Docker", callback_data="d:menu"),
        ],
        [
            InlineKeyboardButton("🌐 Ağ", callback_data="n:overview"),
            InlineKeyboardButton("💽 Depolama", callback_data="st:overview"),
        ],
        [
            InlineKeyboardButton("⚙️ Süreçler", callback_data="p:menu"),
            InlineKeyboardButton("🩺 Sağlık", callback_data="s:health"),
        ],
        [
            InlineKeyboardButton("🔔 Uyarılar", callback_data="a:menu"),
            InlineKeyboardButton("ℹ️ Hakkında", callback_data="x:about"),
        ],
    ]

    if HOST_CONTROL_ENABLED:
        rows.append([InlineKeyboardButton("⚡ Host Yönetimi", callback_data="h:menu")])

    rows.append([InlineKeyboardButton("🔄 Ana menüyü yenile", callback_data="m:main")])
    return InlineKeyboardMarkup(rows)



def back_menu() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [[InlineKeyboardButton("⬅️ Ana menü", callback_data="m:main")]]
    )



def system_menu() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton("🧩 Donanım", callback_data="s:hardware"),
                InlineKeyboardButton("💾 Bellek", callback_data="s:memory"),
            ],
            [
                InlineKeyboardButton("🩺 Sağlık", callback_data="s:health"),
                InlineKeyboardButton("🔄 Yenile", callback_data="s:overview"),
            ],
            [InlineKeyboardButton("⬅️ Ana menü", callback_data="m:main")],
        ]
    )



def process_menu() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton("🔥 CPU'ya göre", callback_data="p:cpu:0"),
                InlineKeyboardButton("💾 RAM'e göre", callback_data="p:ram:0"),
            ],
            [
                InlineKeyboardButton("🔄 Yenile", callback_data="p:menu"),
                InlineKeyboardButton("⬅️ Ana menü", callback_data="m:main"),
            ],
        ]
    )



def docker_menu() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton("📦 Container'lar", callback_data="d:list:0"),
                InlineKeyboardButton("📊 Docker bilgi", callback_data="d:overview"),
            ],
            [
                InlineKeyboardButton("🖼 Image'lar", callback_data="d:images"),
                InlineKeyboardButton("🔄 Yenile", callback_data="d:menu"),
            ],
            [InlineKeyboardButton("⬅️ Ana menü", callback_data="m:main")],
        ]
    )


# ============================================================
# SİSTEM RAPORLARI
# ============================================================


def system_overview_sync() -> str:
    """Ana sistem raporu. Dış IP dahil."""
    cpu = psutil.cpu_percent(interval=0.40)
    ram = psutil.virtual_memory()
    swap = psutil.swap_memory()
    disk_target = str(HOST_ROOT if HOST_ROOT.exists() else Path("/"))
    disk = psutil.disk_usage(disk_target)
    temp = cpu_temp()
    freq = psutil.cpu_freq()
    load1, load5, load15 = os.getloadavg()
    net = psutil.net_io_counters()
    public_ip = read_public_ip()

    temp_text = f"{temp:.1f} °C" if temp is not None else "Okunamadı"
    freq_text = f"{freq.current / 1000:.2f} GHz" if freq else "Okunamadı"

    return (
        "<b>📊 Raspberry Pi sistem durumu</b>\n\n"
        f"🧩 <b>Model:</b> {html.escape(raspberry_model())}\n"
        f"🖥 <b>Host:</b> {html.escape(host_hostname())}\n"
        f"🐧 <b>OS:</b> {html.escape(os_pretty_name())}\n\n"
        f"🧠 <b>CPU:</b> %{cpu:.1f} • {psutil.cpu_count(logical=True)} thread\n"
        f"⚡ <b>Frekans:</b> {freq_text}\n"
        f"📈 <b>Load:</b> {load1:.2f} / {load5:.2f} / {load15:.2f}\n"
        f"🌡 <b>Sıcaklık:</b> {temp_text}\n\n"
        f"💾 <b>RAM:</b> %{ram.percent:.1f} • "
        f"{fmt_bytes(ram.used)} / {fmt_bytes(ram.total)}\n"
        f"🔁 <b>Swap:</b> %{swap.percent:.1f} • "
        f"{fmt_bytes(swap.used)} / {fmt_bytes(swap.total)}\n"
        f"🗄 <b>Disk:</b> %{disk.percent:.1f} • "
        f"{fmt_bytes(disk.used)} / {fmt_bytes(disk.total)}\n\n"
        f"⬆️ <b>Toplam gönderilen:</b> {fmt_bytes(net.bytes_sent)}\n"
        f"⬇️ <b>Toplam alınan:</b> {fmt_bytes(net.bytes_recv)}\n"
        f"🏠 <b>Yerel IP:</b> <code>{html.escape(local_ip())}</code>\n"
        f"🌍 <b>Dış IP:</b> <code>{html.escape(public_ip or 'Okunamadı')}</code>\n\n"
        f"🚀 <b>Boot:</b> {boot_time_text()}\n"
        f"⏱ <b>Uptime:</b> {uptime_text()}"
    )



def hardware_report_sync() -> str:
    """CPU/donanım ve kernel bilgilerini gösterir."""
    freq = psutil.cpu_freq()
    physical = psutil.cpu_count(logical=False)
    logical = psutil.cpu_count(logical=True)
    temp = cpu_temp()

    freq_line = "Okunamadı"
    if freq:
        current = freq.current / 1000
        min_f = freq.min / 1000 if freq.min else 0
        max_f = freq.max / 1000 if freq.max else 0
        freq_line = f"{current:.2f} GHz"
        if min_f or max_f:
            freq_line += f" (min {min_f:.2f} / max {max_f:.2f})"

    cpu_times = psutil.cpu_times_percent(interval=0.35)
    iowait = getattr(cpu_times, "iowait", 0.0)

    return (
        "<b>🧩 Donanım ve sistem</b>\n\n"
        f"📟 <b>Model:</b> {html.escape(raspberry_model())}\n"
        f"🧱 <b>Mimari:</b> {html.escape(platform.machine())}\n"
        f"🐍 <b>Python:</b> {html.escape(platform.python_version())}\n"
        f"🐧 <b>Kernel:</b> {html.escape(platform.release())}\n"
        f"💿 <b>OS:</b> {html.escape(os_pretty_name())}\n\n"
        f"🧠 <b>Fiziksel çekirdek:</b> {physical or 'Bilinmiyor'}\n"
        f"🧵 <b>Thread:</b> {logical or 'Bilinmiyor'}\n"
        f"⚡ <b>CPU frekansı:</b> {freq_line}\n"
        f"🌡 <b>CPU sıcaklığı:</b> "
        f"{f'{temp:.1f} °C' if temp is not None else 'Okunamadı'}\n\n"
        f"👤 <b>CPU user:</b> %{getattr(cpu_times, 'user', 0.0):.1f}\n"
        f"⚙️ <b>CPU system:</b> %{getattr(cpu_times, 'system', 0.0):.1f}\n"
        f"🕒 <b>I/O wait:</b> %{iowait:.1f}\n"
        f"💤 <b>Idle:</b> %{getattr(cpu_times, 'idle', 0.0):.1f}"
    )



def memory_report_sync() -> str:
    """RAM ve swap ayrıntıları."""
    mem = psutil.virtual_memory()
    swap = psutil.swap_memory()

    cached = getattr(mem, "cached", 0)
    buffers = getattr(mem, "buffers", 0)
    shared = getattr(mem, "shared", 0)

    return (
        "<b>💾 Bellek ayrıntıları</b>\n\n"
        f"📦 <b>Toplam RAM:</b> {fmt_bytes(mem.total)}\n"
        f"✅ <b>Kullanılabilir:</b> {fmt_bytes(mem.available)}\n"
        f"📈 <b>Kullanılan:</b> {fmt_bytes(mem.used)} (%{mem.percent:.1f})\n"
        f"🧊 <b>Cache:</b> {fmt_bytes(cached)}\n"
        f"🧱 <b>Buffer:</b> {fmt_bytes(buffers)}\n"
        f"🔗 <b>Shared:</b> {fmt_bytes(shared)}\n\n"
        f"🔁 <b>Swap toplam:</b> {fmt_bytes(swap.total)}\n"
        f"🔁 <b>Swap kullanılan:</b> {fmt_bytes(swap.used)} (%{swap.percent:.1f})\n"
        f"⬅️ <b>Swap in:</b> {fmt_bytes(swap.sin)}\n"
        f"➡️ <b>Swap out:</b> {fmt_bytes(swap.sout)}"
    )



def storage_report_sync() -> str:
    """Host root, /srv/docker ve disk I/O bilgilerini gösterir."""
    root_target = HOST_ROOT if HOST_ROOT.exists() else Path("/")
    root = psutil.disk_usage(str(root_target))
    io = psutil.disk_io_counters()

    lines = [
        "<b>💽 Depolama</b>",
        "",
        "<b>Host root (/)</b>",
        f"📦 Toplam: {fmt_bytes(root.total)}",
        f"📁 Kullanılan: {fmt_bytes(root.used)} (%{root.percent:.1f})",
        f"✅ Boş: {fmt_bytes(root.free)}",
    ]

    docker_data = host_path("/srv/docker")
    if docker_data.exists():
        try:
            d = psutil.disk_usage(str(docker_data))
            lines.extend(
                [
                    "",
                    "<b>/srv/docker dosya sistemi</b>",
                    f"📦 Toplam: {fmt_bytes(d.total)}",
                    f"📁 Kullanılan: {fmt_bytes(d.used)} (%{d.percent:.1f})",
                    f"✅ Boş: {fmt_bytes(d.free)}",
                ]
            )
        except OSError:
            pass

    if io:
        busy = getattr(io, "busy_time", 0)
        lines.extend(
            [
                "",
                "<b>Disk I/O (boot'tan beri)</b>",
                f"📖 Okuma: {fmt_bytes(io.read_bytes)} • {io.read_count:,} işlem",
                f"✍️ Yazma: {fmt_bytes(io.write_bytes)} • {io.write_count:,} işlem",
                f"⏱ I/O busy: {fmt_seconds(busy / 1000) if busy else 'Bilinmiyor'}",
            ]
        )

    return "\n".join(lines)



def network_report_sync() -> str:
    """Ağ arayüzleri, paket hata/drop ve genel IP bilgisini gösterir."""
    public_ip = read_public_ip()
    latency = internet_latency_ms()
    addrs = psutil.net_if_addrs()
    stats = psutil.net_if_stats()
    counters = psutil.net_io_counters(pernic=True)

    lines = [
        "<b>🌐 Ağ durumu</b>",
        "",
        f"🏠 <b>Ana yerel IP:</b> <code>{html.escape(local_ip())}</code>",
        f"🌍 <b>Dış IP:</b> <code>{html.escape(public_ip or 'Okunamadı')}</code>",
        f"⚡ <b>İnternet TCP gecikmesi:</b> "
        f"{f'{latency:.1f} ms' if latency is not None else 'Bağlantı kurulamadı'}",
    ]

    dns = dns_servers()
    if dns:
        lines.append(f"🧭 <b>DNS:</b> {html.escape(', '.join(dns))}")

    lines.extend(["", "<b>Ağ arayüzleri</b>"])

    shown = 0
    for name in sorted(addrs):
        if name == "lo":
            continue

        ipv4 = [a.address for a in addrs[name] if a.family == socket.AF_INET]
        ipv6 = [
            a.address.split("%", 1)[0]
            for a in addrs[name]
            if a.family == socket.AF_INET6
        ]
        if not ipv4 and not ipv6:
            continue

        stat = stats.get(name)
        icon = "🟢" if stat and stat.isup else "🔴"
        speed = f" • {stat.speed} Mbps" if stat and stat.speed and stat.speed > 0 else ""
        mtu = f" • MTU {stat.mtu}" if stat and stat.mtu else ""

        lines.append(f"\n{icon} <b>{html.escape(name)}</b>{speed}{mtu}")
        if ipv4:
            lines.append(f"   IPv4: <code>{html.escape(', '.join(ipv4))}</code>")
        if ipv6:
            lines.append(f"   IPv6: <code>{html.escape(', '.join(ipv6[:2]))}</code>")

        nic = counters.get(name)
        if nic:
            lines.append(
                f"   ↕️ {fmt_bytes(nic.bytes_recv)} ↓ / {fmt_bytes(nic.bytes_sent)} ↑"
            )
            lines.append(
                f"   📦 {nic.packets_recv:,} pkt ↓ / {nic.packets_sent:,} pkt ↑"
            )
            if nic.errin or nic.errout or nic.dropin or nic.dropout:
                lines.append(
                    f"   ⚠️ err {nic.errin}/{nic.errout} • drop {nic.dropin}/{nic.dropout}"
                )

        shown += 1
        if shown >= 12:
            break

    if shown == 0:
        lines.append("Arayüz bilgisi bulunamadı.")

    return clip("\n".join(lines))



def system_health_sync() -> str:
    """Eşiklere göre hızlı sağlık özeti üretir."""
    cpu = psutil.cpu_percent(interval=0.40)
    ram = psutil.virtual_memory().percent
    swap = psutil.swap_memory().percent
    disk_target = str(HOST_ROOT if HOST_ROOT.exists() else Path("/"))
    disk = psutil.disk_usage(disk_target).percent
    temp = cpu_temp()
    load1, _, _ = os.getloadavg()
    public_ip = read_public_ip()

    def mark(ok: bool) -> str:
        return "🟢" if ok else "🔴"

    docker_ok = False
    if docker_client is not None:
        try:
            docker_ok = bool(docker_client.ping())
        except DockerException:
            docker_ok = False

    temp_ok = temp is None or temp < TEMP_LIMIT
    load_ok = LOAD_LIMIT <= 0 or load1 < LOAD_LIMIT

    lines = [
        "<b>🩺 Sistem sağlık özeti</b>",
        "",
        f"{mark(cpu < CPU_LIMIT)} CPU %{cpu:.1f} / limit %{CPU_LIMIT:g}",
        f"{mark(ram < RAM_LIMIT)} RAM %{ram:.1f} / limit %{RAM_LIMIT:g}",
        f"{mark(disk < DISK_LIMIT)} Disk %{disk:.1f} / limit %{DISK_LIMIT:g}",
        f"{mark(swap < SWAP_LIMIT)} Swap %{swap:.1f} / limit %{SWAP_LIMIT:g}",
        f"{mark(temp_ok)} Sıcaklık "
        f"{f'{temp:.1f} °C' if temp is not None else 'okunamadı'} / limit {TEMP_LIMIT:g} °C",
        f"{mark(load_ok)} Load 1m {load1:.2f}"
        + (f" / limit {LOAD_LIMIT:g}" if LOAD_LIMIT > 0 else " / alarm kapalı"),
        f"{mark(public_ip is not None)} İnternet / dış IP",
        f"{mark(docker_ok)} Docker daemon",
        "",
        f"⏱ Uptime: {uptime_text()}",
    ]

    return "\n".join(lines)


# ============================================================
# SÜREÇ / PROCESS YÖNETİMİ
# ============================================================


def collect_processes_sync() -> tuple[list[dict[str, Any]], Counter]:
    """
    Host PID namespace'ındaki süreçleri örnekler.
    CPU yüzdesi için iki ölçüm arasında kısa bekleme gerekir.
    """
    sampled: list[psutil.Process] = []

    for proc in psutil.process_iter(["pid", "name", "status"]):
        try:
            proc.cpu_percent(None)
            sampled.append(proc)
        except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
            continue

    time.sleep(0.35)

    rows: list[dict[str, Any]] = []
    statuses: Counter = Counter()

    for proc in sampled:
        try:
            with proc.oneshot():
                status = proc.status()
                statuses[status] += 1
                rows.append(
                    {
                        "pid": proc.pid,
                        "ppid": proc.ppid(),
                        "name": proc.name() or "?",
                        "username": proc.username() or "?",
                        "status": status,
                        "cpu": proc.cpu_percent(None),
                        "ram": proc.memory_percent(),
                        "rss": proc.memory_info().rss,
                        "threads": proc.num_threads(),
                        "created": proc.create_time(),
                    }
                )
        except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
            continue

    return rows, statuses



def process_summary_sync() -> str:
    """Süreç ekranının ayrıntılı genel özeti."""
    rows, statuses = collect_processes_sync()

    total_threads = sum(int(row["threads"]) for row in rows)
    total_rss = sum(int(row["rss"]) for row in rows)
    running = statuses.get(psutil.STATUS_RUNNING, 0)
    sleeping = statuses.get(psutil.STATUS_SLEEPING, 0)
    zombie = statuses.get(psutil.STATUS_ZOMBIE, 0)

    top_cpu = sorted(rows, key=lambda x: x["cpu"], reverse=True)[:5]
    top_ram = sorted(rows, key=lambda x: x["rss"], reverse=True)[:5]

    lines = [
        "<b>⚙️ Host süreçleri</b>",
        "",
        f"📦 <b>Toplam süreç:</b> {len(rows)}",
        f"🧵 <b>Toplam thread:</b> {total_threads:,}",
        f"🏃 <b>Running:</b> {running}",
        f"💤 <b>Sleeping:</b> {sleeping}",
        f"🧟 <b>Zombie:</b> {zombie}",
        f"💾 <b>Toplam RSS:</b> {fmt_bytes(total_rss)}",
        "",
        "<b>🔥 En yüksek CPU</b>",
    ]

    for row in top_cpu:
        lines.append(
            f"<code>{row['pid']:>6}</code> • {row['cpu']:>5.1f}% • "
            f"{html.escape(str(row['name'])[:28])}"
        )

    lines.extend(["", "<b>💾 En yüksek RAM</b>"])
    for row in top_ram:
        lines.append(
            f"<code>{row['pid']:>6}</code> • {fmt_bytes(row['rss']):>9} • "
            f"{html.escape(str(row['name'])[:28])}"
        )

    return "\n".join(lines)



def process_list_sync(
    sort_by: str,
    page: int,
) -> tuple[str, list[int], int]:
    """CPU veya RAM'e göre sayfalı süreç listesi oluşturur."""
    rows, _ = collect_processes_sync()

    if sort_by == "ram":
        rows.sort(key=lambda x: (x["rss"], x["ram"]), reverse=True)
        title = "💾 RAM'e göre süreçler"
    else:
        rows.sort(key=lambda x: x["cpu"], reverse=True)
        title = "🔥 CPU'ya göre süreçler"
        sort_by = "cpu"

    total_pages = max(1, (len(rows) + PROCESS_PAGE_SIZE - 1) // PROCESS_PAGE_SIZE)
    page = max(0, min(page, total_pages - 1))
    start = page * PROCESS_PAGE_SIZE
    items = rows[start : start + PROCESS_PAGE_SIZE]

    lines = [f"<b>{title}</b>", "", f"Sayfa {page + 1}/{total_pages}"]
    pids: list[int] = []

    for row in items:
        pids.append(int(row["pid"]))
        lines.extend(
            [
                "",
                f"<b>{html.escape(str(row['name'])[:35])}</b>",
                f"PID <code>{row['pid']}</code> • PPID {row['ppid']} • {html.escape(str(row['status']))}",
                f"🧠 CPU %{row['cpu']:.1f} • 💾 RAM %{row['ram']:.2f} ({fmt_bytes(row['rss'])})",
                f"🧵 {row['threads']} thread • 👤 {html.escape(str(row['username'])[:30])}",
            ]
        )

    return clip("\n".join(lines)), pids, total_pages



def process_list_markup(
    sort_by: str,
    page: int,
    pids: list[int],
    total_pages: int,
) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = []

    # Her süreç için PID detay butonu.
    for pid in pids:
        rows.append(
            [InlineKeyboardButton(f"🔎 PID {pid}", callback_data=f"p:view:{pid}")]
        )

    nav: list[InlineKeyboardButton] = []
    if page > 0:
        nav.append(
            InlineKeyboardButton("◀️", callback_data=f"p:{sort_by}:{page - 1}")
        )
    nav.append(
        InlineKeyboardButton(
            f"{page + 1}/{total_pages}",
            callback_data=f"p:{sort_by}:{page}",
        )
    )
    if page < total_pages - 1:
        nav.append(
            InlineKeyboardButton("▶️", callback_data=f"p:{sort_by}:{page + 1}")
        )
    rows.append(nav)

    rows.append(
        [
            InlineKeyboardButton("⚙️ Süreç özeti", callback_data="p:menu"),
            InlineKeyboardButton("⬅️ Ana menü", callback_data="m:main"),
        ]
    )
    return InlineKeyboardMarkup(rows)



def process_detail_sync(pid: int) -> str:
    """Tek bir PID için mümkün olduğunca ayrıntılı fakat güvenli rapor."""
    proc = psutil.Process(pid)

    try:
        proc.cpu_percent(None)
        time.sleep(0.25)

        with proc.oneshot():
            name = proc.name() or "?"
            status = proc.status()
            username = proc.username() or "?"
            ppid = proc.ppid()
            cpu = proc.cpu_percent(None)
            mem_percent = proc.memory_percent()
            mem = proc.memory_info()
            threads = proc.num_threads()
            created = proc.create_time()
            cmdline = " ".join(proc.cmdline()) or "(yok)"
            cwd = ""
            try:
                cwd = proc.cwd()
            except (psutil.AccessDenied, FileNotFoundError, OSError):
                cwd = "Erişim yok"

        io_text = "Erişim yok"
        try:
            io = proc.io_counters()
            io_text = f"{fmt_bytes(io.read_bytes)} oku / {fmt_bytes(io.write_bytes)} yaz"
        except (psutil.AccessDenied, psutil.NoSuchProcess, AttributeError):
            pass

        open_files_text = "Erişim yok"
        try:
            open_files_text = str(len(proc.open_files()))
        except (psutil.AccessDenied, psutil.NoSuchProcess):
            pass

        conn_text = "Erişim yok"
        try:
            conn_text = str(len(proc.net_connections(kind="inet")))
        except (psutil.AccessDenied, psutil.NoSuchProcess, AttributeError):
            pass

        started = datetime.fromtimestamp(created).strftime("%d.%m.%Y %H:%M:%S")
        age = fmt_seconds(time.time() - created)

        return clip(
            "<b>🔎 Süreç ayrıntısı</b>\n\n"
            f"⚙️ <b>Ad:</b> {html.escape(name)}\n"
            f"🆔 <b>PID:</b> <code>{pid}</code>\n"
            f"↩️ <b>PPID:</b> {ppid}\n"
            f"👤 <b>Kullanıcı:</b> {html.escape(username)}\n"
            f"📌 <b>Durum:</b> {html.escape(status)}\n\n"
            f"🧠 <b>CPU:</b> %{cpu:.1f}\n"
            f"💾 <b>RAM:</b> %{mem_percent:.2f} • RSS {fmt_bytes(mem.rss)} • VMS {fmt_bytes(mem.vms)}\n"
            f"🧵 <b>Thread:</b> {threads}\n"
            f"💽 <b>Process I/O:</b> {io_text}\n"
            f"📂 <b>Açık dosya:</b> {open_files_text}\n"
            f"🌐 <b>INET bağlantısı:</b> {conn_text}\n\n"
            f"🚀 <b>Başlangıç:</b> {started}\n"
            f"⏱ <b>Çalışma süresi:</b> {age}\n"
            f"📍 <b>CWD:</b> <code>{html.escape(cwd[:250])}</code>\n\n"
            f"⌨️ <b>Komut:</b>\n<code>{html.escape(cmdline[:900])}</code>"
        )

    except psutil.NoSuchProcess as exc:
        raise RuntimeError("Süreç artık çalışmıyor.") from exc
    except psutil.AccessDenied as exc:
        raise RuntimeError("Bu sürecin ayrıntılarına erişim yok.") from exc


# ============================================================
# DOCKER
# ============================================================


def docker_required() -> None:
    if docker_client is None:
        raise DockerException("Docker daemon bağlantısı yok.")



def docker_overview_sync() -> str:
    """Docker daemon genel bilgileri."""
    docker_required()
    info = docker_client.info()
    version = docker_client.version()

    return (
        "<b>📊 Docker daemon</b>\n\n"
        f"🐳 <b>Docker:</b> {html.escape(str(version.get('Version', '?')))}\n"
        f"🔌 <b>API:</b> {html.escape(str(version.get('ApiVersion', '?')))}\n"
        f"🐧 <b>OS:</b> {html.escape(str(info.get('OperatingSystem', '?')))}\n"
        f"🧱 <b>Kernel:</b> {html.escape(str(info.get('KernelVersion', '?')))}\n"
        f"🗂 <b>Storage driver:</b> {html.escape(str(info.get('Driver', '?')))}\n"
        f"📍 <b>Docker root:</b> <code>{html.escape(str(info.get('DockerRootDir', '?')))}</code>\n\n"
        f"📦 <b>Container:</b> {info.get('Containers', 0)}\n"
        f"🟢 <b>Running:</b> {info.get('ContainersRunning', 0)}\n"
        f"🟡 <b>Paused:</b> {info.get('ContainersPaused', 0)}\n"
        f"🔴 <b>Stopped:</b> {info.get('ContainersStopped', 0)}\n"
        f"🖼 <b>Image:</b> {info.get('Images', 0)}\n\n"
        f"🧠 <b>Docker CPU:</b> {info.get('NCPU', '?')}\n"
        f"💾 <b>Docker RAM:</b> {fmt_bytes(info.get('MemTotal', 0))}"
    )



def list_containers_sync() -> list[dict[str, str]]:
    docker_required()
    result: list[dict[str, str]] = []

    for container in docker_client.containers.list(all=True):
        container.reload()
        state = container.attrs.get("State", {})
        health = state.get("Health", {}).get("Status", "")
        result.append(
            {
                "id": container.id[:12],
                "name": container.name,
                "status": container.status,
                "health": health,
                "image": (
                    container.image.tags[0]
                    if container.image.tags
                    else container.image.short_id
                ),
            }
        )

    result.sort(key=lambda x: (x["status"] != "running", x["name"].lower()))
    return result



def docker_list_markup(
    containers: list[dict[str, str]],
    page: int,
) -> InlineKeyboardMarkup:
    total_pages = max(1, (len(containers) + DOCKER_PAGE_SIZE - 1) // DOCKER_PAGE_SIZE)
    page = max(0, min(page, total_pages - 1))
    start = page * DOCKER_PAGE_SIZE
    page_items = containers[start : start + DOCKER_PAGE_SIZE]

    rows: list[list[InlineKeyboardButton]] = []

    for item in page_items:
        if item["status"] == "running":
            icon = "🟢"
        elif item["status"] == "paused":
            icon = "🟡"
        else:
            icon = "🔴"

        if item["health"] == "unhealthy":
            icon = "🩺"

        rows.append(
            [
                InlineKeyboardButton(
                    f"{icon} {item['name'][:38]}",
                    callback_data=f"d:view:{item['id']}",
                )
            ]
        )

    nav: list[InlineKeyboardButton] = []
    if page > 0:
        nav.append(InlineKeyboardButton("◀️", callback_data=f"d:list:{page - 1}"))
    nav.append(
        InlineKeyboardButton(
            f"{page + 1}/{total_pages}",
            callback_data=f"d:list:{page}",
        )
    )
    if page < total_pages - 1:
        nav.append(InlineKeyboardButton("▶️", callback_data=f"d:list:{page + 1}"))
    rows.append(nav)

    rows.append(
        [
            InlineKeyboardButton("🔄 Yenile", callback_data=f"d:list:{page}"),
            InlineKeyboardButton("⬅️ Docker", callback_data="d:menu"),
        ]
    )
    return InlineKeyboardMarkup(rows)



def container_details_sync(container_id: str) -> tuple[str, str, str]:
    """Container ayrıntıları; environment değişkenleri özellikle gösterilmez."""
    docker_required()
    c = docker_client.containers.get(container_id)
    c.reload()

    attrs = c.attrs
    state = attrs.get("State", {})
    config = attrs.get("Config", {})
    network = attrs.get("NetworkSettings", {})
    host_config = attrs.get("HostConfig", {})

    health = state.get("Health", {}).get("Status", "yok")
    restart_count = attrs.get("RestartCount", 0)
    restart_policy = host_config.get("RestartPolicy", {}).get("Name", "no")
    image = config.get("Image") or (
        c.image.tags[0] if c.image.tags else c.image.short_id
    )

    ports: list[str] = []
    for port, bindings in (network.get("Ports") or {}).items():
        if not bindings:
            ports.append(port)
            continue
        for bind in bindings:
            ports.append(
                f"{bind.get('HostIp', '')}:{bind.get('HostPort', '')} → {port}"
            )

    ips: list[str] = []
    for net_name, data in (network.get("Networks") or {}).items():
        ip_addr = data.get("IPAddress")
        if ip_addr:
            ips.append(f"{net_name}: {ip_addr}")

    mounts: list[str] = []
    for mount in attrs.get("Mounts") or []:
        source = mount.get("Source", "?")
        destination = mount.get("Destination", "?")
        mode = "rw" if mount.get("RW") else "ro"
        mounts.append(f"{source} → {destination} ({mode})")

    pid = state.get("Pid", 0)
    exit_code = state.get("ExitCode", 0)
    oom = bool(state.get("OOMKilled", False))

    memory_limit = int(host_config.get("Memory") or 0)
    nano_cpus = int(host_config.get("NanoCpus") or 0)
    cpu_limit = nano_cpus / 1_000_000_000 if nano_cpus else 0

    text = (
        f"<b>🐳 {html.escape(c.name)}</b>\n\n"
        f"📌 <b>Durum:</b> {html.escape(c.status)}\n"
        f"🩺 <b>Health:</b> {html.escape(health)}\n"
        f"🆔 <b>ID:</b> <code>{c.id[:12]}</code>\n"
        f"🧠 <b>Host PID:</b> {pid or '-'}\n"
        f"🖼 <b>Image:</b> <code>{html.escape(str(image))}</code>\n"
        f"🔁 <b>Restart sayısı:</b> {restart_count}\n"
        f"♻️ <b>Restart policy:</b> {html.escape(str(restart_policy))}\n"
        f"🚀 <b>Başlangıç:</b> {html.escape(str(state.get('StartedAt', '-'))[:19])}\n"
        f"🚪 <b>Exit code:</b> {exit_code}\n"
        f"💥 <b>OOM killed:</b> {'Evet' if oom else 'Hayır'}\n"
    )

    limits: list[str] = []
    if memory_limit > 0:
        limits.append(f"RAM {fmt_bytes(memory_limit)}")
    if cpu_limit > 0:
        limits.append(f"CPU {cpu_limit:g}")
    if limits:
        text += f"🎚 <b>Limit:</b> {html.escape(' • '.join(limits))}\n"

    if ports:
        text += "\n<b>🔌 Portlar</b>\n" + "\n".join(
            f"• {html.escape(port)}" for port in ports[:12]
        )

    if ips:
        text += "\n\n<b>🌐 Container IP</b>\n" + "\n".join(
            f"• {html.escape(value)}" for value in ips[:8]
        )

    if mounts:
        text += "\n\n<b>📁 Mount'lar</b>\n" + "\n".join(
            f"• {html.escape(value[:240])}" for value in mounts[:8]
        )

    return c.id[:12], c.status, clip(text)



def container_stats_sync(container_id: str) -> str:
    docker_required()
    c = docker_client.containers.get(container_id)
    stats = c.stats(stream=False)

    cpu_stats = stats.get("cpu_stats", {})
    pre_cpu = stats.get("precpu_stats", {})
    cpu_delta = (
        cpu_stats.get("cpu_usage", {}).get("total_usage", 0)
        - pre_cpu.get("cpu_usage", {}).get("total_usage", 0)
    )
    system_delta = (
        cpu_stats.get("system_cpu_usage", 0)
        - pre_cpu.get("system_cpu_usage", 0)
    )
    online_cpus = (
        cpu_stats.get("online_cpus")
        or len(cpu_stats.get("cpu_usage", {}).get("percpu_usage") or [])
        or 1
    )

    cpu_percent = (
        (cpu_delta / system_delta) * online_cpus * 100
        if system_delta > 0 and cpu_delta >= 0
        else 0.0
    )

    memory = stats.get("memory_stats", {})
    mem_usage = float(memory.get("usage", 0))
    mem_limit = float(memory.get("limit", 0))
    cache = float(
        memory.get("stats", {}).get(
            "inactive_file",
            memory.get("stats", {}).get("cache", 0),
        )
    )
    mem_effective = max(0.0, mem_usage - cache)
    mem_percent = (mem_effective / mem_limit * 100) if mem_limit else 0.0

    rx = tx = 0
    for net in (stats.get("networks") or {}).values():
        rx += int(net.get("rx_bytes", 0))
        tx += int(net.get("tx_bytes", 0))

    block_read = block_write = 0
    for row in stats.get("blkio_stats", {}).get("io_service_bytes_recursive") or []:
        op = str(row.get("op", "")).lower()
        value = int(row.get("value", 0))
        if op == "read":
            block_read += value
        elif op == "write":
            block_write += value

    pids = int(stats.get("pids_stats", {}).get("current", 0))

    return (
        f"<b>📈 {html.escape(c.name)} istatistikleri</b>\n\n"
        f"🧠 <b>CPU:</b> %{cpu_percent:.1f}\n"
        f"💾 <b>RAM:</b> %{mem_percent:.1f} • "
        f"{fmt_bytes(mem_effective)} / {fmt_bytes(mem_limit)}\n"
        f"🧵 <b>PID sayısı:</b> {pids}\n"
        f"🌐 <b>Ağ:</b> {fmt_bytes(rx)} ↓ / {fmt_bytes(tx)} ↑\n"
        f"💽 <b>Block I/O:</b> {fmt_bytes(block_read)} oku / {fmt_bytes(block_write)} yaz"
    )



def container_logs_sync(container_id: str) -> tuple[str, str]:
    docker_required()
    c = docker_client.containers.get(container_id)
    raw = c.logs(
        tail=DOCKER_LOG_LINES,
        timestamps=True,
        stdout=True,
        stderr=True,
    )
    text = raw.decode("utf-8", errors="replace").strip() or "(log yok)"
    text = clip(text, 3050)

    return c.id[:12], (
        f"<b>📜 {html.escape(c.name)} — son {DOCKER_LOG_LINES} satır</b>\n\n"
        f"<pre>{html.escape(text)}</pre>"
    )



def container_action_sync(container_id: str, action: str) -> str:
    """Allowlist içindeki Docker yönetim işlemlerini uygular."""
    docker_required()
    c = docker_client.containers.get(container_id)

    if c.name == SELF_CONTAINER_NAME and action in {"stop", "restart", "pause"}:
        raise DockerException(
            "Bot kendi container'ını Telegram üzerinden durduramaz, "
            "yeniden başlatamaz veya pause edemez."
        )

    if action == "start":
        c.start()
    elif action == "stop":
        c.stop(timeout=15)
    elif action == "restart":
        c.restart(timeout=15)
    elif action == "pause":
        c.pause()
    elif action == "unpause":
        c.unpause()
    else:
        raise ValueError("Geçersiz Docker işlemi")

    c.reload()
    return (
        f"✅ <b>{html.escape(c.name)}</b>\n"
        f"İşlem: <b>{html.escape(action)}</b>\n"
        f"Yeni durum: <b>{html.escape(c.status)}</b>"
    )



def container_buttons(container_id: str, status: str) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = [
        [
            InlineKeyboardButton("📈 Stats", callback_data=f"d:stats:{container_id}"),
            InlineKeyboardButton("📜 Log", callback_data=f"d:logs:{container_id}"),
        ]
    ]

    if status == "running":
        rows.append(
            [
                InlineKeyboardButton("⏸ Pause", callback_data=f"d:act:pause:{container_id}"),
                InlineKeyboardButton("🔁 Restart", callback_data=f"d:act:restart:{container_id}"),
            ]
        )
        rows.append(
            [InlineKeyboardButton("⏹ Durdur", callback_data=f"d:act:stop:{container_id}")]
        )
    elif status == "paused":
        rows.append(
            [
                InlineKeyboardButton("▶️ Devam", callback_data=f"d:act:unpause:{container_id}"),
                InlineKeyboardButton("⏹ Durdur", callback_data=f"d:act:stop:{container_id}"),
            ]
        )
    else:
        rows.append(
            [InlineKeyboardButton("▶️ Başlat", callback_data=f"d:act:start:{container_id}")]
        )

    rows.append(
        [
            InlineKeyboardButton("🔄 Yenile", callback_data=f"d:view:{container_id}"),
            InlineKeyboardButton("⬅️ Container'lar", callback_data="d:list:0"),
        ]
    )
    return InlineKeyboardMarkup(rows)



def docker_images_report_sync() -> str:
    """Image listesini salt-okunur raporlar; silme/prune yapmaz."""
    docker_required()
    images = docker_client.images.list(all=True)

    unique: dict[str, Any] = {}
    for image in images:
        unique[image.id] = image

    total_size = sum(int(img.attrs.get("Size", 0)) for img in unique.values())
    dangling = sum(1 for img in unique.values() if not img.tags)

    sorted_images = sorted(
        unique.values(),
        key=lambda img: int(img.attrs.get("Size", 0)),
        reverse=True,
    )

    lines = [
        "<b>🖼 Docker image'ları</b>",
        "",
        f"📦 <b>Toplam:</b> {len(unique)}",
        f"💽 <b>Toplam boyut:</b> {fmt_bytes(total_size)}",
        f"🧹 <b>Dangling:</b> {dangling}",
        "",
        "<b>Boyuta göre ilk 12</b>",
    ]

    for image in sorted_images[:12]:
        tag = image.tags[0] if image.tags else "&lt;dangling&gt;"
        lines.append(
            f"• <code>{image.short_id.replace('sha256:', '')}</code> "
            f"{fmt_bytes(image.attrs.get('Size', 0))} • {html.escape(tag) if image.tags else tag}"
        )

    return clip("\n".join(lines))



def docker_state_snapshot_sync() -> dict[str, dict[str, Any]]:
    if docker_client is None:
        return {}

    snapshot: dict[str, dict[str, Any]] = {}
    try:
        for c in docker_client.containers.list(all=True):
            c.reload()
            state = c.attrs.get("State", {})
            snapshot[c.id[:12]] = {
                "name": c.name,
                "status": c.status,
                "health": state.get("Health", {}).get("Status", ""),
                "restart_count": int(c.attrs.get("RestartCount", 0)),
            }
    except DockerException:
        return {}

    return snapshot


# ============================================================
# HOST KONTROLÜ - SSH ALLOWLIST
# ============================================================


def host_control_status_sync() -> str:
    """Host kontrolünün kurulum durumunu gösterir."""
    key_ok = Path(HOST_SSH_KEY).exists()
    known_ok = Path(HOST_KNOWN_HOSTS).exists()

    return (
        "<b>⚡ Raspberry Pi host yönetimi</b>\n\n"
        "Bu bölüm gerçek Raspberry Pi host'unu etkiler.\n"
        "Komutlar sabit allowlist üzerinden SSH ile gönderilir.\n\n"
        f"🔐 <b>SSH anahtarı:</b> {'🟢 Hazır' if key_ok else '🔴 Bulunamadı'}\n"
        f"🧾 <b>known_hosts:</b> {'🟢 Hazır' if known_ok else '🔴 Bulunamadı'}\n"
        f"🎯 <b>Hedef:</b> <code>{html.escape(HOST_SSH_TARGET)}</code>\n\n"
        "⚠️ Kapatma ve yeniden başlatma işlemleri tek kullanımlık onay ister."
    )



def run_host_action_sync(action: str) -> str:
    """
    Rastgele shell komutu kabul ETMEZ.
    Yalnızca aşağıdaki allowlist aksiyonları SSH tarafına yollar.
    Host'ta bu adların sudo/forced-command wrapper ile kısıtlanması önerilir.
    """
    allowed = {"reboot", "shutdown", "restart-docker"}

    if action not in allowed:
        raise ValueError("İzin verilmeyen host işlemi")
    if not HOST_CONTROL_ENABLED:
        raise RuntimeError("Host kontrolü kapalı.")
    if not Path(HOST_SSH_KEY).exists():
        raise RuntimeError("Host SSH anahtarı bulunamadı.")
    if not Path(HOST_KNOWN_HOSTS).exists():
        raise RuntimeError("known_hosts dosyası bulunamadı.")

    cmd = [
        "ssh",
        "-i",
        HOST_SSH_KEY,
        "-o",
        "BatchMode=yes",
        "-o",
        "ConnectTimeout=7",
        "-o",
        "StrictHostKeyChecking=yes",
        "-o",
        f"UserKnownHostsFile={HOST_KNOWN_HOSTS}",
        HOST_SSH_TARGET,
        action,
    ]

    completed = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        timeout=15,
        check=False,
    )

    # reboot/poweroff sırasında SSH bağlantısı kapanabildiğinden 255 görülebilir.
    if completed.returncode not in (0, 255):
        detail = (completed.stderr or completed.stdout or "").strip()
        raise RuntimeError(detail or f"SSH çıkış kodu: {completed.returncode}")

    if action == "reboot":
        return "✅ Raspberry Pi yeniden başlatma komutu gönderildi."
    if action == "shutdown":
        return "✅ Raspberry Pi kapatma komutu gönderildi."
    return "✅ Docker servisini yeniden başlatma komutu gönderildi."



def host_menu_markup() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton(
                    "🔁 Raspberry Pi yeniden başlat",
                    callback_data="h:req:reboot",
                )
            ],
            [
                InlineKeyboardButton(
                    "⏻ Raspberry Pi kapat",
                    callback_data="h:req:shutdown",
                )
            ],
            [
                InlineKeyboardButton(
                    "🐳 Docker servisini restart",
                    callback_data="h:req:restart-docker",
                )
            ],
            [
                InlineKeyboardButton("🔄 Yenile", callback_data="h:menu"),
                InlineKeyboardButton("⬅️ Ana menü", callback_data="m:main"),
            ],
        ]
    )


# ============================================================
# TELEGRAM KOMUTLARI
# ============================================================


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if await reject_if_unauthorized(update):
        return

    await update.effective_message.reply_text(
        "<b>✅ Pi Assistant Loruv V3</b>\n\n"
        "Raspberry Pi, Docker, ağ, depolama ve süreç yönetim paneli hazır.\n"
        "Aşağıdaki butonlardan ilerleyebilirsin.",
        reply_markup=main_menu(),
    )


async def durum(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if await reject_if_unauthorized(update):
        return
    text = await asyncio.to_thread(system_overview_sync)
    await update.effective_message.reply_text(text, reply_markup=system_menu())


async def docker_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if await reject_if_unauthorized(update):
        return
    await update.effective_message.reply_text(
        "<b>🐳 Docker yönetimi</b>\n\nBir bölüm seç:",
        reply_markup=docker_menu(),
    )


async def ip_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if await reject_if_unauthorized(update):
        return

    public_ip, latency = await asyncio.gather(
        asyncio.to_thread(read_public_ip),
        asyncio.to_thread(internet_latency_ms),
    )

    await update.effective_message.reply_text(
        f"🏠 Yerel IP: <code>{html.escape(local_ip())}</code>\n"
        f"🌍 Dış IP: <code>{html.escape(public_ip or 'Okunamadı')}</code>\n"
        f"⚡ TCP gecikme: "
        f"{f'{latency:.1f} ms' if latency is not None else 'Bağlantı kurulamadı'}",
        reply_markup=back_menu(),
    )


async def processes_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if await reject_if_unauthorized(update):
        return
    text = await asyncio.to_thread(process_summary_sync)
    await update.effective_message.reply_text(text, reply_markup=process_menu())


async def network_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if await reject_if_unauthorized(update):
        return
    text = await asyncio.to_thread(network_report_sync)
    await update.effective_message.reply_text(text, reply_markup=back_menu())


async def storage_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if await reject_if_unauthorized(update):
        return
    text = await asyncio.to_thread(storage_report_sync)
    await update.effective_message.reply_text(text, reply_markup=back_menu())


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await start(update, context)


# ============================================================
# CALLBACK ROUTER
# ============================================================


async def callback_router(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if await reject_if_unauthorized(update):
        return

    query = update.callback_query
    if not query:
        return

    await query.answer()
    data = str(query.data or "")

    try:
        # ----------------------------------------------------
        # Ana menü
        # ----------------------------------------------------
        if data == "m:main":
            await safe_edit(
                query,
                "<b>✅ Pi Assistant Loruv V3</b>\n\nBir bölüm seç:",
                main_menu(),
            )
            return

        # ----------------------------------------------------
        # Sistem
        # ----------------------------------------------------
        if data == "s:overview":
            await safe_edit(query, "⏳ Sistem bilgisi okunuyor…")
            text = await asyncio.to_thread(system_overview_sync)
            await safe_edit(query, text, system_menu())
            return

        if data == "s:hardware":
            await safe_edit(query, "⏳ Donanım bilgisi okunuyor…")
            text = await asyncio.to_thread(hardware_report_sync)
            markup = InlineKeyboardMarkup(
                [
                    [
                        InlineKeyboardButton("🔄 Yenile", callback_data="s:hardware"),
                        InlineKeyboardButton("⬅️ Sistem", callback_data="s:overview"),
                    ]
                ]
            )
            await safe_edit(query, text, markup)
            return

        if data == "s:memory":
            text = await asyncio.to_thread(memory_report_sync)
            markup = InlineKeyboardMarkup(
                [
                    [
                        InlineKeyboardButton("🔄 Yenile", callback_data="s:memory"),
                        InlineKeyboardButton("⬅️ Sistem", callback_data="s:overview"),
                    ]
                ]
            )
            await safe_edit(query, text, markup)
            return

        if data == "s:health":
            await safe_edit(query, "⏳ Sağlık kontrolleri yapılıyor…")
            text = await asyncio.to_thread(system_health_sync)
            markup = InlineKeyboardMarkup(
                [
                    [
                        InlineKeyboardButton("🔄 Yenile", callback_data="s:health"),
                        InlineKeyboardButton("⬅️ Ana menü", callback_data="m:main"),
                    ]
                ]
            )
            await safe_edit(query, text, markup)
            return

        # ----------------------------------------------------
        # Ağ / Depolama
        # ----------------------------------------------------
        if data == "n:overview":
            await safe_edit(query, "⏳ Ağ bilgileri okunuyor…")
            text = await asyncio.to_thread(network_report_sync)
            markup = InlineKeyboardMarkup(
                [
                    [
                        InlineKeyboardButton("🔄 Yenile", callback_data="n:overview"),
                        InlineKeyboardButton("⬅️ Ana menü", callback_data="m:main"),
                    ]
                ]
            )
            await safe_edit(query, text, markup)
            return

        if data == "st:overview":
            await safe_edit(query, "⏳ Depolama bilgileri okunuyor…")
            text = await asyncio.to_thread(storage_report_sync)
            markup = InlineKeyboardMarkup(
                [
                    [
                        InlineKeyboardButton("🔄 Yenile", callback_data="st:overview"),
                        InlineKeyboardButton("⬅️ Ana menü", callback_data="m:main"),
                    ]
                ]
            )
            await safe_edit(query, text, markup)
            return

        # ----------------------------------------------------
        # Süreçler
        # ----------------------------------------------------
        if data == "p:menu":
            await safe_edit(query, "⏳ Host süreçleri örnekleniyor…")
            text = await asyncio.to_thread(process_summary_sync)
            await safe_edit(query, text, process_menu())
            return

        if data.startswith("p:cpu:") or data.startswith("p:ram:"):
            _, sort_by, page_text = data.split(":", 2)
            page = int(page_text)
            await safe_edit(query, "⏳ Süreç listesi örnekleniyor…")
            text, pids, total_pages = await asyncio.to_thread(
                process_list_sync,
                sort_by,
                page,
            )
            # process_list_sync sayfayı sınırlar; callback'te gelen sayfa da
            # aynı aralıkta olacağı için burada doğrudan kullanılıyor.
            safe_page = max(0, min(page, total_pages - 1))
            await safe_edit(
                query,
                text,
                process_list_markup(sort_by, safe_page, pids, total_pages),
            )
            return

        if data.startswith("p:view:"):
            pid = int(data.split(":", 2)[2])
            await safe_edit(query, "⏳ Süreç ayrıntısı okunuyor…")
            text = await asyncio.to_thread(process_detail_sync, pid)
            markup = InlineKeyboardMarkup(
                [
                    [
                        InlineKeyboardButton("🔄 Yenile", callback_data=f"p:view:{pid}"),
                        InlineKeyboardButton("⬅️ Süreçler", callback_data="p:menu"),
                    ]
                ]
            )
            await safe_edit(query, text, markup)
            return

        # ----------------------------------------------------
        # Uyarılar
        # ----------------------------------------------------
        if data == "a:menu":
            enabled = load_alerts_enabled()
            state_text = "AÇIK 🟢" if enabled else "KAPALI 🔴"
            text = (
                "<b>🔔 Otomatik uyarılar</b>\n\n"
                f"Durum: <b>{state_text}</b>\n\n"
                f"CPU ≥ %{CPU_LIMIT:g}\n"
                f"RAM ≥ %{RAM_LIMIT:g}\n"
                f"Disk ≥ %{DISK_LIMIT:g}\n"
                f"Swap ≥ %{SWAP_LIMIT:g}\n"
                f"Sıcaklık ≥ {TEMP_LIMIT:g} °C\n"
                + (f"Load 1m ≥ {LOAD_LIMIT:g}\n" if LOAD_LIMIT > 0 else "Load alarmı: kapalı\n")
                + "İnternet kesintisi / geri gelmesi\n"
                + "Dış IP değişimi\n"
                + "Container start/stop/pause değişimleri\n"
                + "Docker health ve restart değişimleri"
            )
            markup = InlineKeyboardMarkup(
                [
                    [
                        InlineKeyboardButton(
                            "🔕 Uyarıları kapat" if enabled else "🔔 Uyarıları aç",
                            callback_data="a:toggle",
                        )
                    ],
                    [InlineKeyboardButton("🧪 Test bildirimi", callback_data="a:test")],
                    [InlineKeyboardButton("⬅️ Ana menü", callback_data="m:main")],
                ]
            )
            await safe_edit(query, text, markup)
            return

        if data == "a:toggle":
            enabled = not load_alerts_enabled()
            save_alerts_enabled(enabled)
            if enabled:
                for key in alert_state:
                    alert_state[key] = False
            await safe_edit(
                query,
                "✅ Uyarılar açıldı." if enabled else "🔕 Uyarılar kapatıldı.",
                InlineKeyboardMarkup(
                    [[InlineKeyboardButton("⬅️ Uyarılar", callback_data="a:menu")]]
                ),
            )
            return

        if data == "a:test":
            await context.bot.send_message(
                ALLOWED_USER_ID,
                "🧪 <b>Pi Assistant V3 test bildirimi</b>\nBildirim sistemi çalışıyor.",
                parse_mode=ParseMode.HTML,
            )
            await safe_edit(
                query,
                "✅ Test bildirimi gönderildi.",
                InlineKeyboardMarkup(
                    [[InlineKeyboardButton("⬅️ Uyarılar", callback_data="a:menu")]]
                ),
            )
            return

        # ----------------------------------------------------
        # Docker ana menü / özet / image
        # ----------------------------------------------------
        if data == "d:menu":
            try:
                containers = await asyncio.to_thread(list_containers_sync)
                running = sum(1 for c in containers if c["status"] == "running")
                unhealthy = sum(1 for c in containers if c["health"] == "unhealthy")
                text = (
                    "<b>🐳 Docker yönetimi</b>\n\n"
                    f"📦 Toplam container: <b>{len(containers)}</b>\n"
                    f"🟢 Çalışan: <b>{running}</b>\n"
                    f"🩺 Unhealthy: <b>{unhealthy}</b>\n\n"
                    "Bir bölüm seç:"
                )
            except DockerException as exc:
                text = f"❌ Docker bağlantısı yok: {html.escape(str(exc))}"
            await safe_edit(query, text, docker_menu())
            return

        if data == "d:overview":
            await safe_edit(query, "⏳ Docker daemon bilgisi okunuyor…")
            text = await asyncio.to_thread(docker_overview_sync)
            markup = InlineKeyboardMarkup(
                [
                    [
                        InlineKeyboardButton("🔄 Yenile", callback_data="d:overview"),
                        InlineKeyboardButton("⬅️ Docker", callback_data="d:menu"),
                    ]
                ]
            )
            await safe_edit(query, text, markup)
            return

        if data == "d:images":
            await safe_edit(query, "⏳ Docker image bilgileri okunuyor…")
            text = await asyncio.to_thread(docker_images_report_sync)
            markup = InlineKeyboardMarkup(
                [
                    [
                        InlineKeyboardButton("🔄 Yenile", callback_data="d:images"),
                        InlineKeyboardButton("⬅️ Docker", callback_data="d:menu"),
                    ]
                ]
            )
            await safe_edit(query, text, markup)
            return

        # ----------------------------------------------------
        # Docker container listesi / detay / stats / log
        # ----------------------------------------------------
        if data.startswith("d:list:"):
            page = int(data.rsplit(":", 1)[1])
            await safe_edit(query, "⏳ Docker listesi okunuyor…")
            containers = await asyncio.to_thread(list_containers_sync)
            text = (
                f"<b>📦 Docker container'ları</b>\n\n"
                f"Toplam: <b>{len(containers)}</b>\n"
                "Detay için bir container seç:"
            )
            await safe_edit(query, text, docker_list_markup(containers, page))
            return

        if data.startswith("d:view:"):
            container_id = data.split(":", 2)[2]
            await safe_edit(query, "⏳ Container bilgisi okunuyor…")
            cid, status, text = await asyncio.to_thread(
                container_details_sync,
                container_id,
            )
            await safe_edit(query, text, container_buttons(cid, status))
            return

        if data.startswith("d:stats:"):
            container_id = data.split(":", 2)[2]
            await safe_edit(query, "⏳ Docker stats alınıyor…")
            text = await asyncio.to_thread(container_stats_sync, container_id)
            markup = InlineKeyboardMarkup(
                [
                    [
                        InlineKeyboardButton(
                            "🔄 Yenile",
                            callback_data=f"d:stats:{container_id}",
                        ),
                        InlineKeyboardButton(
                            "⬅️ Container",
                            callback_data=f"d:view:{container_id}",
                        ),
                    ]
                ]
            )
            await safe_edit(query, text, markup)
            return

        if data.startswith("d:logs:"):
            container_id = data.split(":", 2)[2]
            await safe_edit(query, "⏳ Loglar okunuyor…")
            cid, text = await asyncio.to_thread(container_logs_sync, container_id)
            markup = InlineKeyboardMarkup(
                [
                    [
                        InlineKeyboardButton(
                            "🔄 Yenile",
                            callback_data=f"d:logs:{cid}",
                        ),
                        InlineKeyboardButton(
                            "⬅️ Container",
                            callback_data=f"d:view:{cid}",
                        ),
                    ]
                ]
            )
            await safe_edit(query, text, markup)
            return

        # ----------------------------------------------------
        # Docker aksiyon talebi
        # start/unpause doğrudan; stop/restart/pause onaylı.
        # ----------------------------------------------------
        if data.startswith("d:act:"):
            _, _, action, container_id = data.split(":", 3)

            if action in {"start", "unpause"}:
                await safe_edit(query, "⏳ Docker işlemi uygulanıyor…")
                text = await asyncio.to_thread(
                    container_action_sync,
                    container_id,
                    action,
                )
                await safe_edit(
                    query,
                    text,
                    InlineKeyboardMarkup(
                        [
                            [
                                InlineKeyboardButton(
                                    "⬅️ Container",
                                    callback_data=f"d:view:{container_id}",
                                )
                            ]
                        ]
                    ),
                )
                return

            if action not in {"stop", "restart", "pause"}:
                raise ValueError("Geçersiz Docker işlemi")

            c = await asyncio.to_thread(docker_client.containers.get, container_id)
            labels = {
                "stop": "durdurmak",
                "restart": "yeniden başlatmak",
                "pause": "pause etmek",
            }
            token = create_confirmation(
                kind=f"docker:{action}",
                target=container_id,
                back=f"d:view:{container_id}",
            )
            await safe_edit(
                query,
                "⚠️ <b>Kritik Docker işlemi</b>\n\n"
                f"<b>{html.escape(c.name)}</b> container'ını "
                f"<b>{labels[action]}</b> istediğine emin misin?\n\n"
                f"Onay {CONFIRM_TTL} saniye geçerlidir.",
                confirmation_markup(token, f"d:view:{container_id}"),
            )
            return

        # ----------------------------------------------------
        # Host menüsü / aksiyon talebi
        # ----------------------------------------------------
        if data == "h:menu":
            if not HOST_CONTROL_ENABLED:
                raise RuntimeError("Host kontrolü kapalı.")
            text = await asyncio.to_thread(host_control_status_sync)
            await safe_edit(query, text, host_menu_markup())
            return

        if data.startswith("h:req:"):
            if not HOST_CONTROL_ENABLED:
                raise RuntimeError("Host kontrolü kapalı.")

            action = data.split(":", 2)[2]
            labels = {
                "reboot": "Raspberry Pi'yi yeniden başlatmak",
                "shutdown": "Raspberry Pi'yi tamamen kapatmak",
                "restart-docker": "Docker servisini yeniden başlatmak",
            }
            if action not in labels:
                raise ValueError("Geçersiz host işlemi")

            token = create_confirmation(
                kind=f"host:{action}",
                target="host",
                back="h:menu",
            )
            await safe_edit(
                query,
                "⚠️ <b>Son onay</b>\n\n"
                f"{labels[action]} üzeresin.\n"
                f"Onay butonu {CONFIRM_TTL} saniye ve yalnızca bir kullanım için geçerlidir.",
                confirmation_markup(token, "h:menu"),
            )
            return

        # ----------------------------------------------------
        # Tek kullanımlık kritik işlem onayı
        # ----------------------------------------------------
        if data.startswith("cf:"):
            token = data.split(":", 1)[1]
            confirmation = consume_confirmation(token)
            if not confirmation:
                await safe_edit(
                    query,
                    "⌛ Bu onayın süresi dolmuş veya daha önce kullanılmış.",
                    back_menu(),
                )
                return

            kind = str(confirmation["kind"])
            target = str(confirmation["target"])
            back = str(confirmation["back"])

            if kind.startswith("docker:"):
                action = kind.split(":", 1)[1]
                await safe_edit(query, "⏳ Docker işlemi uygulanıyor…")
                text = await asyncio.to_thread(
                    container_action_sync,
                    target,
                    action,
                )
                await safe_edit(
                    query,
                    text,
                    InlineKeyboardMarkup(
                        [[InlineKeyboardButton("⬅️ Container", callback_data=back)]]
                    ),
                )
                return

            if kind.startswith("host:"):
                action = kind.split(":", 1)[1]

                # Kullanıcıya önce görünür bilgi bırakılır. Reboot/shutdown
                # sonrasında bot kısa süre çevrimdışı olacaktır.
                await safe_edit(
                    query,
                    "⚡ Host komutu gönderiliyor. Cihaz/servis kısa süre erişilemez olabilir…",
                )
                result = await asyncio.to_thread(run_host_action_sync, action)
                await safe_edit(
                    query,
                    html.escape(result),
                    InlineKeyboardMarkup(
                        [[InlineKeyboardButton("⬅️ Ana menü", callback_data="m:main")]]
                    ),
                )
                return

            raise ValueError("Bilinmeyen onay işlemi")

        # ----------------------------------------------------
        # Hakkında
        # ----------------------------------------------------
        if data == "x:about":
            docker_text = "bağlı" if docker_client is not None else "bağlı değil"
            text = (
                "<b>ℹ️ Pi Assistant Loruv V3</b>\n\n"
                "• Telegram butonlu yönetim paneli\n"
                "• Raspberry Pi sistem/ağ/depolama izleme\n"
                "• Ayrıntılı host process görünümü\n"
                "• Docker container yönetimi, stats ve log\n"
                "• Kritik işlemlerde süreli tek kullanımlık onay\n"
                "• Otomatik kaynak/internet/Docker uyarıları\n"
                "• Opsiyonel güvenli host reboot/shutdown\n\n"
                f"🐳 Docker: <b>{docker_text}</b>\n"
                f"🔔 Uyarılar: <b>{'açık' if load_alerts_enabled() else 'kapalı'}</b>\n"
                f"⚡ Host kontrolü: <b>{'açık' if HOST_CONTROL_ENABLED else 'kapalı'}</b>"
            )
            await safe_edit(query, text, back_menu())
            return

        await query.answer("Bilinmeyen işlem.", show_alert=True)

    except NotFound:
        await safe_edit(
            query,
            "❌ Container artık bulunamadı.",
            InlineKeyboardMarkup(
                [[InlineKeyboardButton("⬅️ Docker", callback_data="d:list:0")]]
            ),
        )
    except (DockerException, RuntimeError, ValueError, psutil.Error) as exc:
        logger.warning("İşlem hatası: %s", exc)
        await safe_edit(
            query,
            f"❌ <b>İşlem başarısız</b>\n\n{html.escape(str(exc))}",
            back_menu(),
        )
    except Exception as exc:
        logger.exception("Callback hatası")
        await safe_edit(
            query,
            f"❌ Beklenmeyen hata: <code>{html.escape(str(exc))}</code>",
            back_menu(),
        )


# ============================================================
# İZLEME / UYARI MOTORU
# ============================================================


async def send_alert(
    context: ContextTypes.DEFAULT_TYPE,
    key: str,
    active: bool,
    active_message: str,
    recovery_message: str,
) -> None:
    """Alarm sadece durum değişiminde bir kez gönderilir."""
    previous = alert_state.get(key, False)
    alerts_enabled = load_alerts_enabled()

    if alerts_enabled:
        if active and not previous:
            await context.bot.send_message(
                ALLOWED_USER_ID,
                active_message,
                parse_mode=ParseMode.HTML,
            )
        elif not active and previous:
            await context.bot.send_message(
                ALLOWED_USER_ID,
                recovery_message,
                parse_mode=ParseMode.HTML,
            )

    alert_state[key] = active



def monitor_metrics_sync() -> dict[str, Any]:
    disk_target = str(HOST_ROOT if HOST_ROOT.exists() else Path("/"))
    load1, load5, load15 = os.getloadavg()
    return {
        "cpu": psutil.cpu_percent(interval=0.40),
        "ram": psutil.virtual_memory().percent,
        "swap": psutil.swap_memory().percent,
        "disk": psutil.disk_usage(disk_target).percent,
        "temp": cpu_temp(),
        "load1": load1,
        "load5": load5,
        "load15": load15,
    }


async def monitor_docker_changes(context: ContextTypes.DEFAULT_TYPE) -> None:
    """Container status/health/restart değişikliklerini bildirir."""
    global docker_monitor_state

    current = await asyncio.to_thread(docker_state_snapshot_sync)
    if not current:
        return

    alerts_enabled = load_alerts_enabled()

    if docker_monitor_state:
        for cid, info in current.items():
            old = docker_monitor_state.get(cid)

            if old is None:
                if alerts_enabled:
                    await context.bot.send_message(
                        ALLOWED_USER_ID,
                        f"🐳 Yeni container görüldü: <b>{html.escape(info['name'])}</b> "
                        f"({html.escape(info['status'])})",
                        parse_mode=ParseMode.HTML,
                    )
                continue

            if old.get("status") != info.get("status") and alerts_enabled:
                icon = "🟢" if info["status"] == "running" else "🔴"
                await context.bot.send_message(
                    ALLOWED_USER_ID,
                    f"{icon} <b>{html.escape(info['name'])}</b> durumu değişti\n"
                    f"{html.escape(str(old.get('status')))} → "
                    f"<b>{html.escape(str(info.get('status')))}</b>",
                    parse_mode=ParseMode.HTML,
                )

            if (
                old.get("health") != info.get("health")
                and info.get("health")
                and alerts_enabled
            ):
                icon = "✅" if info["health"] == "healthy" else "🩺"
                await context.bot.send_message(
                    ALLOWED_USER_ID,
                    f"{icon} <b>{html.escape(info['name'])}</b> health: "
                    f"<b>{html.escape(info['health'])}</b>",
                    parse_mode=ParseMode.HTML,
                )

            if (
                int(info.get("restart_count", 0))
                > int(old.get("restart_count", 0))
                and alerts_enabled
            ):
                await context.bot.send_message(
                    ALLOWED_USER_ID,
                    f"🔁 <b>{html.escape(info['name'])}</b> restart sayısı arttı: "
                    f"{old.get('restart_count', 0)} → {info.get('restart_count', 0)}",
                    parse_mode=ParseMode.HTML,
                )

        removed = set(docker_monitor_state) - set(current)
        for cid in removed:
            old = docker_monitor_state[cid]
            if alerts_enabled:
                await context.bot.send_message(
                    ALLOWED_USER_ID,
                    "🗑 Docker container artık görünmüyor: "
                    f"<b>{html.escape(old.get('name', cid))}</b>",
                    parse_mode=ParseMode.HTML,
                )

    docker_monitor_state = current


async def monitor(context: ContextTypes.DEFAULT_TYPE) -> None:
    """Periyodik kaynak, internet ve Docker izleme döngüsü."""
    try:
        metrics_task = asyncio.to_thread(monitor_metrics_sync)
        ip_task = asyncio.to_thread(read_public_ip)
        metrics, public_ip = await asyncio.gather(metrics_task, ip_task)

        cpu = float(metrics["cpu"])
        ram = float(metrics["ram"])
        swap = float(metrics["swap"])
        disk = float(metrics["disk"])
        temp = metrics["temp"]
        load1 = float(metrics["load1"])

        await send_alert(
            context,
            "cpu",
            cpu >= CPU_LIMIT,
            f"⚠️ CPU kullanımı yüksek: <b>%{cpu:.1f}</b>",
            f"✅ CPU normale döndü: <b>%{cpu:.1f}</b>",
        )
        await send_alert(
            context,
            "ram",
            ram >= RAM_LIMIT,
            f"⚠️ RAM kullanımı yüksek: <b>%{ram:.1f}</b>",
            f"✅ RAM normale döndü: <b>%{ram:.1f}</b>",
        )
        await send_alert(
            context,
            "swap",
            swap >= SWAP_LIMIT,
            f"⚠️ Swap kullanımı yüksek: <b>%{swap:.1f}</b>",
            f"✅ Swap normale döndü: <b>%{swap:.1f}</b>",
        )
        await send_alert(
            context,
            "disk",
            disk >= DISK_LIMIT,
            f"⚠️ Disk kullanımı yüksek: <b>%{disk:.1f}</b>",
            f"✅ Disk kullanımı normale döndü: <b>%{disk:.1f}</b>",
        )

        if temp is not None:
            await send_alert(
                context,
                "temp",
                temp >= TEMP_LIMIT,
                f"🔥 Sıcaklık yüksek: <b>{temp:.1f} °C</b>",
                f"✅ Sıcaklık normale döndü: <b>{temp:.1f} °C</b>",
            )

        if LOAD_LIMIT > 0:
            await send_alert(
                context,
                "load",
                load1 >= LOAD_LIMIT,
                f"📈 Load yüksek: <b>{load1:.2f}</b>",
                f"✅ Load normale döndü: <b>{load1:.2f}</b>",
            )

        await send_alert(
            context,
            "internet",
            public_ip is None,
            "🌐 <b>İnternet erişimi kesildi</b> veya dış IP servisine ulaşılamıyor.",
            "✅ <b>İnternet erişimi geri geldi.</b>",
        )

        # Dış IP değişimini kalıcı state dosyasından izler.
        if public_ip:
            ip_file = STATE_DIR / "public_ip.txt"
            old_ip = read_text(ip_file)

            if old_ip and old_ip != public_ip and load_alerts_enabled():
                await context.bot.send_message(
                    ALLOWED_USER_ID,
                    "🔄 <b>Dış IP değişti</b>\n"
                    f"Eski: <code>{html.escape(old_ip)}</code>\n"
                    f"Yeni: <code>{html.escape(public_ip)}</code>",
                    parse_mode=ParseMode.HTML,
                )

            ip_file.write_text(public_ip)

        await monitor_docker_changes(context)
        prune_confirmation_tokens()

    except TelegramError:
        logger.exception("Telegram alarm gönderim hatası")
    except Exception:
        logger.exception("Monitor döngüsü hatası")


# ============================================================
# BAŞLANGIÇ / HATA YÖNETİMİ
# ============================================================


async def post_init(application: Application) -> None:
    global docker_monitor_state

    # Telegram'ın slash command menüsünü oluşturur.
    await application.bot.set_my_commands(
        [
            BotCommand("menu", "Ana yönetim menüsü"),
            BotCommand("durum", "Sistem durum raporu"),
            BotCommand("docker", "Docker yönetimi"),
            BotCommand("surecler", "Host süreçleri"),
            BotCommand("ag", "Ağ raporu"),
            BotCommand("depolama", "Disk ve I/O raporu"),
            BotCommand("ip", "Yerel ve dış IP"),
            BotCommand("yardim", "Yardım / ana menü"),
        ]
    )

    docker_monitor_state = await asyncio.to_thread(docker_state_snapshot_sync)

    # Bot ayağa kalkınca Telegram'a bilgi verir.
    await application.bot.send_message(
        ALLOWED_USER_ID,
        "<b>✅ Pi Assistant Loruv V3 çalışıyor.</b>\n"
        "Bot container'ı veya Raspberry Pi yeniden başlatılmış olabilir.",
        parse_mode=ParseMode.HTML,
        reply_markup=main_menu(),
    )

    if application.job_queue is None:
        raise RuntimeError(
            'JobQueue kurulu değil. requirements.txt içinde '
            '"python-telegram-bot[job-queue]" kullanılmalı.'
        )

    application.job_queue.run_repeating(
        monitor,
        interval=CHECK_INTERVAL,
        first=10,
        name="pi-assistant-v3-monitor",
    )


async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    logger.error(
        "Telegram update hatası: %r",
        context.error,
        exc_info=(
            type(context.error),
            context.error,
            context.error.__traceback__,
        )
        if context.error
        else None,
    )


# ============================================================
# MAIN
# ============================================================


def main() -> None:
    defaults = Defaults(parse_mode=ParseMode.HTML)

    app = (
        Application.builder()
        .token(BOT_TOKEN)
        .defaults(defaults)
        .post_init(post_init)
        .build()
    )

    app.add_handler(CommandHandler(["start", "menu"], start))
    app.add_handler(CommandHandler("durum", durum))
    app.add_handler(CommandHandler("docker", docker_command))
    app.add_handler(CommandHandler("surecler", processes_command))
    app.add_handler(CommandHandler("ag", network_command))
    app.add_handler(CommandHandler("depolama", storage_command))
    app.add_handler(CommandHandler("ip", ip_command))
    app.add_handler(CommandHandler("yardim", help_command))
    app.add_handler(CallbackQueryHandler(callback_router))
    app.add_error_handler(error_handler)

    app.run_polling(drop_pending_updates=True)


if __name__ == "__main__":
    main()
