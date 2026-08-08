# Pi Assistant Loruv V5

> Raspberry Pi, Linux host ve Docker ortamını Telegram üzerinden izlemek, yönetmek ve teşhis etmek için geliştirilmiş; güvenlik ve düşük SSD yazımı odaklı self-hosted yönetim botu.
>
> A security-conscious, SSD-friendly self-hosted Telegram assistant for monitoring, diagnosing and managing Raspberry Pi/Linux hosts and Docker environments.

---

## İçindekiler

### Türkçe

- [Proje Hakkında](#proje-hakkında)
- [V5 Final Özellikleri](#v5-final-özellikleri)
- [Telegram Komutları](#telegram-komutları)
- [Ana Menü](#ana-menü)
- [Gereksinimler](#gereksinimler)
- [Proje Yapısı](#proje-yapısı)
- [Telegram Botu Oluşturma](#telegram-botu-oluşturma)
- [Portainer Repository ile Kurulum](#portainer-repository-ile-kurulum-önerilen)
- [Git ile Lokal Kurulum](#git-ile-lokal-kurulum)
- [Host Araçlarını Etkinleştirme](#host-araçlarını-etkinleştirme)
- [Yapılandırma](#yapılandırma)
- [SSD Dostu Çalışma](#ssd-dostu-çalışma)
- [Güncelleme](#güncelleme)
- [Sorun Giderme](#sorun-giderme)
- [Güvenlik](#güvenlik)
- [Smoke Test](#smoke-test)

### English

- [About](#about)
- [V5 Final Features](#v5-final-features)
- [Telegram Commands](#telegram-commands)
- [Requirements](#requirements)
- [Portainer Repository Deployment](#portainer-repository-deployment-recommended)
- [Local Git Deployment](#local-git-deployment)
- [Optional Host Tools](#optional-host-tools)
- [Configuration](#configuration-1)
- [SSD-Friendly Design](#ssd-friendly-design)
- [Security](#security-1)

---

# Türkçe

## Proje Hakkında

**Pi Assistant Loruv V5 FINAL**, Raspberry Pi veya uyumlu bir Linux sunucuyu Telegram üzerinden yönetmek için hazırlanmış kapsamlı bir self-hosted yardımcı uygulamadır.

V5 yalnızca birkaç sistem metriği gösteren bir bot değildir. Raspberry Pi host işletim sistemi, Docker Engine, gerçek host süreçleri, ağ portları, SSD/SMART, systemd servisleri, internet bağlantısı, dosya indirme/yükleme ve kritik host işlemlerini tek Telegram arayüzünde birleştirir.

V5 tasarımında üç temel ilke vardır:

1. **Güçlü yönetim:** Günlük sunucu yönetiminde SSH ihtiyacını azaltmak.
2. **Dar yetki:** Telegram üzerinden sınırsız shell erişimi vermemek.
3. **SSD dostu çalışma:** Sürekli telemetry ve gereksiz log yazımlarını mümkün olduğunca azaltmak.

Bot varsayılan olarak yalnız `ALLOWED_USER_ID` ile tanımlanan Telegram hesabından gelen işlemleri kabul eder.

---

# V5 Final Özellikleri

## 📊 Raspberry Pi / Sistem İzleme

Telegram üzerinden aşağıdaki host bilgileri görüntülenebilir:

- Raspberry Pi modeli
- Hostname
- İşletim sistemi
- Kernel
- Mimari
- Sistem uptime
- Son boot zamanı
- CPU kullanımı
- Fiziksel çekirdek / logical thread sayısı
- CPU frekansı
- Load average: 1 / 5 / 15 dakika
- CPU sıcaklığı
- RAM kullanımı
- Available RAM
- Cache / buffer / shared memory
- Swap kullanımı
- Disk kapasitesi
- Kullanılan ve boş disk alanı
- Disk read/write I/O
- Yerel IP
- Dış IP
- Toplam ağ RX/TX

Sistem değerleri belirlenen eşikleri aştığında Telegram bildirimi gönderilebilir.

---

## 🩺 Sağlık Merkezi

Tek bir ekranda genel sunucu sağlığı görüntülenebilir:

- CPU
- RAM
- Swap
- Disk
- Sıcaklık
- Load
- İnternet bağlantısı
- Docker daemon
- Host process görünürlüğü
- Opsiyonel SMART / güç / systemd durumu

Amaç, sunucuda sorun olup olmadığını tek bakışta görebilmektir.

---

## ⚙️ Gerçek Host Süreç Yöneticisi

V5'in önemli değişikliklerinden biri process görünürlüğüdür.

Container içinde çalışan standart `psutil`, normalde yalnız container namespace'ini görebilir. V5 compose dosyası gerçek host `/proc` ağacını salt okunur bağlar:

```yaml
- /proc:/host/proc:ro
```

Bot ise host process bilgileri için:

```python
psutil.PROCFS_PATH = "/host/proc"
```

kullanır.

Bu sayede yalnız Pi Assistant process'i değil, Raspberry Pi üzerinde çalışan gerçek host süreçleri görülebilir.

### Süreç özellikleri

- Toplam PID sayısı
- Toplam thread sayısı
- Running / sleeping / zombie vb. durum özeti
- CPU kullanımına göre sıralama
- RAM kullanımına göre sıralama
- Disk I/O kullanımına göre sıralama
- PID ile arama
- Process adı ile arama
- Command line ile arama
- Sayfalı process listesi

### PID detay ekranı

- PID
- PPID
- Process adı
- Kullanıcı
- Process status
- CPU kullanımı
- CPU core
- Nice değeri
- RAM yüzdesi
- RSS
- VMS
- Thread sayısı
- Disk read/write
- Açık dosya sayısı
- INET bağlantı sayısı
- Başlangıç zamanı
- Process uptime
- Executable yolu
- CWD
- Command line

Bot başlangıçta host process görünürlüğünü ayrıca kontrol eder.

---

# 🐳 Docker Yönetimi

V5 kapsamlı bir Docker yönetim merkezi içerir.

### Container yönetimi

- Tüm container'ları listeleme
- Running / stopped / paused durumları
- Health durumu
- Image bilgisi
- Container ID
- Restart count
- Restart policy
- Başlangıç zamanı
- Container PID
- OOM durumu
- Portlar
- Container IP adresleri
- Mount'lar
- Resource limitleri
- Start
- Stop
- Restart
- Pause
- Resume

Stop, restart ve diğer kritik işlemler ikinci onay ister.

### Container kaynak kullanımı

- CPU
- RAM
- Network RX
- Network TX
- Block read
- Block write

Tüm çalışan container'lar merkezi kaynak ekranında karşılaştırılabilir. Bu özellik özellikle SSD'ye fazla yazan container'ı tespit etmek için kullanışlıdır.

### Container logları

- Son logları Telegram içinde görüntüleme
- Logları `.txt` dosyası olarak Telegram'a gönderme

---

## 🔍 Tek Tuşla Tüm Docker Güncelleme Kontrolü

Docker menüsünde bütün container image'ları tek seferde kontrol edilebilir.

Akış:

1. Container'ın kullandığı repository/tag belirlenir.
2. Registry'deki image pull edilir.
3. Mevcut image ID ile yeni image ID karşılaştırılır.
4. Her container için durum raporlanır.

Olası durumlar:

- ✅ Güncel
- 🟠 Güncelleme var
- ⚪ Kontrol edilemedi
- ⏭ Yoksayıldı

**Güncelleme kontrolü sırasında çalışan container değiştirilmez.**

Güncelleme bulunan container'lar daha sonra ayrı bir toplu güncelleme işlemiyle uygulanabilir.

### Toplu güncelleme güvenliği

- Ayrı ikinci onay
- Süreli ve tek kullanımlık confirmation token
- Container'ları sırayla güncelleme
- Health kontrolü
- Hata durumunda rollback denemesi
- İstenirse ilk hatada toplu işlemi durdurma
- `pi-assistant-loruv` varsayılan olarak kendi kendini güncellemez
- Riskli generic recreate senaryolarında işlem reddedilebilir

Yoksayılacak container'lar:

```env
UPDATE_IGNORE_CONTAINERS=pi-assistant-loruv,my-local-app
```

> Güncelleme kontrolü yeni image katmanlarını gerçekten indirebilir. Bu nedenle registry kontrolü SSD ve internet trafiği oluşturabilir.

---

## 🔌 Docker + Host Port Merkezi

V5 yalnız Docker port mapping bilgisini değil, gerçek host listening socket'lerini de gösterebilir.

### Docker portları

- Container adı
- Host IP
- Host port
- Container port
- TCP / UDP
- Yayınlanmış portlar
- `EXPOSE` edilmiş ancak yayınlanmamış portlar
- `0.0.0.0` / `::` binding uyarısı

Örnek:

```text
uptime-kuma
0.0.0.0:3002 → 3001/tcp
```

### Host listening portları

- Listening IP
- Port
- TCP / UDP
- PID
- Process adı

Bu sayede Docker dışında çalışan host servisleri de görülebilir.

> `0.0.0.0` veya `::` üzerinde dinleyen bir servis tüm interface'lere bind edilmiştir; bu tek başına internetten erişilebilir olduğu anlamına gelmez. Firewall, router ve NAT ayrıca değerlendirilmelidir.

---

## 💽 Docker Disk ve Temizlik Merkezi

- Docker image disk kullanımı
- Container writable layer kullanımı
- Volume kullanımı
- Build cache
- Dangling image'lar
- Kullanılmayan image'lar
- Stopped container'lar
- Kullanılmayan network'ler
- Kullanılmayan volume'ler

Temizlik işlemleri ayrı ayrı çalıştırılır. Veri kaybı riski daha yüksek olan volume cleanup ayrıca güçlü uyarı ve onay ister.

---

# 💿 SSD / SMART

Host araçları etkinleştirildiğinde SMART bilgileri Telegram'dan görüntülenebilir.

Desteklenen bilgiler diske ve USB/SATA/NVMe bridge'e göre değişebilir.

V5 aşağıdaki değerleri okuyabilir:

- Disk device
- Model
- Seri numarası
- Firmware
- Protokol
- Kapasite
- SMART overall health
- Sıcaklık
- Power-on hours
- Power cycles
- Reallocated sectors
- Pending sectors
- Offline uncorrectable
- UDMA CRC errors
- NVMe percentage used
- Available spare
- Media/data integrity errors
- Unsafe shutdowns
- NVMe toplam okuma/yazma tahmini

### SMART işlemleri

- SMART detay ekranı
- `smartctl -x` tam raporunu `.txt` gönderme
- SMART short self-test
- SMART long self-test
- Opsiyonel periyodik SMART alarmı

Varsayılan olarak otomatik SMART sorgulaması kapalıdır:

```env
SMART_MONITOR_INTERVAL=0
```

Bu ayar özellikle bazı USB disklerin uyku davranışını gereksiz etkilememek için bilinçli olarak seçilmiştir.

---

# ⚡ Raspberry Pi Güç / Throttling

Host helper ve `vcgencmd` mevcut olduğunda:

- Undervoltage
- Geçmiş undervoltage
- Throttling
- Geçmiş throttling
- Frequency cap
- Geçmiş frequency cap
- Soft temperature limit
- Core voltage
- ARM clock
- Firmware bilgisi

izlenebilir.

Geçmiş firmware bitleri sayesinde kısa süreli undervoltage veya throttling olayları da tespit edilebilir.

---

# 🌐 Ağ ve İnternet

- Yerel IP
- Dış IP
- Interface listesi
- IPv4 / IPv6
- MTU
- Link hızı
- RX/TX
- Packet count
- Error/drop
- Gateway testi
- `1.1.1.1` bağlantı testi
- `8.8.8.8` bağlantı testi
- DNS çözümleme testi
- Packet loss
- Ortalama gecikme
- Speedtest
- İnternet gitti / geldi alarmı
- Dış IP değişikliği alarmı

---

# 📥 URL ile Raspberry Pi'ye Dosya İndirme

Telegram üzerinden doğrudan URL göndererek dosya sunucuya indirilebilir.

Varsayılan download dizini:

```text
/srv/downloads
```

### İndirme özellikleri

- HTTP / HTTPS
- Metadata kontrolü
- Dosya adı
- Content type
- Dosya boyutu
- Maksimum indirme boyutu
- Minimum boş SSD alanı kontrolü
- Streaming download
- `.part` geçici dosyası
- Başarılı indirmede atomic rename
- SHA-256
- İlerleme yüzdesi
- Download hızı
- ETA
- Aynı isim varsa `-2`, `-3` şeklinde yeni isim

### SSRF koruması

URL downloader, Telegram botunun iç ağ tarama aracı haline gelmemesi için kısıtlanmıştır.

Varsayılan olarak:

- Yalnız HTTP/HTTPS kabul edilir
- URL içi username/password reddedilir
- localhost reddedilir
- `.local` hedefler reddedilir
- loopback reddedilir
- private/LAN IP'ler reddedilir
- link-local reddedilir
- CGNAT/non-global hedefler reddedilir
- Redirect hedefleri tekrar doğrulanır
- Varsayılan izinli portlar yalnız 80 ve 443'tür

```env
DOWNLOAD_ALLOWED_PORTS=80,443
MAX_DOWNLOAD_SIZE_GB=10
DOWNLOAD_MIN_FREE_GB=2
```

---

# 📁 Telegram Dosya Yöneticisi

Botun yazabildiği alanlar bilinçli olarak sınırlandırılmıştır:

```text
/srv/downloads
/srv/uploads
```

Dosya yöneticisi ile:

- Dosyaları listeleme
- Sayfalama
- Dosya boyutu
- Son değiştirilme zamanı
- SHA-256 hesaplama
- Dosyayı Telegram'a gönderme
- Dosya silme
- Download alanını temizleme
- Upload alanını temizleme
- `/srv` altında en büyük dosyaları salt okunur görüntüleme

mümkündür.

`/etc`, `/boot`, `/usr` gibi kritik host alanları Telegram dosya yöneticisinin silme alanı değildir.

---

## 📎 Telegram → Raspberry Pi Dosya Yükleme

Telegram botuna document gönderildiğinde izin verilen boyuttaysa:

```text
/srv/uploads
```

altına kaydedilir.

Bot:

- Dosya adını
- Boyutunu
- SHA-256 değerini

raporlar ve dosyayı dosya yöneticisine ekler.

Varsayılan bot limitleri:

```env
TELEGRAM_SEND_MAX_MB=49
TELEGRAM_UPLOAD_MAX_MB=19
```

Bu değerler environment değişkenleriyle değiştirilebilir; gerçek kullanılabilir limit Telegram Bot API ve kullanılan altyapının sınırlarına bağlıdır.

---

# 🧩 systemd Yönetimi

Host araçları etkinleştirildiğinde:

- systemd servis listesi
- Active state
- Sub state
- Main PID
- Memory
- CPU time
- Restart count
- Result
- Unit file state
- Failed servisler
- Journal logları
- Journal'ı `.txt` gönderme
- Failed / recovered alarmı

kullanılabilir.

### Servis restart güvenliği

Telegram'dan her servis restart edilemez.

İzin verilen servisler host üzerindeki allowlist dosyasında tanımlanır:

```text
/etc/pi-assistant-systemd-allowlist
```

Örnek:

```text
docker.service
tailscaled.service
smbd.service
nmbd.service
```

---

# 🧰 Bakım ve Güvenlik

## Bakım ekranı

- Bekleyen apt paket sayısı
- Reboot required
- Failed systemd servisleri
- Kernel
- Boot zamanı

## Güvenlik ekranı

- Aktif login kullanıcıları
- Son login kayıtları
- Son 24 saatte başarısız SSH authentication sayısı
- Host listening portlarıyla birlikte güvenlik değerlendirmesi

---

# 🕒 Olay Geçmişi

V5 sürekli CPU/RAM telemetry verisini disk üzerindeki bir veritabanına yazmaz.

Yalnız önemli olaylar küçük ve sınırlandırılmış bir geçmişte tutulur:

- Bot başlangıcı
- CPU/RAM/swap/disk/sıcaklık alarmı
- İnternet gitti / geldi
- Dış IP değişti
- Docker status değişikliği
- Docker health değişikliği
- Container restart
- Docker update
- Dosya indirme
- Dosya silme
- SMART işlemleri
- Host güç olayları

Varsayılan:

```env
EVENT_HISTORY_MAX=200
```

---

# 🔔 Otomatik Bildirimler

V5 aşağıdaki durumlarda Telegram bildirimi gönderebilir:

- Bot başladı
- CPU yüksek
- RAM yüksek
- Swap yüksek
- Disk doluluk yüksek
- CPU sıcaklığı yüksek
- Load yüksek
- İnternet kesildi
- İnternet geri geldi
- Dış IP değişti
- Container status değişti
- Container health değişti
- Container restart count arttı
- Undervoltage oluştu
- Throttling oluştu
- Frequency cap oluştu
- systemd servisi failed oldu
- systemd servisi toparlandı
- SMART sağlık sorunu tespit edildi
- İzlenen metrik normale döndü

Uyarılar Telegram menüsünden açılıp kapatılabilir.

---

# ⚡ Host Yönetimi

`HOST_CONTROL_ENABLED=true` olduğunda güvenli host helper üzerinden:

- Raspberry Pi reboot
- Raspberry Pi shutdown
- Docker daemon restart
- Allowlist içindeki systemd servisini restart
- SMART short test
- SMART long test

çalıştırılabilir.

Bu özellik rastgele shell çalıştırmaz.

Kritik işlemler Telegram'da ikinci onay ister.

---

# 🔐 Kritik İşlem Onayı

Aşağıdaki işlemler tek kullanımlık ve süreli confirmation token kullanır:

- Container stop
- Container restart
- Container pause
- Container recreate/update
- Toplu Docker update
- Docker cleanup
- Volume cleanup
- Dosya silme
- Dosya alanını temizleme
- Olay geçmişini temizleme
- systemd restart
- SMART test
- Raspberry Pi reboot
- Raspberry Pi shutdown
- Docker daemon restart

Varsayılan geçerlilik:

```env
CONFIRM_TTL=45
```

Eski bir Telegram mesajındaki `Onayla` butonu daha sonra tekrar kullanılamaz.

---

# Telegram Komutları

| Komut | Açıklama |
| --- | --- |
| `/start` | Botu başlatır ve ana menüyü gösterir |
| `/menu` | Ana yönetim menüsü |
| `/durum` | Raspberry Pi / host sistem raporu |
| `/docker` | Docker yönetim merkezi |
| `/surecler` | Gerçek host süreçleri |
| `/ag` | Ağ ve interface raporu |
| `/depolama` | Disk ve I/O raporu |
| `/ip` | Yerel ve dış IP |
| `/portlar` | Docker + host listening portları |
| `/dosyalar` | Download/upload dosya yöneticisi |
| `/olaylar` | Son önemli olaylar |
| `/araclar` | Raspberry Pi güç / SMART / systemd araçları |
| `/servisler` | systemd servisleri |
| `/smart` | SSD / SMART sağlık ekranı |
| `/speedtest` | İnternet hız testi |
| `/rapor` | Tanılama ve log `.txt` raporları |
| `/yardim` | Yardım / ana menü |

V5'in asıl kullanım biçimi komut yazmaktan çok Telegram **inline button** menüleridir.

---

# Ana Menü

Örnek V5 ana menüsü:

```text
🤖 Pi Assistant Loruv V5 FINAL

📊 Sistem        🐳 Docker
⚙️ Süreçler      🔌 Portlar
🌐 Ağ            💽 Depolama
📁 Dosyalar      📥 URL İndir
🧩 Servisler     💿 SSD / SMART
🧰 Host          🩺 Sağlık
📄 Raporlar      🕒 Olaylar
🔔 Uyarılar      ℹ️ Hakkında

        ⚡ Host Yönetimi
        🔄 Yenile
```

Bazı butonlar `HOST_TOOLS_ENABLED` veya `HOST_CONTROL_ENABLED` kapalıysa gizlenebilir veya pasif olabilir.

---

# Gereksinimler

Temel kullanım:

- Raspberry Pi veya uyumlu Linux host
- 64-bit Linux önerilir
- Docker Engine
- Docker Compose plugin
- İnternet bağlantısı
- Telegram hesabı
- BotFather ile oluşturulmuş Telegram botu
- Portainer opsiyonel ancak önerilir

Host araçları için opsiyonel:

- OpenSSH server
- `smartmontools`
- Raspberry Pi üzerinde `vcgencmd`
- `systemd` / `journalctl`
- Ookla `speedtest` veya uyumlu `speedtest-cli`

Docker kontrolü:

```bash
docker --version
docker compose version
sudo systemctl status docker
```

---

# Proje Yapısı

V5 repository yapısı:

```text
Pi-Assistant-Loruv/
├── bot.py
├── compose.yml
├── Dockerfile
├── requirements.txt
├── VERSION
├── README.md
├── LICENSE
├── .env.example
├── .gitignore
├── .dockerignore
│
├── host/
│   ├── install-host-helper.sh
│   ├── pi-assistant-host
│   ├── pi-assistant-ssh-gateway
│   ├── pi-assistant-systemd-allowlist.example
│   └── piassistant-sudoers
│
├── scripts/
│   └── smoke-test.sh
│
└── secrets/
    └── .gitkeep
```

> Repository'nizde compose dosyasının adı farklıysa Portainer `Compose path` alanında gerçek dosya adını kullanın.

---

# Telegram Botu Oluşturma

## 1. BotFather

Telegram'da:

```text
@BotFather
```

botunu açın.

## 2. Bot oluşturun

```text
/newbot
```

BotFather size bir token verir.

Örnek format:

```text
123456789:AAxxxxxxxxxxxxxxxxxxxxxxxxxxxx
```

Bu değer `BOT_TOKEN` olarak kullanılır.

## 3. Telegram User ID

Kendi numeric Telegram kullanıcı ID'nizi öğrenin.

Örnek:

```text
123456789
```

Bu değer `ALLOWED_USER_ID` olarak kullanılır.

> Bot tokenını README, compose veya public GitHub commit'ine yazmayın.

---

# Portainer Repository ile Kurulum — Önerilen

V5 için önerilen yöntem Portainer'ın repository deploy özelliğidir.

Avantajları:

- Portainer stack üzerinde **Total control**
- Repository'den doğrudan build
- GitHub güncellemesinden sonra Pull and redeploy
- Token'ın repository dışında tutulması
- Lokal proje dosyası yönetme ihtiyacının azalması

## 1. Eski stack varsa kaldırın

Portainer:

```text
Stacks
→ eski Pi Assistant stack
→ Delete / Remove
```

Eski container kalmışsa:

```bash
docker rm -f pi-assistant-loruv
```

Kalıcı bind-mount dizinlerini silmeyin.

## 2. Host dizinlerini hazırlayın

Raspberry Pi üzerinde:

```bash
sudo mkdir -p /srv/docker/pi-assistant
sudo mkdir -p /srv/downloads
sudo mkdir -p /srv/uploads
```

İsterseniz kullanıcı yetkisi:

```bash
sudo chown -R "$USER":"$USER" /srv/docker/pi-assistant /srv/downloads /srv/uploads
```

## 3. Portainer'da Repository seçin

```text
Stacks
→ Add stack
→ Repository
```

Ayarlar:

| Alan | Değer |
| --- | --- |
| Name | `pi-assistant-loruv` |
| Authentication | Public repo ise `OFF` |
| Repository URL | `https://github.com/emrecagri/Pi-Assistant-Loruv` |
| Skip TLS Verification | `OFF` |
| Repository reference | `refs/heads/main` |
| Compose path | `compose.yml` |
| GitOps updates | İlk kurulumda `OFF` önerilir |

> Repository kökündeki compose dosyanız `compose.yaml` ise `Compose path` alanına `compose.yaml` yazın. Portainer'daki değer dosya adıyla birebir aynı olmalıdır.

## 4. Environment Variables

Portainer sayfasında:

```text
Environment variables
```

alanına minimum olarak yalnız:

```env
BOT_TOKEN=GERCEK_TELEGRAM_BOT_TOKEN
ALLOWED_USER_ID=GERCEK_TELEGRAM_USER_ID
```

girin.

Compose içinde bunlar:

```yaml
BOT_TOKEN: "${BOT_TOKEN}"
ALLOWED_USER_ID: "${ALLOWED_USER_ID}"
```

şeklinde alınır.

Diğer ayarlar compose içindeki `${VARIABLE:-default}` değerleriyle otomatik varsayılan kullanabilir.

Örneğin:

```yaml
CHECK_INTERVAL: "${CHECK_INTERVAL:-60}"
TEMP_LIMIT: "${TEMP_LIMIT:-75}"
LOG_LEVEL: "${LOG_LEVEL:-WARNING}"
```

Daha sonra yalnız değiştirmek istediğiniz değerleri Portainer Environment Variables'a ekleyebilirsiniz.

## 5. İlk deploy

İlk kurulumda şu iki özellik kapalı kalabilir:

```env
HOST_TOOLS_ENABLED=false
HOST_CONTROL_ENABLED=false
```

Bunları ayrıca tanımlamasanız da varsayılan `false` kullanılabilir.

Son olarak:

```text
Deploy the stack
```

seçin.

## 6. Güncelleme

GitHub'a yeni kod push edildikten sonra:

```text
Stacks
→ pi-assistant-loruv
→ Pull and redeploy
```

kullanılabilir.

> Aynı `container_name` ile hem terminal hem Portainer üzerinden aynı anda ikinci stack oluşturmaya çalışmayın.

---

# Git ile Lokal Kurulum

Portainer yerine Raspberry Pi üzerinde lokal repository kullanmak isterseniz:

```bash
cd /srv/docker
git clone https://github.com/emrecagri/Pi-Assistant-Loruv.git
cd Pi-Assistant-Loruv
```

Kalıcı dizinleri oluşturun:

```bash
sudo mkdir -p /srv/docker/pi-assistant /srv/downloads /srv/uploads
sudo chown -R "$USER":"$USER" /srv/docker/pi-assistant /srv/downloads /srv/uploads
```

`.env`:

```bash
cp .env.example .env
nano .env
```

Minimum:

```env
BOT_TOKEN=GERCEK_TELEGRAM_BOT_TOKEN
ALLOWED_USER_ID=GERCEK_TELEGRAM_USER_ID
```

Build ve başlatma:

```bash
docker compose -f compose.yml up -d --build
```

Durum:

```bash
docker compose -f compose.yml ps
```

Log:

```bash
docker logs --tail 100 pi-assistant-loruv
```

---

# Host Araçlarını Etkinleştirme

Temel Docker/sistem özellikleri host helper olmadan kullanılabilir.

Aşağıdakiler için host helper gerekir:

- SMART
- Raspberry Pi undervoltage/throttling
- systemd
- journal
- speedtest
- bazı bakım/güvenlik raporları
- reboot
- shutdown
- Docker daemon restart

## 1. Host helper kurulumu

Repository Raspberry Pi üzerinde mevcutsa:

```bash
cd /srv/docker/Pi-Assistant-Loruv
sudo ./host/install-host-helper.sh
```

`smartmontools`:

```bash
sudo apt update
sudo apt install -y smartmontools
```

SMART cihazlarını kontrol edin:

```bash
sudo smartctl --scan-open
```

Raspberry Pi power kontrolü:

```bash
vcgencmd get_throttled
```

---

## 2. Güvenli SSH forced-command anahtarı

Host araçları sınırsız shell kullanmaz. Container yalnız özel SSH anahtarı ve forced-command gateway üzerinden allowlist komutlarını çalıştırır.

Lokal repository deployment kullanıyorsanız proje içinde:

```bash
mkdir -p secrets
ssh-keygen -t ed25519 -f secrets/host_ssh_key -N ""
chmod 600 secrets/host_ssh_key
```

Public key:

```bash
cat secrets/host_ssh_key.pub
```

Host üzerindeki `piassistant` kullanıcısının:

```text
/home/piassistant/.ssh/authorized_keys
```

satırına şu formatta eklenir:

```text
restrict,command="/usr/local/sbin/pi-assistant-ssh-gateway" ssh-ed25519 AAAA...PUBLIC_KEY...
```

İzinler:

```bash
sudo chown -R piassistant:piassistant /home/piassistant/.ssh
sudo chmod 700 /home/piassistant/.ssh
sudo chmod 600 /home/piassistant/.ssh/authorized_keys
```

Known hosts:

```bash
ssh-keyscan -H 127.0.0.1 > secrets/known_hosts
chmod 600 secrets/known_hosts
```

Test:

```bash
ssh -i secrets/host_ssh_key \
  -o StrictHostKeyChecking=yes \
  -o UserKnownHostsFile=secrets/known_hosts \
  piassistant@127.0.0.1 throttled
```

Keyfi shell komutu reddedilmelidir:

```bash
ssh -i secrets/host_ssh_key \
  -o StrictHostKeyChecking=yes \
  -o UserKnownHostsFile=secrets/known_hosts \
  piassistant@127.0.0.1 "rm -rf /"
```

Beklenen:

```text
Denied
```

### Portainer Repository kullanıcıları için secrets notu

Portainer repository deployment kullanıldığında private SSH anahtarını public Git repository'ye koymayın.

En temiz yöntem host üzerinde kalıcı bir secret dizini kullanmaktır:

```text
/srv/docker/pi-assistant/secrets
```

ve compose mount'unu örneğin:

```yaml
- /srv/docker/pi-assistant/secrets:/run/secrets:ro
```

şeklinde kullanmaktır.

Bu sayede Portainer repository'yi yeniden klonladığında private key kaybolmaz ve GitHub'a yüklenmez.

---

## 3. systemd restart allowlist

Host helper kurulumu:

```text
/etc/pi-assistant-systemd-allowlist
```

dosyasını kullanır.

Örnek:

```text
docker.service
tailscaled.service
smbd.service
nmbd.service
```

Düzenleme:

```bash
sudo nano /etc/pi-assistant-systemd-allowlist
```

---

## 4. Host araçlarını açın

Portainer Environment Variables veya lokal `.env` içine:

```env
HOST_TOOLS_ENABLED=true
HOST_CONTROL_ENABLED=true
```

`HOST_TOOLS_ENABLED=true`:

- SMART
- vcgencmd
- speedtest
- systemd/journal
- bakım
- güvenlik
- host ağ tanılama

özelliklerini açar.

`HOST_CONTROL_ENABLED=true` ayrıca:

- reboot
- shutdown
- Docker daemon restart
- systemd allowlist restart
- SMART test

özelliklerini açar.

---

# Yapılandırma

Compose V5 ayarları environment variables üzerinden yönetilir.

## Zorunlu

| Değişken | Açıklama |
| --- | --- |
| `BOT_TOKEN` | BotFather tarafından verilen Telegram bot tokenı |
| `ALLOWED_USER_ID` | Botu kullanabilecek numeric Telegram user ID |

## Sistem / alarm

| Değişken | Varsayılan | Açıklama |
| --- | ---: | --- |
| `CHECK_INTERVAL` | `60` | Genel monitor aralığı, saniye |
| `CPU_LIMIT` | `90` | CPU alarm yüzdesi |
| `RAM_LIMIT` | `90` | RAM alarm yüzdesi |
| `DISK_LIMIT` | `90` | Disk alarm yüzdesi |
| `SWAP_LIMIT` | `80` | Swap alarm yüzdesi |
| `TEMP_LIMIT` | `75` | Sıcaklık alarmı, °C |
| `LOAD_LIMIT` | `0` | Load alarmı, `0` = kapalı |
| `PUBLIC_IP_CHECK_URL` | `https://api.ipify.org` | Dış IP servisi |
| `PUBLIC_IP_TIMEOUT` | `5` | Dış IP timeout |

## Docker

| Değişken | Varsayılan | Açıklama |
| --- | --- | --- |
| `DOCKER_RECREATE_ENABLED` | `true` | Güvenli generic recreate özelliği |
| `UPDATE_HEALTH_WAIT` | `20` | Update sonrası health bekleme |
| `UPDATE_IGNORE_CONTAINERS` | `pi-assistant-loruv` | Update kontrolünde atlanacak container'lar |
| `BULK_UPDATE_STOP_ON_ERROR` | `true` | Toplu update ilk hatada dursun |
| `DOCKER_BULK_STATS_LIMIT` | `40` | Merkezi stats üst sınırı |
| `DOCKER_LOG_LINES` | `100` | Telegram içi log satırı |
| `DOCKER_LOG_FILE_LINES` | `1500` | `.txt` log üst sınırı |

## Dosya yöneticisi

| Değişken | Varsayılan | Açıklama |
| --- | --- | --- |
| `DOWNLOAD_DIR` | `/srv/downloads` | URL download dizini |
| `UPLOAD_DIR` | `/srv/uploads` | Telegram upload dizini |
| `MAX_DOWNLOAD_SIZE_GB` | `10` | URL download maksimum boyutu |
| `DOWNLOAD_MIN_FREE_GB` | `2` | SSD'de minimum boş kalacak alan |
| `DOWNLOAD_TIMEOUT` | `600` | Download timeout |
| `DOWNLOAD_ALLOWED_PORTS` | `80,443` | İzinli URL portları |
| `TELEGRAM_SEND_MAX_MB` | `49` | Bot → Telegram dosya varsayılan sınırı |
| `TELEGRAM_UPLOAD_MAX_MB` | `19` | Telegram → bot dosya varsayılan sınırı |

## SSD / olay

| Değişken | Varsayılan | Açıklama |
| --- | ---: | --- |
| `LOG_LEVEL` | `WARNING` | Python log seviyesi |
| `EVENT_HISTORY_MAX` | `200` | Tutulacak maksimum önemli olay |
| `DISK_WRITE_SAMPLE_INTERVAL` | `300` | RAM'deki disk-write trend örnekleme süresi |
| `SMART_MONITOR_INTERVAL` | `0` | Otomatik SMART; `0` = kapalı |
| `PI_POWER_MONITOR_INTERVAL` | `300` | Pi power monitor aralığı |
| `SYSTEMD_MONITOR_INTERVAL` | `300` | systemd monitor aralığı |
| `CONFIRM_TTL` | `45` | Kritik onay geçerlilik süresi |

---

# SSD Dostu Çalışma

V5 Raspberry Pi + SSD kullanımına göre tasarlanmıştır.

## 1. Düşük Python log seviyesi

```env
LOG_LEVEL=WARNING
```

Varsayılan olarak debug/info seviyesinde sürekli disk logu üretilmez.

## 2. Docker `local` logging driver

Compose örneği:

```yaml
logging:
  driver: local
  options:
    max-size: "2m"
    max-file: "2"
```

Böylece bot loglarının kontrolsüz büyümesi engellenir.

## 3. Read-only root filesystem

```yaml
read_only: true
```

Bot yalnız açıkça izin verilen bind mount alanlarına yazar.

## 4. `/tmp` RAM üzerinde

```yaml
tmpfs:
  - /tmp:size=32m,mode=1777
```

Geçici işlemler SSD yerine RAM kullanır.

## 5. Sürekli telemetry DB yok

CPU/RAM gibi değerler sürekli SQLite/Influx/JSON geçmişine yazılmaz.

Yalnız önemli olaylar sınırlı geçmişte tutulur.

## 6. Disk write trendi RAM'de

Disk write trendi RAM içindeki sınırlı örneklerde tutulur; her örnek SSD'ye kaydedilmez.

---

# Güncelleme

## Portainer Repository

Önerilen yöntem:

```text
Stacks
→ pi-assistant-loruv
→ Pull and redeploy
```

Bu işlem repository'nin yeni sürümünü çekip image'ı tekrar oluşturur.

## Lokal Git

```bash
cd /srv/docker/Pi-Assistant-Loruv
git pull
docker compose -f compose.yml up -d --build
```

Cache sorunu varsa:

```bash
docker compose -f compose.yml build --no-cache
docker compose -f compose.yml up -d
```

---

# Logları Görüntüleme

Son 100 satır:

```bash
docker logs --tail 100 pi-assistant-loruv
```

Canlı log:

```bash
docker logs -f --tail 100 pi-assistant-loruv
```

Canlı log takibinden çıkmak:

```text
Ctrl + C
```

Bu işlem container'ı durdurmaz.

---

# Sorun Giderme

## Portainer: container name already in use

Hata:

```text
Conflict. The container name "/pi-assistant-loruv" is already in use
```

Eski stack/container hâlâ vardır.

Önce Portainer'dan eski stack'i kaldırın.

Gerekirse:

```bash
docker rm -f pi-assistant-loruv
```

Sonra yeniden deploy edin.

---

## Telegram mesajı gelmiyor

Kontrol edin:

1. `BOT_TOKEN` doğru mu?
2. `ALLOWED_USER_ID` doğru mu?
3. Bota `/start` gönderdiniz mi?
4. Raspberry Pi internete bağlı mı?
5. Container running mi?

```bash
docker ps --filter name=pi-assistant-loruv
```

Log:

```bash
docker logs --tail 100 pi-assistant-loruv
```

---

## Docker listesi alınamıyor

Docker socket mount'unu kontrol edin:

```yaml
- /var/run/docker.sock:/var/run/docker.sock
```

Host:

```bash
ls -l /var/run/docker.sock
```

---

## Süreçler yalnız container'ı gösteriyor

Compose'ta aşağıdakilerin bulunduğunu kontrol edin:

```yaml
pid: host
```

ve:

```yaml
- /proc:/host/proc:ro
```

Ayrıca:

```env
HOST_PROC=/host/proc
```

olmalıdır.

---

## Sıcaklık okunamıyor

Host:

```bash
cat /sys/class/thermal/thermal_zone0/temp
```

Compose:

```yaml
- /sys:/host/sys:ro
```

---

## SMART cihazı görünmüyor

Host:

```bash
sudo smartctl --scan-open
```

USB-SATA/NVMe bridge SMART passthrough desteklemiyorsa bazı değerler okunamayabilir.

---

## Host araçları çalışmıyor

Kontrol:

```env
HOST_TOOLS_ENABLED=true
```

SSH test:

```bash
ssh -i secrets/host_ssh_key \
  -o StrictHostKeyChecking=yes \
  -o UserKnownHostsFile=secrets/known_hosts \
  piassistant@127.0.0.1 throttled
```

---

## Dosya indirilemiyor

URL downloader bilinçli olarak private/non-global hedefleri reddeder.

Kontrol edin:

- URL `http://` veya `https://` mi?
- Port `DOWNLOAD_ALLOWED_PORTS` içinde mi?
- Hedef public IP'ye mi çözülüyor?
- Dosya maksimum boyuttan küçük mü?
- SSD'de `DOWNLOAD_MIN_FREE_GB` kadar alan kalıyor mu?

---

# Güvenlik

Pi Assistant güçlü Docker ve opsiyonel host erişimine sahiptir.

Aşağıdaki kurallara dikkat edin:

- `BOT_TOKEN` public repository'ye yazılmamalıdır.
- `ALLOWED_USER_ID` doğru kullanıcıya ait olmalıdır.
- Private SSH key GitHub'a yüklenmemelidir.
- `secrets/` içindeki gerçek key'ler `.gitignore` / `.dockerignore` kapsamında tutulmalıdır.
- Docker socket root seviyesine yakın güçlü yetki sağlar.
- Bot rastgele shell/terminal çalıştırmaz.
- Host komutları forced-command + allowlist ile sınırlandırılır.
- Kritik işlemler süreli ikinci onay ister.
- URL downloader private/non-global hedefleri engeller.
- Dosya yöneticisi yalnız izinli upload/download alanlarına yazar.
- Portainer'ı doğrudan internete açmak yerine VPN/Tailscale veya güvenli reverse proxy yöntemleri tercih edin.
- Bot token sızarsa BotFather üzerinden tokenı iptal edip yenileyin.
- Kullanılmayan volume cleanup veri kaybına yol açabilir; dikkatli kullanın.

### Önerilen `.gitignore`

```gitignore
.env
secrets/*
!secrets/.gitkeep
__pycache__/
*.pyc
```

---

# Smoke Test

V5 paketi temel statik kontroller için smoke test içerir.

```bash
chmod +x scripts/smoke-test.sh
./scripts/smoke-test.sh
```

Kontrol edilen başlıklar:

- Python syntax
- Shell syntax
- Compose kritik mount/log yapısı
- Forced-command bilinmeyen komut deny testi
- Callback data uzunluk kontrolü
- V5 kritik özellik izleri
- Paket içinde bariz secret/private-key izi kontrolü

---

# Lisans

Bu proje **MIT License** altında yayımlanır. Ayrıntılar için repository'deki `LICENSE` dosyasına bakın.

---

# Katkı

Bug report, geliştirme önerisi ve pull request'ler değerlidir.

Örnek akış:

```bash
git checkout -b feature/my-feature
git add .
git commit -m "Add my feature"
git push origin feature/my-feature
```

Ardından GitHub üzerinden Pull Request oluşturabilirsiniz.

---

# English

## About

**Pi Assistant Loruv V5 FINAL** is a self-hosted Telegram management assistant for Raspberry Pi and compatible Linux/Docker hosts.

V5 combines host monitoring, Docker management, real host processes, network ports, SSD/SMART information, systemd services, internet diagnostics, file transfers and selected host-control actions in one Telegram interface.

The design focuses on three principles:

1. **Powerful management** — reduce the need to SSH into the server for everyday tasks.
2. **Restricted privilege** — never expose a generic remote shell through Telegram.
3. **SSD-friendly operation** — avoid unnecessary persistent telemetry and uncontrolled logs.

Only the Telegram account configured through `ALLOWED_USER_ID` is authorized by default.

---

# V5 Final Features

## 📊 Host monitoring

- Raspberry Pi model
- Hostname / OS / kernel / architecture
- Uptime and boot time
- CPU usage and frequency
- Physical/logical CPUs
- Load average
- CPU temperature
- RAM details
- Swap usage
- Disk capacity and I/O
- Local IP
- Public IP
- Network RX/TX
- Threshold alerts and recovery notifications

## 🩺 Health center

A consolidated view for:

- CPU
- RAM
- Swap
- Disk
- Temperature
- Load
- Internet connectivity
- Docker daemon
- Host process visibility
- Optional SMART / power / systemd status

## ⚙️ Real host process manager

The compose file mounts the real host procfs:

```yaml
- /proc:/host/proc:ro
```

and V5 points psutil to:

```python
psutil.PROCFS_PATH = "/host/proc"
```

This allows the bot to inspect the Raspberry Pi host processes instead of only its own container namespace.

Features include:

- Process count and status summary
- Sort by CPU
- Sort by RAM
- Sort by disk I/O
- Search by PID/name/command line
- PPID and username
- CPU/core/nice
- RSS/VMS
- Thread count
- Read/write I/O
- Open files
- INET connections
- Process start time and uptime
- Executable, CWD and command line

## 🐳 Docker management

- List all containers
- Start / stop / restart
- Pause / resume
- Health status
- Image and container details
- Ports and IP addresses
- Mounts and resource limits
- CPU/RAM/network/block-I/O stats
- Telegram log view
- Export container logs as `.txt`
- Images, networks and volumes
- Docker disk usage
- Controlled cleanup operations

## 🔍 Check all Docker updates with one button

V5 can check the registry image for all eligible containers in a single operation.

The check itself does not recreate running containers.

Results are reported as:

- Up to date
- Update available
- Ignored
- Could not check

Available updates can then be applied in a separate confirmed bulk-update flow.

Safety mechanisms include:

- Confirmation token
- Ordered updates
- Health waiting
- Rollback attempt
- Optional stop-on-first-error
- Update ignore list
- Self-container protection
- Refusal of unsafe generic recreate scenarios

## 🔌 Docker and host ports

V5 shows:

- Container
- Host IP/port
- Container port
- TCP/UDP
- Published ports
- Unpublished exposed ports
- `0.0.0.0` / `::` binding warnings
- Host listening sockets
- PID/process owning a listening port

## 💿 SSD / SMART

When host tools are enabled, V5 can display supported SMART information such as:

- Device/model/serial/firmware
- Capacity/protocol
- SMART overall health
- Temperature
- Power-on hours
- Power cycles
- Reallocated/pending/uncorrectable sectors
- CRC errors
- NVMe percentage used
- Available spare
- Media errors
- Unsafe shutdowns
- NVMe read/write estimates

It can also export `smartctl -x` as a text report and start short/long SMART self-tests after confirmation.

## ⚡ Raspberry Pi power monitoring

Using `vcgencmd`:

- Undervoltage
- Historical undervoltage
- Throttling
- Historical throttling
- Frequency cap
- Soft temperature limit
- Core voltage
- ARM clock
- Firmware information

## 🌐 Network diagnostics

- Local/public IP
- Interfaces
- IPv4/IPv6
- MTU/link speed
- RX/TX/errors/drops
- Gateway connectivity
- Public DNS connectivity
- DNS resolution test
- Packet loss and latency
- Speedtest
- Internet down/recovery alerts
- Public-IP change alerts

## 📥 Secure URL downloader

Files can be downloaded to:

```text
/srv/downloads
```

with:

- HTTP/HTTPS only
- SSRF filtering
- Redirect re-validation
- Port allowlist
- Streaming downloads
- Size and free-space limits
- `.part` temporary files
- Atomic rename
- SHA-256
- Progress, rate and ETA

## 📁 File manager

Writable file-manager roots are intentionally limited to:

```text
/srv/downloads
/srv/uploads
```

The bot can list, inspect, hash, send and delete files in those areas after the required confirmation flow.

Documents sent to the bot can also be stored in `/srv/uploads` when they satisfy configured limits.

## 🧩 systemd

Optional host tools provide:

- Service list
- Active/sub state
- Main PID
- Memory and CPU time
- Restart count
- Result/unit-file state
- Failed-service monitoring
- Journal export as `.txt`
- Allowlisted service restart

## 🕒 Bounded event history

V5 does not store continuous system telemetry in a database. It persists only a bounded list of important events, such as connectivity changes, threshold alarms, Docker state changes, updates and file operations.

---

# Telegram Commands

| Command | Description |
| --- | --- |
| `/start` | Start the bot / show menu |
| `/menu` | Main management menu |
| `/durum` | Host status report |
| `/docker` | Docker center |
| `/surecler` | Real host processes |
| `/ag` | Network report |
| `/depolama` | Disk and I/O report |
| `/ip` | Local and public IP |
| `/portlar` | Docker + host listening ports |
| `/dosyalar` | Download/upload file manager |
| `/olaylar` | Recent important events |
| `/araclar` | Raspberry Pi/SMART/systemd host tools |
| `/servisler` | systemd services |
| `/smart` | SSD / SMART information |
| `/speedtest` | Internet speed test |
| `/rapor` | Diagnostic/log `.txt` reports |
| `/yardim` | Help / main menu |

Most V5 functions are also available through Telegram inline buttons, so typing commands is usually unnecessary.

---

# Requirements

Base deployment:

- Raspberry Pi or compatible Linux host
- Docker Engine
- Docker Compose plugin
- Internet connection
- Telegram account and BotFather bot
- Portainer optional but recommended

Optional host tools:

- OpenSSH server
- `smartmontools`
- `vcgencmd` on Raspberry Pi
- systemd/journalctl
- Ookla `speedtest` or compatible `speedtest-cli`

---

# Portainer Repository Deployment — Recommended

Open:

```text
Stacks
→ Add stack
→ Repository
```

Use:

| Field | Value |
| --- | --- |
| Name | `pi-assistant-loruv` |
| Repository URL | `https://github.com/emrecagri/Pi-Assistant-Loruv` |
| Repository reference | `refs/heads/main` |
| Compose path | `compose.yml` |
| Authentication | Off for a public repository |
| Skip TLS Verification | Off |
| GitOps updates | Off initially is recommended |

Add at least these Portainer environment variables:

```env
BOT_TOKEN=YOUR_REAL_TELEGRAM_BOT_TOKEN
ALLOWED_USER_ID=YOUR_REAL_TELEGRAM_USER_ID
```

Then deploy the stack.

After a new GitHub commit:

```text
Stacks
→ pi-assistant-loruv
→ Pull and redeploy
```

> If your repository uses `compose.yaml` rather than `compose.yml`, enter the exact filename in Portainer.

---

# Local Git Deployment

```bash
cd /srv/docker
git clone https://github.com/emrecagri/Pi-Assistant-Loruv.git
cd Pi-Assistant-Loruv
```

Create persistent directories:

```bash
sudo mkdir -p /srv/docker/pi-assistant /srv/downloads /srv/uploads
sudo chown -R "$USER":"$USER" /srv/docker/pi-assistant /srv/downloads /srv/uploads
```

Create `.env`:

```bash
cp .env.example .env
nano .env
```

Minimum:

```env
BOT_TOKEN=YOUR_REAL_TELEGRAM_BOT_TOKEN
ALLOWED_USER_ID=YOUR_REAL_TELEGRAM_USER_ID
```

Build and start:

```bash
docker compose -f compose.yml up -d --build
```

---

# Optional Host Tools

Install the host helper on the Raspberry Pi/Linux host:

```bash
sudo ./host/install-host-helper.sh
```

Install SMART tooling:

```bash
sudo apt update
sudo apt install -y smartmontools
```

Host operations use a restricted SSH forced-command gateway rather than a generic remote shell.

Enable them only after the helper/key setup is complete:

```env
HOST_TOOLS_ENABLED=true
HOST_CONTROL_ENABLED=true
```

For Portainer Repository deployment, keep the real SSH private key outside the public Git repository. An absolute host secret directory such as `/srv/docker/pi-assistant/secrets` is recommended.

---

# Configuration

The compose file uses variable interpolation:

```yaml
BOT_TOKEN: "${BOT_TOKEN}"
ALLOWED_USER_ID: "${ALLOWED_USER_ID}"
CHECK_INTERVAL: "${CHECK_INTERVAL:-60}"
TEMP_LIMIT: "${TEMP_LIMIT:-75}"
LOG_LEVEL: "${LOG_LEVEL:-WARNING}"
```

Only `BOT_TOKEN` and `ALLOWED_USER_ID` need to be supplied for a basic deployment. Other values can use their compose defaults and be overridden later through Portainer environment variables or a local `.env` file.

---

# SSD-Friendly Design

V5 minimizes unnecessary storage writes:

- Default Python log level: `WARNING`
- Docker `local` logging driver
- Small rotating bot logs
- Read-only container root filesystem
- `/tmp` mounted as tmpfs
- No continuous telemetry database
- Bounded event history
- Disk-write trend sampled in RAM
- Automatic SMART polling disabled by default

Example logging configuration:

```yaml
logging:
  driver: local
  options:
    max-size: "2m"
    max-file: "2"
```

---

# Security

- Never commit a real `BOT_TOKEN`.
- Never commit the host SSH private key.
- Restrict bot access through `ALLOWED_USER_ID`.
- Docker socket access is highly privileged.
- V5 intentionally provides no generic Telegram shell.
- Host commands pass through a forced-command allowlist gateway.
- Destructive actions require short-lived, single-use confirmation tokens.
- The URL downloader rejects private/non-global targets by default.
- File management is limited to explicitly mounted upload/download directories.
- Be careful with volume cleanup operations.
- Prefer VPN/Tailscale or another secure access layer rather than exposing management services directly to the public internet.

---

# Smoke Test

```bash
chmod +x scripts/smoke-test.sh
./scripts/smoke-test.sh
```

The script checks core Python/shell syntax, compose assumptions, forced-command denial behavior, callback sizes and common secret-packaging mistakes.

---

# License

Licensed under the **MIT License**. See `LICENSE` for details.

---

# Contributing

Issues, suggestions and pull requests are welcome.

If Pi Assistant Loruv is useful to you, consider starring the repository.
