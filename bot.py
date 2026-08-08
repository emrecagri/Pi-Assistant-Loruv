import asyncio
import html
import json
import logging
import os
import socket
import subprocess
import time
import urllib.request
from pathlib import Path
from typing import Any, Optional

import docker
import psutil
from docker.errors import DockerException, NotFound
from telegram import BotCommand, InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.constants import ParseMode
from telegram.error import BadRequest
from telegram.ext import (
    Application,
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    Defaults,
)

BOT_TOKEN = os.environ["BOT_TOKEN"]
ALLOWED_USER_ID = int(os.environ["ALLOWED_USER_ID"])

CHECK_INTERVAL = int(os.getenv("CHECK_INTERVAL", "60"))
CPU_LIMIT = float(os.getenv("CPU_LIMIT", "90"))
RAM_LIMIT = float(os.getenv("RAM_LIMIT", "90"))
DISK_LIMIT = float(os.getenv("DISK_LIMIT", "90"))
TEMP_LIMIT = float(os.getenv("TEMP_LIMIT", "75"))

PUBLIC_IP_CHECK_URL = os.getenv(
    "PUBLIC_IP_CHECK_URL",
    "https://api.ipify.org",
)

SELF_CONTAINER_NAME = os.getenv("SELF_CONTAINER_NAME", "pi-assistant-loruv")

HOST_ROOT = Path(os.getenv("HOST_ROOT", "/host/root"))
HOST_SYS = Path(os.getenv("HOST_SYS", "/host/sys"))
STATE_DIR = Path(os.getenv("STATE_DIR", "/app/data"))
STATE_DIR.mkdir(parents=True, exist_ok=True)

HOST_CONTROL_ENABLED = os.getenv("HOST_CONTROL_ENABLED", "false").lower() == "true"
HOST_SSH_TARGET = os.getenv("HOST_SSH_TARGET", "piassistant@127.0.0.1")
HOST_SSH_KEY = os.getenv("HOST_SSH_KEY", "/run/secrets/host_ssh_key")
HOST_KNOWN_HOSTS = os.getenv("HOST_KNOWN_HOSTS", "/run/secrets/known_hosts")

DOCKER_PAGE_SIZE = 8
MAX_MESSAGE = 3900

logging.basicConfig(
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    level=os.getenv("LOG_LEVEL", "INFO").upper(),
)
logger = logging.getLogger("pi-assistant-loruv")

try:
    docker_client = docker.from_env()
    docker_client.ping()
except DockerException as exc:
    logger.error("Docker bağlantısı kurulamadı: %s", exc)
    docker_client = None

alert_state = {
    "cpu": False,
    "ram": False,
    "disk": False,
    "temp": False,
    "internet": False,
}
docker_monitor_state: dict[str, dict[str, Any]] = {}


# ----------------------------
# Genel yardımcılar
# ----------------------------

def clip(text: str, limit: int = MAX_MESSAGE) -> str:
    if len(text) <= limit:
        return text
    return text[: limit - 80] + "\n\n… çıktı kısaltıldı."


def fmt_bytes(value: float) -> str:
    units = ("B", "KB", "MB", "GB", "TB", "PB")
    value = float(value)
    for unit in units:
        if abs(value) < 1024.0 or unit == units[-1]:
            return f"{value:.2f} {unit}"
        value /= 1024.0
    return f"{value:.2f} PB"


def read_text(path: Path, default: str = "") -> str:
    try:
        return path.read_text(errors="ignore").replace("\x00", "").strip()
    except OSError:
        return default


def host_path(relative: str) -> Path:
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
    path = host_path("/etc/os-release")
    raw = read_text(path)
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


def uptime_text() -> str:
    seconds = max(0, int(time.time() - psutil.boot_time()))
    days, seconds = divmod(seconds, 86400)
    hours, seconds = divmod(seconds, 3600)
    minutes, _ = divmod(seconds, 60)
    return f"{days} gün {hours} saat {minutes} dk"


def local_ip() -> str:
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        sock.connect(("1.1.1.1", 80))
        return sock.getsockname()[0]
    except OSError:
        return "Bulunamadı"
    finally:
        sock.close()


def read_public_ip() -> Optional[str]:
    try:
        request = urllib.request.Request(
            PUBLIC_IP_CHECK_URL,
            headers={"User-Agent": "Pi-Assistant-Loruv/2.0"},
        )
        with urllib.request.urlopen(request, timeout=8) as response:
            value = response.read().decode().strip()
            return value or None
    except Exception:
        return None


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
    if is_authorized(update):
        return False
    if update.callback_query:
        await update.callback_query.answer("Bu botu kullanma yetkin yok.", show_alert=True)
    elif update.effective_message:
        await update.effective_message.reply_text("Bu botu kullanma yetkin yok.")
    return True


async def safe_edit(query, text: str, reply_markup: InlineKeyboardMarkup | None = None) -> None:
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


def main_menu() -> InlineKeyboardMarkup:
    rows = [
        [
            InlineKeyboardButton("📊 Sistem", callback_data="s:overview"),
            InlineKeyboardButton("🐳 Docker", callback_data="d:list:0"),
        ],
        [
            InlineKeyboardButton("🌐 Ağ", callback_data="n:overview"),
            InlineKeyboardButton("💽 Depolama", callback_data="st:overview"),
        ],
        [
            InlineKeyboardButton("⚙️ Süreçler", callback_data="p:top"),
            InlineKeyboardButton("🔔 Uyarılar", callback_data="a:menu"),
        ],
    ]
    if HOST_CONTROL_ENABLED:
        rows.append([InlineKeyboardButton("⚡ Host Yönetimi", callback_data="h:menu")])
    rows.append([InlineKeyboardButton("🔄 Yenile", callback_data="m:main")])
    return InlineKeyboardMarkup(rows)


def back_menu() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [[InlineKeyboardButton("⬅️ Ana menü", callback_data="m:main")]]
    )


# ----------------------------
# Sistem raporları
# ----------------------------

def system_overview_sync() -> str:
    cpu = psutil.cpu_percent(interval=0.45)
    ram = psutil.virtual_memory()
    disk_target = str(HOST_ROOT if HOST_ROOT.exists() else Path("/"))
    disk = psutil.disk_usage(disk_target)
    temp = cpu_temp()
    freq = psutil.cpu_freq()
    load1, load5, load15 = os.getloadavg()
    net = psutil.net_io_counters()

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
        f"💾 <b>RAM:</b> %{ram.percent:.1f} • {fmt_bytes(ram.used)} / {fmt_bytes(ram.total)}\n"
        f"🗄 <b>Disk:</b> %{disk.percent:.1f} • {fmt_bytes(disk.used)} / {fmt_bytes(disk.total)}\n\n"
        f"⬆️ <b>Toplam gönderilen:</b> {fmt_bytes(net.bytes_sent)}\n"
        f"⬇️ <b>Toplam alınan:</b> {fmt_bytes(net.bytes_recv)}\n"
        f"🏠 <b>Yerel IP:</b> {html.escape(local_ip())}\n"
        f"⏱ <b>Uptime:</b> {uptime_text()}"
    )


def storage_report_sync() -> str:
    disk_target = str(HOST_ROOT if HOST_ROOT.exists() else Path("/"))
    disk = psutil.disk_usage(disk_target)
    io = psutil.disk_io_counters()

    text = (
        "<b>💽 Depolama</b>\n\n"
        f"📦 <b>Toplam:</b> {fmt_bytes(disk.total)}\n"
        f"✅ <b>Boş:</b> {fmt_bytes(disk.free)}\n"
        f"📁 <b>Kullanılan:</b> {fmt_bytes(disk.used)} (%{disk.percent:.1f})\n"
    )

    if io:
        text += (
            "\n<b>Disk I/O</b>\n"
            f"📖 Okuma: {fmt_bytes(io.read_bytes)} • {io.read_count:,} işlem\n"
            f"✍️ Yazma: {fmt_bytes(io.write_bytes)} • {io.write_count:,} işlem\n"
        )

    # Yaygın host dizinlerinin kaba boyutu disk kullanımı üzerinden değil,
    # dosya ağacını tarayarak hesaplanmadığı için burada özellikle gösterilmiyor.
    return text


def network_report_sync(public_ip: Optional[str]) -> str:
    addrs = psutil.net_if_addrs()
    stats = psutil.net_if_stats()
    counters = psutil.net_io_counters(pernic=True)

    lines = [
        "<b>🌐 Ağ durumu</b>",
        "",
        f"🏠 <b>Ana yerel IP:</b> {html.escape(local_ip())}",
        f"🌍 <b>Genel IP:</b> {html.escape(public_ip or 'Okunamadı')}",
        "",
        "<b>Arayüzler</b>",
    ]

    shown = 0
    for name in sorted(addrs):
        if name == "lo":
            continue
        ipv4 = [
            a.address
            for a in addrs[name]
            if getattr(a.family, "name", "") == "AF_INET"
        ]
        if not ipv4:
            continue
        stat = stats.get(name)
        state = "🟢" if stat and stat.isup else "🔴"
        speed = f" • {stat.speed} Mbps" if stat and stat.speed and stat.speed > 0 else ""
        lines.append(
            f"{state} <b>{html.escape(name)}</b>: "
            f"{html.escape(', '.join(ipv4))}{speed}"
        )
        nic = counters.get(name)
        if nic:
            lines.append(
                f"   ↕️ {fmt_bytes(nic.bytes_recv)} ↓ / {fmt_bytes(nic.bytes_sent)} ↑"
            )
        shown += 1
        if shown >= 10:
            break

    if shown == 0:
        lines.append("Arayüz bilgisi bulunamadı.")

    return "\n".join(lines)


def top_processes_sync() -> str:
    processes = []
    for proc in psutil.process_iter(["pid", "name", "username"]):
        try:
            proc.cpu_percent(None)
            processes.append(proc)
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            pass

    time.sleep(0.35)

    rows = []
    for proc in processes:
        try:
            rows.append(
                {
                    "pid": proc.pid,
                    "name": proc.name() or "?",
                    "cpu": proc.cpu_percent(None),
                    "ram": proc.memory_percent(),
                }
            )
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue

    top_cpu = sorted(rows, key=lambda x: x["cpu"], reverse=True)[:7]
    top_ram = sorted(rows, key=lambda x: x["ram"], reverse=True)[:7]

    lines = ["<b>⚙️ Host süreçleri</b>", "", "<b>CPU'ya göre ilk 7</b>"]
    for item in top_cpu:
        lines.append(
            f"<code>{item['pid']:>6}</code> "
            f"{item['cpu']:>5.1f}%  {html.escape(item['name'][:28])}"
        )

    lines.extend(["", "<b>RAM'e göre ilk 7</b>"])
    for item in top_ram:
        lines.append(
            f"<code>{item['pid']:>6}</code> "
            f"{item['ram']:>5.1f}%  {html.escape(item['name'][:28])}"
        )

    return "\n".join(lines)


# ----------------------------
# Docker
# ----------------------------

def docker_required() -> None:
    if docker_client is None:
        raise DockerException("Docker daemon bağlantısı yok.")


def list_containers_sync() -> list[dict[str, str]]:
    docker_required()
    result = []
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


def docker_list_markup(containers: list[dict[str, str]], page: int) -> InlineKeyboardMarkup:
    total_pages = max(1, (len(containers) + DOCKER_PAGE_SIZE - 1) // DOCKER_PAGE_SIZE)
    page = max(0, min(page, total_pages - 1))
    start = page * DOCKER_PAGE_SIZE
    page_items = containers[start : start + DOCKER_PAGE_SIZE]

    rows = []
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

    nav = []
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
            InlineKeyboardButton("⬅️ Ana menü", callback_data="m:main"),
        ]
    )
    return InlineKeyboardMarkup(rows)


def container_details_sync(container_id: str) -> tuple[str, str]:
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

    ports = []
    for port, bindings in (network.get("Ports") or {}).items():
        if not bindings:
            ports.append(port)
            continue
        for bind in bindings:
            ports.append(
                f"{bind.get('HostIp', '')}:{bind.get('HostPort', '')} → {port}"
            )

    ips = []
    for net_name, data in (network.get("Networks") or {}).items():
        ip_addr = data.get("IPAddress")
        if ip_addr:
            ips.append(f"{net_name}: {ip_addr}")

    text = (
        f"<b>🐳 {html.escape(c.name)}</b>\n\n"
        f"Durum: <b>{html.escape(c.status)}</b>\n"
        f"Health: <b>{html.escape(health)}</b>\n"
        f"Image: <code>{html.escape(str(image))}</code>\n"
        f"ID: <code>{c.id[:12]}</code>\n"
        f"Restart sayısı: {restart_count}\n"
        f"Restart policy: {html.escape(str(restart_policy))}\n"
        f"Başlangıç: {html.escape(str(state.get('StartedAt', '-'))[:19])}\n"
    )

    if ports:
        text += "\n<b>Portlar</b>\n" + "\n".join(
            f"• {html.escape(port)}" for port in ports[:12]
        )
    if ips:
        text += "\n\n<b>Container IP</b>\n" + "\n".join(
            f"• {html.escape(value)}" for value in ips[:8]
        )

    return c.id[:12], text


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
    for row in (
        stats.get("blkio_stats", {}).get("io_service_bytes_recursive") or []
    ):
        op = str(row.get("op", "")).lower()
        value = int(row.get("value", 0))
        if op == "read":
            block_read += value
        elif op == "write":
            block_write += value

    return (
        f"<b>📈 {html.escape(c.name)} istatistikleri</b>\n\n"
        f"🧠 CPU: <b>%{cpu_percent:.1f}</b>\n"
        f"💾 RAM: <b>%{mem_percent:.1f}</b> • "
        f"{fmt_bytes(mem_effective)} / {fmt_bytes(mem_limit)}\n"
        f"🌐 Ağ: {fmt_bytes(rx)} ↓ / {fmt_bytes(tx)} ↑\n"
        f"💽 Block I/O: {fmt_bytes(block_read)} oku / {fmt_bytes(block_write)} yaz"
    )


def container_logs_sync(container_id: str) -> tuple[str, str]:
    docker_required()
    c = docker_client.containers.get(container_id)
    raw = c.logs(
        tail=80,
        timestamps=True,
        stdout=True,
        stderr=True,
    )
    text = raw.decode("utf-8", errors="replace").strip() or "(log yok)"
    text = clip(text, 3100)
    return c.id[:12], (
        f"<b>📜 {html.escape(c.name)} — son 80 satır</b>\n\n"
        f"<pre>{html.escape(text)}</pre>"
    )


def container_action_sync(container_id: str, action: str) -> str:
    docker_required()
    c = docker_client.containers.get(container_id)

    if c.name == SELF_CONTAINER_NAME:
        raise DockerException(
            "Bot kendi container'ını Telegram üzerinden durduramaz/yeniden başlatamaz."
        )

    if action == "start":
        c.start()
    elif action == "stop":
        c.stop(timeout=15)
    elif action == "restart":
        c.restart(timeout=15)
    else:
        raise ValueError("Geçersiz Docker işlemi")

    c.reload()
    return f"✅ <b>{html.escape(c.name)}</b>: {html.escape(action)} tamamlandı."


def container_buttons(container_id: str, status: str | None = None) -> InlineKeyboardMarkup:
    rows = [
        [
            InlineKeyboardButton("📈 Stats", callback_data=f"d:stats:{container_id}"),
            InlineKeyboardButton("📜 Log", callback_data=f"d:logs:{container_id}"),
        ]
    ]

    actions = []
    if status != "running":
        actions.append(
            InlineKeyboardButton("▶️ Başlat", callback_data=f"d:act:start:{container_id}")
        )
    else:
        actions.extend(
            [
                InlineKeyboardButton(
                    "⏹ Durdur", callback_data=f"d:act:stop:{container_id}"
                ),
                InlineKeyboardButton(
                    "🔁 Restart", callback_data=f"d:act:restart:{container_id}"
                ),
            ]
        )
    rows.append(actions)
    rows.append(
        [
            InlineKeyboardButton("🔄 Yenile", callback_data=f"d:view:{container_id}"),
            InlineKeyboardButton("⬅️ Docker", callback_data="d:list:0"),
        ]
    )
    return InlineKeyboardMarkup(rows)


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


# ----------------------------
# Host kontrolü (opsiyonel, SSH allowlist)
# ----------------------------

def run_host_action_sync(action: str) -> str:
    allowed = {"reboot", "shutdown", "restart-docker"}
    if action not in allowed:
        raise ValueError("İzin verilmeyen host işlemi")
    if not HOST_CONTROL_ENABLED:
        raise RuntimeError("Host kontrolü kapalı.")

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
    )

    # Reboot/poweroff sırasında SSH bağlantısı kapanabildiğinden 255 normal olabilir.
    if completed.returncode not in (0, 255):
        detail = (completed.stderr or completed.stdout or "").strip()
        raise RuntimeError(detail or f"SSH çıkış kodu: {completed.returncode}")

    if action == "reboot":
        return "✅ Raspberry Pi yeniden başlatma komutu gönderildi."
    if action == "shutdown":
        return "✅ Raspberry Pi kapatma komutu gönderildi."
    return "✅ Docker servisini yeniden başlatma komutu gönderildi."


# ----------------------------
# Telegram komutları
# ----------------------------

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if await reject_if_unauthorized(update):
        return
    await update.effective_message.reply_text(
        "<b>✅ Pi Assistant Loruv v2</b>\n\n"
        "Raspberry Pi ve Docker yönetim paneli hazır.\n"
        "Aşağıdaki butonlardan ilerleyebilirsin.",
        reply_markup=main_menu(),
    )


async def durum(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if await reject_if_unauthorized(update):
        return
    text = await asyncio.to_thread(system_overview_sync)
    await update.effective_message.reply_text(text, reply_markup=back_menu())


async def docker_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if await reject_if_unauthorized(update):
        return
    try:
        containers = await asyncio.to_thread(list_containers_sync)
        text = (
            f"<b>🐳 Docker</b>\n\n"
            f"Toplam container: <b>{len(containers)}</b>\n"
            "Bir container seç:"
        )
        await update.effective_message.reply_text(
            text,
            reply_markup=docker_list_markup(containers, 0),
        )
    except DockerException as exc:
        await update.effective_message.reply_text(
            f"❌ Docker hatası: {html.escape(str(exc))}"
        )


async def ip_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if await reject_if_unauthorized(update):
        return
    public_ip = await asyncio.to_thread(read_public_ip)
    await update.effective_message.reply_text(
        f"🏠 Yerel IP: <code>{html.escape(local_ip())}</code>\n"
        f"🌍 Genel IP: <code>{html.escape(public_ip or 'Okunamadı')}</code>",
        reply_markup=back_menu(),
    )


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await start(update, context)


# ----------------------------
# Callback menü sistemi
# ----------------------------

async def callback_router(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if await reject_if_unauthorized(update):
        return

    query = update.callback_query
    if not query:
        return

    await query.answer()
    data = str(query.data or "")

    try:
        if data == "m:main":
            await safe_edit(
                query,
                "<b>✅ Pi Assistant Loruv v2</b>\n\nBir bölüm seç:",
                main_menu(),
            )
            return

        if data == "s:overview":
            await safe_edit(query, "⏳ Sistem bilgisi okunuyor…")
            text = await asyncio.to_thread(system_overview_sync)
            markup = InlineKeyboardMarkup(
                [
                    [
                        InlineKeyboardButton("🔄 Yenile", callback_data="s:overview"),
                        InlineKeyboardButton("⬅️ Ana menü", callback_data="m:main"),
                    ]
                ]
            )
            await safe_edit(query, text, markup)
            return

        if data == "n:overview":
            await safe_edit(query, "⏳ Ağ bilgisi okunuyor…")
            public_ip = await asyncio.to_thread(read_public_ip)
            text = await asyncio.to_thread(network_report_sync, public_ip)
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
            await safe_edit(query, "⏳ Disk bilgisi okunuyor…")
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

        if data == "p:top":
            await safe_edit(query, "⏳ Süreçler örnekleniyor…")
            text = await asyncio.to_thread(top_processes_sync)
            markup = InlineKeyboardMarkup(
                [
                    [
                        InlineKeyboardButton("🔄 Yenile", callback_data="p:top"),
                        InlineKeyboardButton("⬅️ Ana menü", callback_data="m:main"),
                    ]
                ]
            )
            await safe_edit(query, text, markup)
            return

        if data == "a:menu":
            enabled = load_alerts_enabled()
            state_text = "AÇIK 🟢" if enabled else "KAPALI 🔴"
            text = (
                "<b>🔔 Otomatik uyarılar</b>\n\n"
                f"Durum: <b>{state_text}</b>\n\n"
                f"CPU ≥ %{CPU_LIMIT:g}\n"
                f"RAM ≥ %{RAM_LIMIT:g}\n"
                f"Disk ≥ %{DISK_LIMIT:g}\n"
                f"Sıcaklık ≥ {TEMP_LIMIT:g} °C\n"
                "İnternet kesintisi / geri gelmesi\n"
                "Genel IP değişimi\n"
                "Container start/stop/exited değişimleri\n"
                "Docker health değişimleri"
            )
            markup = InlineKeyboardMarkup(
                [
                    [
                        InlineKeyboardButton(
                            "🔕 Uyarıları kapat" if enabled else "🔔 Uyarıları aç",
                            callback_data="a:toggle",
                        )
                    ],
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
            await query.answer(
                "Uyarılar açıldı." if enabled else "Uyarılar kapatıldı.",
                show_alert=False,
            )
            # Menü yeniden çizilsin.
            state_text = "AÇIK 🟢" if enabled else "KAPALI 🔴"
            text = (
                "<b>🔔 Otomatik uyarılar</b>\n\n"
                f"Durum: <b>{state_text}</b>\n\n"
                f"CPU ≥ %{CPU_LIMIT:g}\n"
                f"RAM ≥ %{RAM_LIMIT:g}\n"
                f"Disk ≥ %{DISK_LIMIT:g}\n"
                f"Sıcaklık ≥ {TEMP_LIMIT:g} °C\n"
                "İnternet / genel IP / Docker durum değişimleri izleniyor."
            )
            markup = InlineKeyboardMarkup(
                [
                    [
                        InlineKeyboardButton(
                            "🔕 Uyarıları kapat" if enabled else "🔔 Uyarıları aç",
                            callback_data="a:toggle",
                        )
                    ],
                    [InlineKeyboardButton("⬅️ Ana menü", callback_data="m:main")],
                ]
            )
            await safe_edit(query, text, markup)
            return

        if data.startswith("d:list:"):
            page = int(data.rsplit(":", 1)[1])
            await safe_edit(query, "⏳ Docker listesi okunuyor…")
            containers = await asyncio.to_thread(list_containers_sync)
            text = (
                f"<b>🐳 Docker</b>\n\n"
                f"Toplam container: <b>{len(containers)}</b>\n"
                "Detay için bir container seç:"
            )
            await safe_edit(query, text, docker_list_markup(containers, page))
            return

        if data.startswith("d:view:"):
            container_id = data.split(":", 2)[2]
            await safe_edit(query, "⏳ Container bilgisi okunuyor…")
            cid, text = await asyncio.to_thread(container_details_sync, container_id)
            c = await asyncio.to_thread(docker_client.containers.get, cid)
            c.reload()
            await safe_edit(query, text, container_buttons(cid, c.status))
            return

        if data.startswith("d:stats:"):
            container_id = data.split(":", 2)[2]
            await safe_edit(query, "⏳ Docker stats alınıyor…")
            text = await asyncio.to_thread(container_stats_sync, container_id)
            markup = InlineKeyboardMarkup(
                [
                    [
                        InlineKeyboardButton(
                            "🔄 Yenile", callback_data=f"d:stats:{container_id}"
                        ),
                        InlineKeyboardButton(
                            "⬅️ Container", callback_data=f"d:view:{container_id}"
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
                        InlineKeyboardButton("🔄 Yenile", callback_data=f"d:logs:{cid}"),
                        InlineKeyboardButton("⬅️ Container", callback_data=f"d:view:{cid}"),
                    ]
                ]
            )
            await safe_edit(query, text, markup)
            return

        if data.startswith("d:act:"):
            _, _, action, container_id = data.split(":", 3)
            c = await asyncio.to_thread(docker_client.containers.get, container_id)
            c.reload()

            if action == "start":
                text = await asyncio.to_thread(
                    container_action_sync,
                    container_id,
                    action,
                )
                markup = InlineKeyboardMarkup(
                    [[InlineKeyboardButton("⬅️ Container", callback_data=f"d:view:{container_id}")]]
                )
                await safe_edit(query, text, markup)
                return

            action_label = "durdurmak" if action == "stop" else "yeniden başlatmak"
            text = (
                f"⚠️ <b>{html.escape(c.name)}</b> container'ını "
                f"<b>{action_label}</b> istediğine emin misin?"
            )
            markup = InlineKeyboardMarkup(
                [
                    [
                        InlineKeyboardButton(
                            "✅ Evet", callback_data=f"d:do:{action}:{container_id}"
                        ),
                        InlineKeyboardButton(
                            "❌ Vazgeç", callback_data=f"d:view:{container_id}"
                        ),
                    ]
                ]
            )
            await safe_edit(query, text, markup)
            return

        if data.startswith("d:do:"):
            _, _, action, container_id = data.split(":", 3)
            await safe_edit(query, "⏳ Docker işlemi uygulanıyor…")
            text = await asyncio.to_thread(
                container_action_sync,
                container_id,
                action,
            )
            markup = InlineKeyboardMarkup(
                [[InlineKeyboardButton("⬅️ Docker", callback_data="d:list:0")]]
            )
            await safe_edit(query, text, markup)
            return

        if data == "h:menu" and HOST_CONTROL_ENABLED:
            text = (
                "<b>⚡ Raspberry Pi host yönetimi</b>\n\n"
                "Bu işlemler container dışındaki gerçek Raspberry Pi'yi etkiler.\n"
                "Her kritik işlem ikinci onay ister."
            )
            markup = InlineKeyboardMarkup(
                [
                    [
                        InlineKeyboardButton(
                            "🔁 Raspberry Pi reboot",
                            callback_data="h:confirm:reboot",
                        )
                    ],
                    [
                        InlineKeyboardButton(
                            "⏻ Raspberry Pi kapat",
                            callback_data="h:confirm:shutdown",
                        )
                    ],
                    [
                        InlineKeyboardButton(
                            "🐳 Docker servisini restart",
                            callback_data="h:confirm:restart-docker",
                        )
                    ],
                    [InlineKeyboardButton("⬅️ Ana menü", callback_data="m:main")],
                ]
            )
            await safe_edit(query, text, markup)
            return

        if data.startswith("h:confirm:") and HOST_CONTROL_ENABLED:
            action = data.split(":", 2)[2]
            labels = {
                "reboot": "Raspberry Pi'yi yeniden başlatmak",
                "shutdown": "Raspberry Pi'yi tamamen kapatmak",
                "restart-docker": "Docker servisini yeniden başlatmak",
            }
            if action not in labels:
                raise ValueError("Geçersiz host işlemi")
            text = (
                "⚠️ <b>Son onay</b>\n\n"
                f"{labels[action]} üzeresin.\n"
                "Devam edilsin mi?"
            )
            markup = InlineKeyboardMarkup(
                [
                    [
                        InlineKeyboardButton(
                            "✅ Onayla",
                            callback_data=f"h:do:{action}",
                        ),
                        InlineKeyboardButton(
                            "❌ Vazgeç",
                            callback_data="h:menu",
                        ),
                    ]
                ]
            )
            await safe_edit(query, text, markup)
            return

        if data.startswith("h:do:") and HOST_CONTROL_ENABLED:
            action = data.split(":", 2)[2]
            # Reboot/shutdown sırasında bot bağlantısı kesilebileceği için kullanıcıya
            # önce görünür bir durum mesajı bırak.
            await safe_edit(
                query,
                "⚡ Host komutu gönderiliyor. Cihaz/servis kısa süre erişilemez olabilir…",
            )
            result = await asyncio.to_thread(run_host_action_sync, action)
            markup = InlineKeyboardMarkup(
                [[InlineKeyboardButton("⬅️ Ana menü", callback_data="m:main")]]
            )
            await safe_edit(query, html.escape(result), markup)
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
    except (DockerException, RuntimeError, ValueError) as exc:
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


# ----------------------------
# İzleme / uyarılar
# ----------------------------

async def send_alert(
    context: ContextTypes.DEFAULT_TYPE,
    key: str,
    active: bool,
    active_message: str,
    recovery_message: str,
) -> None:
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
    return {
        "cpu": psutil.cpu_percent(interval=0.45),
        "ram": psutil.virtual_memory().percent,
        "disk": psutil.disk_usage(disk_target).percent,
        "temp": cpu_temp(),
    }


async def monitor_docker_changes(context: ContextTypes.DEFAULT_TYPE) -> None:
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

            if old.get("health") != info.get("health") and info.get("health") and alerts_enabled:
                icon = "✅" if info["health"] == "healthy" else "🩺"
                await context.bot.send_message(
                    ALLOWED_USER_ID,
                    f"{icon} <b>{html.escape(info['name'])}</b> health: "
                    f"<b>{html.escape(info['health'])}</b>",
                    parse_mode=ParseMode.HTML,
                )

            if int(info.get("restart_count", 0)) > int(old.get("restart_count", 0)) and alerts_enabled:
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
                    f"🗑 Docker container artık görünmüyor: "
                    f"<b>{html.escape(old.get('name', cid))}</b>",
                    parse_mode=ParseMode.HTML,
                )

    docker_monitor_state = current


async def monitor(context: ContextTypes.DEFAULT_TYPE) -> None:
    try:
        metrics_task = asyncio.to_thread(monitor_metrics_sync)
        ip_task = asyncio.to_thread(read_public_ip)
        metrics, public_ip = await asyncio.gather(metrics_task, ip_task)

        cpu = float(metrics["cpu"])
        ram = float(metrics["ram"])
        disk = float(metrics["disk"])
        temp = metrics["temp"]

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

        await send_alert(
            context,
            "internet",
            public_ip is None,
            "🌐 <b>İnternet erişimi kesildi</b> veya dış IP servisine ulaşılamıyor.",
            "✅ <b>İnternet erişimi geri geldi.</b>",
        )

        if public_ip:
            ip_file = STATE_DIR / "public_ip.txt"
            old_ip = read_text(ip_file)
            if old_ip and old_ip != public_ip and load_alerts_enabled():
                await context.bot.send_message(
                    ALLOWED_USER_ID,
                    "🔄 <b>Genel IP değişti</b>\n"
                    f"Eski: <code>{html.escape(old_ip)}</code>\n"
                    f"Yeni: <code>{html.escape(public_ip)}</code>",
                    parse_mode=ParseMode.HTML,
                )
            ip_file.write_text(public_ip)

        await monitor_docker_changes(context)

    except Exception:
        logger.exception("Monitor döngüsü hatası")


async def post_init(application: Application) -> None:
    global docker_monitor_state

    await application.bot.set_my_commands(
        [
            BotCommand("menu", "Ana yönetim menüsü"),
            BotCommand("durum", "Sistem durum raporu"),
            BotCommand("docker", "Docker container listesi"),
            BotCommand("ip", "Yerel ve genel IP"),
            BotCommand("yardim", "Yardım"),
        ]
    )

    docker_monitor_state = await asyncio.to_thread(docker_state_snapshot_sync)

    await application.bot.send_message(
        ALLOWED_USER_ID,
        "<b>✅ Pi Assistant Loruv v2 çalışıyor.</b>\n"
        "Raspberry Pi veya bot container'ı yeniden başlatılmış olabilir.",
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
        name="host-monitor",
    )


async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    logger.exception("Telegram update hatası", exc_info=context.error)


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
    app.add_handler(CommandHandler("ip", ip_command))
    app.add_handler(CommandHandler("yardim", help_command))
    app.add_handler(CallbackQueryHandler(callback_router))
    app.add_error_handler(error_handler)

    app.run_polling(drop_pending_updates=True)


if __name__ == "__main__":
    main()
