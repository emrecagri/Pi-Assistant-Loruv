import asyncio
import logging
import os
import socket
import time
from pathlib import Path
from typing import Optional

import docker
import psutil
from docker.errors import DockerException, NotFound
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes

BOT_TOKEN = os.environ["BOT_TOKEN"]
ALLOWED_USER_ID = int(os.environ["ALLOWED_USER_ID"])

CHECK_INTERVAL = int(os.getenv("CHECK_INTERVAL", "60"))
CPU_LIMIT = float(os.getenv("CPU_LIMIT", "90"))
RAM_LIMIT = float(os.getenv("RAM_LIMIT", "90"))
DISK_LIMIT = float(os.getenv("DISK_LIMIT", "90"))
TEMP_LIMIT = float(os.getenv("TEMP_LIMIT", "75"))
PUBLIC_IP_CHECK_URL = os.getenv("PUBLIC_IP_CHECK_URL", "https://api.ipify.org")
STATE_DIR = Path("/app/data")
STATE_DIR.mkdir(parents=True, exist_ok=True)

logging.basicConfig(
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger("pi-assistant-loruv")

try:
    docker_client = docker.from_env()
except DockerException:
    docker_client = None

alert_state = {
    "cpu": False,
    "ram": False,
    "disk": False,
    "temp": False,
    "internet": False,
}


def is_authorized(update: Update) -> bool:
    user = update.effective_user
    return bool(user and user.id == ALLOWED_USER_ID)


async def reject_if_unauthorized(update: Update) -> bool:
    if is_authorized(update):
        return False
    if update.effective_message:
        await update.effective_message.reply_text("Bu botu kullanma yetkin yok.")
    return True


def cpu_temp() -> Optional[float]:
    candidates = [
        Path("/sys/class/thermal/thermal_zone0/temp"),
        Path("/host/sys/class/thermal/thermal_zone0/temp"),
    ]
    for path in candidates:
        try:
            return int(path.read_text().strip()) / 1000
        except (OSError, ValueError):
            continue
    return None


def uptime_text() -> str:
    seconds = int(time.time() - psutil.boot_time())
    days, seconds = divmod(seconds, 86400)
    hours, seconds = divmod(seconds, 3600)
    minutes, _ = divmod(seconds, 60)
    return f"{days} gün {hours} saat {minutes} dakika"


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
    import urllib.request
    try:
        with urllib.request.urlopen(PUBLIC_IP_CHECK_URL, timeout=10) as response:
            return response.read().decode().strip()
    except Exception:
        return None


def system_status() -> str:
    cpu = psutil.cpu_percent(interval=1)
    ram = psutil.virtual_memory()
    disk = psutil.disk_usage("/")
    temp = cpu_temp()
    net = psutil.net_io_counters()
    temp_line = f"{temp:.1f} °C" if temp is not None else "Okunamadı"

    return (
        "🖥️ Raspberry Pi durum raporu\n\n"
        f"🧠 CPU: %{cpu:.1f}\n"
        f"💾 RAM: %{ram.percent:.1f} ({ram.used / 1024**3:.1f}/{ram.total / 1024**3:.1f} GB)\n"
        f"🗄️ Disk: %{disk.percent:.1f} ({disk.used / 1024**3:.1f}/{disk.total / 1024**3:.1f} GB)\n"
        f"🌡️ Sıcaklık: {temp_line}\n"
        f"⬆️ Gönderilen: {net.bytes_sent / 1024**3:.2f} GB\n"
        f"⬇️ Alınan: {net.bytes_recv / 1024**3:.2f} GB\n"
        f"🏠 Yerel IP: {local_ip()}\n"
        f"⏱️ Çalışma süresi: {uptime_text()}"
    )


def docker_list_text() -> str:
    if docker_client is None:
        return "Docker bağlantısı kurulamadı."
    try:
        containers = docker_client.containers.list(all=True)
    except DockerException as exc:
        return f"Docker bilgisi alınamadı: {exc}"

    if not containers:
        return "Hiç container bulunamadı."

    lines = ["🐳 Docker container'ları\n"]
    for container in containers:
        icon = "🟢" if container.status == "running" else "🔴"
        image = container.image.tags[0] if container.image.tags else container.image.short_id
        lines.append(f"{icon} {container.name}\n   {container.status} | {image}")
    return "\n".join(lines)


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if await reject_if_unauthorized(update):
        return
    await update.message.reply_text(
        "✅ Pi Assistant aktif\n\n"
        "/durum - Sistem raporu\n"
        "/docker - Container listesi\n"
        "/baslat <ad> - Container başlat\n"
        "/durdur <ad> - Container durdur\n"
        "/yenidenbaslat <ad> - Container yeniden başlat\n"
        "/ip - Yerel ve genel IP\n"
        "/yardim - Komut listesi"
    )


async def durum(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if await reject_if_unauthorized(update):
        return
    await update.message.reply_text(system_status())


async def docker_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if await reject_if_unauthorized(update):
        return
    await update.message.reply_text(docker_list_text())


async def container_action(update: Update, context: ContextTypes.DEFAULT_TYPE, action: str) -> None:
    if await reject_if_unauthorized(update):
        return
    if not context.args:
        await update.message.reply_text(f"Kullanım: /{action} container_adi")
        return
    if docker_client is None:
        await update.message.reply_text("Docker bağlantısı kurulamadı.")
        return

    name = context.args[0]
    if name == os.getenv("HOSTNAME"):
        await update.message.reply_text("Bot kendi container'ı üzerinde bu işlemi yapamaz.")
        return

    try:
        container = docker_client.containers.get(name)
        if action == "baslat":
            container.start()
        elif action == "durdur":
            container.stop(timeout=15)
        elif action == "yenidenbaslat":
            container.restart(timeout=15)
        await update.message.reply_text(f"✅ {name}: {action} işlemi tamamlandı.")
    except NotFound:
        await update.message.reply_text(f"❌ '{name}' adında container bulunamadı.")
    except DockerException as exc:
        await update.message.reply_text(f"❌ Docker hatası: {exc}")


async def baslat(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await container_action(update, context, "baslat")


async def durdur(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await container_action(update, context, "durdur")


async def yenidenbaslat(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await container_action(update, context, "yenidenbaslat")


async def ip_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if await reject_if_unauthorized(update):
        return
    public_ip = await asyncio.to_thread(read_public_ip)
    await update.message.reply_text(
        f"🏠 Yerel IP: {local_ip()}\n"
        f"🌍 Genel IP: {public_ip or 'İnternet yok veya okunamadı'}"
    )


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await start(update, context)


async def send_alert(context: ContextTypes.DEFAULT_TYPE, key: str, active: bool, message: str) -> None:
    previous = alert_state[key]
    if active and not previous:
        await context.bot.send_message(ALLOWED_USER_ID, message)
    elif not active and previous:
        await context.bot.send_message(ALLOWED_USER_ID, f"✅ Normale döndü: {key}")
    alert_state[key] = active


async def monitor(context: ContextTypes.DEFAULT_TYPE) -> None:
    cpu = psutil.cpu_percent(interval=1)
    ram = psutil.virtual_memory().percent
    disk = psutil.disk_usage("/").percent
    temp = cpu_temp()

    await send_alert(context, "cpu", cpu >= CPU_LIMIT, f"⚠️ CPU kullanımı yüksek: %{cpu:.1f}")
    await send_alert(context, "ram", ram >= RAM_LIMIT, f"⚠️ RAM kullanımı yüksek: %{ram:.1f}")
    await send_alert(context, "disk", disk >= DISK_LIMIT, f"⚠️ Disk kullanımı yüksek: %{disk:.1f}")
    if temp is not None:
        await send_alert(context, "temp", temp >= TEMP_LIMIT, f"🔥 Sıcaklık yüksek: {temp:.1f} °C")

    public_ip = await asyncio.to_thread(read_public_ip)
    await send_alert(
        context,
        "internet",
        public_ip is None,
        "🌐 İnternet bağlantısı kesildi veya dış IP servisine ulaşılamıyor.",
    )

    if public_ip:
        ip_file = STATE_DIR / "public_ip.txt"
        old_ip = ip_file.read_text().strip() if ip_file.exists() else ""
        if old_ip and old_ip != public_ip:
            await context.bot.send_message(
                ALLOWED_USER_ID,
                f"🔄 Genel IP değişti\nEski: {old_ip}\nYeni: {public_ip}",
            )
        ip_file.write_text(public_ip)


async def post_init(application: Application) -> None:
    await application.bot.send_message(
        ALLOWED_USER_ID,
        "✅ Pi Assistant çalıştı. Raspberry Pi veya bot container'ı yeniden başlatılmış olabilir.",
    )
    application.job_queue.run_repeating(monitor, interval=CHECK_INTERVAL, first=10)


def main() -> None:
    app = (
        Application.builder()
        .token(BOT_TOKEN)
        .post_init(post_init)
        .build()
    )

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("durum", durum))
    app.add_handler(CommandHandler("docker", docker_cmd))
    app.add_handler(CommandHandler("baslat", baslat))
    app.add_handler(CommandHandler("durdur", durdur))
    app.add_handler(CommandHandler("yenidenbaslat", yenidenbaslat))
    app.add_handler(CommandHandler("ip", ip_command))
    app.add_handler(CommandHandler("yardim", help_command))

    app.run_polling(drop_pending_updates=True)


if __name__ == "__main__":
    main()
