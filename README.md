# Pi Assistant | Raspberry Pi Telegram Docker Yönetimi

> Raspberry Pi sistemlerini Telegram üzerinden izlemek ve Docker container’larını uzaktan yönetmek için geliştirilmiş, hafif ve genişletilebilir bir self-hosted yardımcı uygulama.

> A lightweight and extensible self-hosted assistant for monitoring Raspberry Pi systems and remotely managing Docker containers through Telegram.

---

## İçindekiler / Table of Contents

### Türkçe

* [Proje Hakkında](#proje-hakkında)
* [Özellikler](#özellikler)
* [Telegram Komutları](#telegram-komutları)
* [Gereksinimler](#gereksinimler)
* [Proje Yapısı](#proje-yapısı)
* [Telegram Botu Oluşturma](#telegram-botu-oluşturma)
* [Git ile Kurulum](#git-ile-kurulum)
* [Dosya Yükleyerek Kurulum](#dosya-yükleyerek-kurulum)
* [Portainer Üzerinden Yönetim](#portainer-üzerinden-yönetim)
* [Yapılandırma](#yapılandırma)
* [Kod Güncelleme](#kod-güncelleme)
* [Logları Görüntüleme](#logları-görüntüleme)
* [Sorun Giderme](#sorun-giderme)
* [Güvenlik](#güvenlik)

### English

* [About the Project](#about-the-project)
* [Features](#features)
* [Telegram Commands](#telegram-commands)
* [Requirements](#requirements)
* [Project Structure](#project-structure)
* [Creating a Telegram Bot](#creating-a-telegram-bot)
* [Installation with Git](#installation-with-git)
* [Manual File Installation](#manual-file-installation)
* [Managing with Portainer](#managing-with-portainer)
* [Configuration](#configuration)
* [Updating the Code](#updating-the-code)
* [Viewing Logs](#viewing-logs)
* [Troubleshooting](#troubleshooting)
* [Security](#security-1)

---

# Türkçe

## Proje Hakkında

Pi Assistant, Docker çalışan bir Raspberry Pi üzerinde sistem durumunu izlemek ve Docker container’larını Telegram üzerinden yönetmek amacıyla geliştirilmiştir.

Uygulama aşağıdaki görevleri yerine getirebilir:

* Raspberry Pi veya bot container’ı başladığında Telegram bildirimi gönderir.
* CPU, RAM, disk ve sıcaklık değerlerini izler.
* Belirlenen eşikler aşıldığında uyarı gönderir.
* İnternet bağlantısı kesildiğinde veya geri geldiğinde bildirim gönderir.
* Genel IP adresi değiştiğinde haber verir.
* Docker container’larını listeler.
* Container başlatma, durdurma ve yeniden başlatma işlemlerini Telegram üzerinden gerçekleştirir.
* Yalnızca izin verilen Telegram kullanıcı hesabından gelen komutları kabul eder.

Pi Assistant özellikle ev sunucuları, homelab sistemleri, Raspberry Pi cihazları ve küçük ölçekli self-hosted sistemler için tasarlanmıştır.

---

## Özellikler

### Sistem İzleme

* CPU kullanım oranı
* RAM kullanım oranı
* Disk kullanım oranı
* Raspberry Pi işlemci sıcaklığı
* Ağ üzerinden gönderilen veri miktarı
* Ağ üzerinden alınan veri miktarı
* Sistem çalışma süresi
* Yerel IP adresi
* Genel IP adresi

### Otomatik Bildirimler

Pi Assistant aşağıdaki durumlarda Telegram bildirimi gönderebilir:

* Bot container’ı başladığında
* Raspberry Pi yeniden açıldığında
* CPU kullanımı belirlenen sınırı geçtiğinde
* RAM kullanımı belirlenen sınırı geçtiğinde
* Disk kullanımı belirlenen sınırı geçtiğinde
* İşlemci sıcaklığı yükseldiğinde
* İnternet bağlantısı kesildiğinde
* İnternet bağlantısı tekrar geldiğinde
* Genel IP adresi değiştiğinde
* İzlenen değerler yeniden normale döndüğünde

### Docker Yönetimi

* Tüm container’ları listeleme
* Container çalışma durumunu görüntüleme
* Container başlatma
* Container durdurma
* Container yeniden başlatma
* Container image bilgisini görüntüleme

---

## Telegram Komutları

| Komut                        | Açıklama                                                            |
| ---------------------------- | ------------------------------------------------------------------- |
| `/start`                     | Botun karşılama mesajını ve temel komutları gösterir                |
| `/yardim`                    | Kullanılabilir komutları listeler                                   |
| `/durum`                     | CPU, RAM, disk, sıcaklık, ağ ve çalışma süresi bilgilerini gösterir |
| `/docker`                    | Docker container’larını ve durumlarını listeler                     |
| `/ip`                        | Yerel ve genel IP adresini gösterir                                 |
| `/baslat <container>`        | Belirtilen container’ı başlatır                                     |
| `/durdur <container>`        | Belirtilen container’ı durdurur                                     |
| `/yenidenbaslat <container>` | Belirtilen container’ı yeniden başlatır                             |

### Komut örnekleri

```text
/durum
```

```text
/docker
```

```text
/ip
```

```text
/baslat nginx-proxy-manager
```

```text
/durdur nginx-proxy-manager
```

```text
/yenidenbaslat nginx-proxy-manager
```

Container adı, `/docker` komutunda gösterildiği şekilde yazılmalıdır.

---

## Gereksinimler

Kurulumdan önce aşağıdaki bileşenlerin hazır olması gerekir:

* Raspberry Pi
* 64 bit Raspberry Pi OS veya uyumlu bir Linux dağıtımı
* Docker Engine
* Docker Compose eklentisi
* Portainer, isteğe bağlı
* Telegram hesabı
* BotFather üzerinden oluşturulmuş Telegram botu
* İnternet bağlantısı

Docker sürümünü kontrol etmek için:

```bash
docker --version
```

Docker Compose sürümünü kontrol etmek için:

```bash
docker compose version
```

Docker servisinin çalışıp çalışmadığını kontrol etmek için:

```bash
sudo systemctl status docker
```

---

## Proje Yapısı

```text
pi-assistant-loruv/
├── bot.py
├── compose.yaml
├── Dockerfile
├── requirements.txt
├── .env.example
├── .gitignore
├── README.md
└── data/
```

### Dosyaların görevleri

| Dosya              | Açıklama                                                                 |
| ------------------ | ------------------------------------------------------------------------ |
| `bot.py`           | Telegram botunun ve sistem izleme özelliklerinin ana Python kodu         |
| `compose.yaml`     | Container’ın nasıl çalıştırılacağını belirleyen Docker Compose dosyası   |
| `Dockerfile`       | Python uygulamasının Docker image olarak nasıl oluşturulacağını tanımlar |
| `requirements.txt` | Gerekli Python kütüphanelerini içerir                                    |
| `.env.example`     | Ortam değişkenleri için örnek yapılandırma dosyası                       |
| `.env`             | Bot tokeni, kullanıcı ID’si ve eşik değerleri gibi özel ayarlar          |
| `.gitignore`       | GitHub’a yüklenmemesi gereken dosyaları tanımlar                         |
| `data/`            | Genel IP gibi kalıcı bilgilerin saklandığı klasör                        |

> `.env` dosyası gizli bilgiler içerdiği için GitHub’a yüklenmemelidir.

---

## Telegram Botu Oluşturma

### 1. BotFather’ı açın

Telegram üzerinde aşağıdaki resmi botu açın:

```text
@BotFather
```

### 2. Yeni bot oluşturun

BotFather’a şu komutu gönderin:

```text
/newbot
```

Botunuz için bir isim ve kullanıcı adı belirleyin.

BotFather size aşağıdakine benzer bir token verecektir:

```text
123456789:AAxxxxxxxxxxxxxxxxxxxxxxxxxxxx
```

Bu değer daha sonra `.env` dosyasındaki `BOT_TOKEN` alanına yazılacaktır.

### 3. Bota mesaj gönderin

Oluşturduğunuz botu açın ve şu komutu gönderin:

```text
/start
```

### 4. Telegram kullanıcı ID’nizi öğrenin

Telegram kullanıcı ID’nizi öğrenmek için bir kullanıcı bilgi botundan yararlanabilir veya Telegram API üzerinden kendi kullanıcı ID’nizi belirleyebilirsiniz.

Örnek kullanıcı ID:

```text
123456789
```

Bu değer `.env` dosyasındaki `ALLOWED_USER_ID` alanına yazılacaktır.

---

## Git ile Kurulum

Bu yöntem GitHub repository’sini doğrudan Raspberry Pi üzerine klonlar.

### 1. `/srv/docker` dizinine geçin

```bash
cd /srv/docker
```

Dizin mevcut değilse oluşturun:

```bash
sudo mkdir -p /srv/docker
```

Kullanıcınıza yetki vermek için:

```bash
sudo chown -R $USER:$USER /srv/docker
```

Ardından:

```bash
cd /srv/docker
```

### 2. Repository’yi klonlayın

```bash
git clone https://github.com/emrecagri/Pi-Assistant-Loruv.git
```

Örnek:

```bash
git clone https://github.com/emrecagri/Pi-Assistant-Loruv.git
```

### 3. Proje klasörüne girin

```bash
cd /srv/docker/pi-assistant-loruv
```

### 4. Ortam dosyasını oluşturun

```bash
cp .env.example .env
```

### 5. `.env` dosyasını düzenleyin

```bash
nano .env
```

Örnek yapılandırma:

```env
BOT_TOKEN=BOTFATHER_TOKENINIZ
ALLOWED_USER_ID=TELEGRAM_KULLANICI_IDNIZ

CHECK_INTERVAL=60
CPU_LIMIT=90
RAM_LIMIT=90
DISK_LIMIT=90
TEMP_LIMIT=75
PUBLIC_IP_CHECK_URL=https://api.ipify.org
```

Nano editöründe kaydetmek için:

```text
Ctrl + O
Enter
Ctrl + X
```

### 6. Container’ı oluşturun ve başlatın

```bash
sudo docker compose up -d --build
```

### 7. Container durumunu kontrol edin

```bash
sudo docker compose ps
```

### 8. Logları kontrol edin

```bash
sudo docker compose logs -f
```

Başarılı kurulumdan sonra Telegram’a aşağıdakine benzer bir mesaj gelmelidir:

```text
Pi Assistant çalıştı. Raspberry Pi veya bot container'ı yeniden başlatılmış olabilir.
```

---

## Dosya Yükleyerek Kurulum

Bu yöntem Git kullanmadan, proje dosyalarını Raspberry Pi’ye elle yüklemek isteyen kullanıcılar içindir.

Dosyalar SFTP, SCP, File Browser veya başka bir dosya aktarım yöntemiyle yüklenebilir.

### Hedef klasör

Proje şu dizinde tutulacaktır:

```text
/srv/docker/pi-assistant-loruv
```

### 1. Proje klasörünü oluşturun

```bash
sudo mkdir -p /srv/docker/pi-assistant-loruv
```

### 2. Klasör izinlerini düzenleyin

```bash
sudo chown -R $USER:$USER /srv/docker/pi-assistant-loruv
```

### 3. Proje dosyalarını yükleyin

Aşağıdaki dosyaları `/srv/docker/pi-assistant-loruv` içerisine yükleyin:

```text
bot.py
compose.yaml
Dockerfile
requirements.txt
.env.example
.gitignore
README.md
```

Ayrıca `data` klasörünü oluşturun:

```bash
mkdir -p /srv/docker/pi-assistant-loruv/data
```

### 4. Dosyaların doğru yerde olduğunu kontrol edin

```bash
ls -la /srv/docker/pi-assistant-loruv
```

Beklenen görünüm:

```text
bot.py
compose.yaml
Dockerfile
requirements.txt
.env.example
.gitignore
README.md
data
```

### 5. Proje klasörüne girin

```bash
cd /srv/docker/pi-assistant-loruv
```

### 6. `.env` dosyasını oluşturun

```bash
cp .env.example .env
```

### 7. Ayarları girin

```bash
nano .env
```

Örnek:

```env
BOT_TOKEN=BOTFATHER_TOKENINIZ
ALLOWED_USER_ID=TELEGRAM_KULLANICI_IDNIZ

CHECK_INTERVAL=60
CPU_LIMIT=90
RAM_LIMIT=90
DISK_LIMIT=90
TEMP_LIMIT=75
PUBLIC_IP_CHECK_URL=https://api.ipify.org
```

### 8. Container’ı oluşturun

```bash
sudo docker compose up -d --build
```

### 9. Çalışma durumunu kontrol edin

```bash
sudo docker compose ps
```

### 10. Logları görüntüleyin

```bash
sudo docker compose logs -f
```

---

## Portainer Üzerinden Yönetim

İlk image oluşturma işlemi terminal üzerinden yapılabilir:

```bash
cd /srv/docker/pi-assistant-loruv
sudo docker compose up -d --build
```

Kurulum tamamlandıktan sonra container Portainer üzerinde görünür.

Portainer içinde şu yolu takip edin:

```text
Containers
→ pi-assistant-loruv
```

Buradan aşağıdaki işlemleri yapabilirsiniz:

* Container başlatma
* Container durdurma
* Container yeniden başlatma
* Logları görüntüleme
* Container istatistiklerini görüntüleme
* Container detaylarını inceleme

### Portainer üzerinden log görüntüleme

```text
Containers
→ pi-assistant-loruv
→ Logs
```

### Portainer üzerinden yeniden başlatma

```text
Containers
→ pi-assistant-loruv
→ Restart
```

### Önemli bilgi

Sadece Portainer üzerinde `Restart` seçeneğini kullanmak, mevcut image’ı yeniden başlatır.

`bot.py`, `Dockerfile` veya `requirements.txt` dosyası değiştirilmişse image’ın yeniden oluşturulması gerekir.

Bu durumda şu komut kullanılmalıdır:

```bash
cd /srv/docker/pi-assistant-loruv
sudo docker compose up -d --build
```

---

## Yapılandırma

Uygulama ayarları `.env` dosyası üzerinden yönetilir.

```env
BOT_TOKEN=BOTFATHER_TOKENINIZ
ALLOWED_USER_ID=TELEGRAM_KULLANICI_IDNIZ

CHECK_INTERVAL=60
CPU_LIMIT=90
RAM_LIMIT=90
DISK_LIMIT=90
TEMP_LIMIT=75
PUBLIC_IP_CHECK_URL=https://api.ipify.org
```

### Ortam değişkenleri

| Değişken              | Açıklama                                                | Örnek                   |
| --------------------- | ------------------------------------------------------- | ----------------------- |
| `BOT_TOKEN`           | BotFather tarafından verilen Telegram bot tokeni        | `123456:AA...`          |
| `ALLOWED_USER_ID`     | Botu kullanmasına izin verilen Telegram kullanıcı ID’si | `123456789`             |
| `CHECK_INTERVAL`      | Kontroller arasındaki süre, saniye                      | `60`                    |
| `CPU_LIMIT`           | CPU kullanım uyarı sınırı                               | `90`                    |
| `RAM_LIMIT`           | RAM kullanım uyarı sınırı                               | `90`                    |
| `DISK_LIMIT`          | Disk kullanım uyarı sınırı                              | `90`                    |
| `TEMP_LIMIT`          | Sıcaklık uyarı sınırı, Celsius                          | `75`                    |
| `PUBLIC_IP_CHECK_URL` | Genel IP kontrol servisi                                | `https://api.ipify.org` |

### Örnek daha hassas yapılandırma

```env
CHECK_INTERVAL=30
CPU_LIMIT=80
RAM_LIMIT=85
DISK_LIMIT=85
TEMP_LIMIT=70
```

Bu ayarlarda sistem her 30 saniyede bir kontrol edilir.

---

## Kod Güncelleme

### `bot.py` değiştirildiğinde

Python kodunda değişiklik yaptıktan sonra container’ın yalnızca yeniden başlatılması yeterli değildir.

Çünkü `bot.py` dosyası Docker image oluşturulurken image içine kopyalanır.

Bu nedenle image yeniden oluşturulmalıdır:

```bash
cd /srv/docker/pi-assistant-loruv
sudo docker compose up -d --build
```

Bu komut:

1. Docker image’ı yeniden oluşturur.
2. Yeni Python kodunu image içine kopyalar.
3. Eski container’ı yenisiyle değiştirir.
4. Container’ı arka planda yeniden başlatır.

### `requirements.txt` değiştirildiğinde

Yeni bir Python kütüphanesi eklendiğinde:

```bash
cd /srv/docker/pi-assistant-loruv
sudo docker compose up -d --build
```

komutu tekrar çalıştırılmalıdır.

Örneğin `requirements.txt` içerisine yeni bir paket eklendiyse image yeniden oluşturulur ve paket yüklenir.

### `Dockerfile` değiştirildiğinde

Dockerfile üzerinde değişiklik yapıldıysa:

```bash
cd /srv/docker/pi-assistant-loruv
sudo docker compose up -d --build
```

komutu kullanılmalıdır.

### `compose.yaml` değiştirildiğinde

Compose dosyası değiştirildikten sonra:

```bash
cd /srv/docker/pi-assistant-loruv
sudo docker compose up -d
```

çalıştırılabilir.

Ancak değişiklik image yapısını da etkiliyorsa güvenli yöntem şudur:

```bash
sudo docker compose up -d --build
```

### `.env` değiştirildiğinde

`.env` dosyası değiştirildikten sonra container’ın yeniden oluşturulması gerekir:

```bash
cd /srv/docker/pi-assistant-loruv
sudo docker compose up -d --force-recreate
```

Alternatif olarak:

```bash
sudo docker compose down
sudo docker compose up -d
```

### GitHub’dan yeni kod çekildiğinde

Repository Git ile kurulmuşsa:

```bash
cd /srv/docker/pi-assistant-loruv
git pull
```

Ardından image’ı yeniden oluşturun:

```bash
sudo docker compose up -d --build
```

Tek seferde:

```bash
cd /srv/docker/pi-assistant-loruv
git pull
sudo docker compose up -d --build
```

### Cache kullanmadan tamamen yeniden oluşturma

Docker eski katmanları kullanıyor veya değişiklikler uygulanmıyorsa:

```bash
cd /srv/docker/pi-assistant-loruv
sudo docker compose build --no-cache
sudo docker compose up -d
```

### Güncelleme sonrası kontrol

```bash
sudo docker compose ps
```

```bash
sudo docker compose logs -f
```

---

## Logları Görüntüleme

Canlı logları görüntülemek için:

```bash
cd /srv/docker/pi-assistant-loruv
sudo docker compose logs -f
```

Son 100 satırı görmek için:

```bash
sudo docker compose logs --tail=100
```

Sadece Pi Assistant container loglarını görüntülemek için:

```bash
sudo docker logs -f pi-assistant-loruv
```

Log takibinden çıkmak için:

```text
Ctrl + C
```

Bu işlem container’ı durdurmaz.

---

## Sık Kullanılan Docker Komutları

### Container’ı başlatma

```bash
sudo docker compose up -d
```

### Image’ı yeniden oluşturma

```bash
sudo docker compose up -d --build
```

### Container’ı durdurma ve kaldırma

```bash
sudo docker compose down
```

### Container’ı yeniden başlatma

```bash
sudo docker compose restart
```

### Çalışma durumunu görüntüleme

```bash
sudo docker compose ps
```

### Logları görüntüleme

```bash
sudo docker compose logs -f
```

### Tamamen yeniden oluşturma

```bash
sudo docker compose down
sudo docker compose build --no-cache
sudo docker compose up -d
```

---

## Sorun Giderme

### Telegram mesajı gelmiyor

Aşağıdakileri kontrol edin:

1. Bot tokeni doğru mu?
2. `ALLOWED_USER_ID` doğru mu?
3. Telegram’da bota `/start` gönderdiniz mi?
4. Raspberry Pi internete bağlı mı?
5. Container çalışıyor mu?

```bash
sudo docker compose ps
```

Logları kontrol edin:

```bash
sudo docker compose logs -f
```

### Container sürekli yeniden başlıyor

Logları görüntüleyin:

```bash
sudo docker logs --tail=100 pi-assistant-loruv
```

`.env` dosyasını kontrol edin:

```bash
cat .env
```

Tokeni herkese açık ortamlarda paylaşmayın.

### Docker container listesi alınamıyor

Compose dosyasında aşağıdaki bağlantının bulunduğunu kontrol edin:

```yaml
volumes:
  - /var/run/docker.sock:/var/run/docker.sock
```

Docker socket dosyasını kontrol edin:

```bash
ls -l /var/run/docker.sock
```

### Sıcaklık okunamıyor

Compose dosyasında aşağıdaki volume bağlantısının bulunduğunu kontrol edin:

```yaml
volumes:
  - /sys/class/thermal:/host/sys/class/thermal:ro
```

Host üzerinde sıcaklık dosyasını kontrol edin:

```bash
cat /sys/class/thermal/thermal_zone0/temp
```

Örneğin şu değer:

```text
47500
```

şu sıcaklığı ifade eder:

```text
47.5 °C
```

### Kod değişikliği uygulanmıyor

Sadece container yeniden başlatılmış olabilir.

Image’ı yeniden oluşturun:

```bash
cd /srv/docker/pi-assistant-loruv
sudo docker compose up -d --build
```

Sorun devam ederse cache kullanmadan oluşturun:

```bash
sudo docker compose build --no-cache
sudo docker compose up -d
```

---

## Güvenlik

Pi Assistant, Docker socket bağlantısı kullandığı için güçlü sistem yetkilerine sahiptir.

Aşağıdaki güvenlik kurallarına dikkat edilmelidir:

* `.env` dosyasını GitHub’a yüklemeyin.
* Telegram bot tokenini kimseyle paylaşmayın.
* Bot yalnızca kendi Telegram kullanıcı ID’nize izin vermelidir.
* Repository içerisinde gerçek token bulundurmayın.
* Docker socket erişiminin root seviyesine yakın yetki sağladığını unutmayın.
* Raspberry Pi üzerindeki SSH erişimini güçlü parola veya SSH anahtarıyla koruyun.
* Gereksiz portları internete açmayın.
* Portainer’ı doğrudan internete açık bırakmayın.
* Bot tokeni sızarsa BotFather üzerinden tokeni iptal edip yenisini oluşturun.

### `.gitignore` örneği

```gitignore
.env
data/
__pycache__/
*.pyc
```

### Yanlışlıkla `.env` Git’e eklendiyse

Git takibinden çıkarın:

```bash
git rm --cached .env
```

Ardından commit oluşturun:

```bash
git commit -m "Remove environment file"
```

Token GitHub’a yüklendiyse yalnızca dosyayı silmek yeterli değildir. BotFather üzerinden token yenilenmelidir.

---

# English

## About the Project

Pi Assistant is designed to monitor a Raspberry Pi system running Docker and manage Docker containers remotely through Telegram.

The application can:

* Send a Telegram notification when the Raspberry Pi or bot container starts.
* Monitor CPU, RAM, disk usage, and CPU temperature.
* Send alerts when configured thresholds are exceeded.
* Notify the user when the internet connection is lost or restored.
* Detect and report public IP address changes.
* List Docker containers.
* Start, stop, and restart Docker containers through Telegram.
* Accept commands only from an authorized Telegram user.

Pi Assistant is suitable for home servers, homelabs, Raspberry Pi devices, and small self-hosted environments.

---

## Features

### System Monitoring

* CPU usage
* RAM usage
* Disk usage
* Raspberry Pi CPU temperature
* Sent network data
* Received network data
* System uptime
* Local IP address
* Public IP address

### Automatic Notifications

Pi Assistant can send Telegram notifications when:

* The bot container starts
* The Raspberry Pi restarts
* CPU usage exceeds the configured threshold
* RAM usage exceeds the configured threshold
* Disk usage exceeds the configured threshold
* CPU temperature becomes too high
* Internet connectivity is lost
* Internet connectivity is restored
* The public IP address changes
* System values return to normal

### Docker Management

* List all containers
* Display container status
* Start containers
* Stop containers
* Restart containers
* Display container image information

---

## Telegram Commands

| Command                      | Description                                                           |
| ---------------------------- | --------------------------------------------------------------------- |
| `/start`                     | Displays the welcome message and basic commands                       |
| `/yardim`                    | Displays the available commands                                       |
| `/durum`                     | Displays CPU, RAM, disk, temperature, network, and uptime information |
| `/docker`                    | Lists Docker containers and their status                              |
| `/ip`                        | Displays local and public IP addresses                                |
| `/baslat <container>`        | Starts the specified container                                        |
| `/durdur <container>`        | Stops the specified container                                         |
| `/yenidenbaslat <container>` | Restarts the specified container                                      |

### Command examples

```text
/durum
```

```text
/docker
```

```text
/ip
```

```text
/baslat nginx-proxy-manager
```

```text
/durdur nginx-proxy-manager
```

```text
/yenidenbaslat nginx-proxy-manager
```

The container name must match the name displayed by the `/docker` command.

---

## Requirements

Before installation, make sure the following components are available:

* Raspberry Pi
* 64-bit Raspberry Pi OS or a compatible Linux distribution
* Docker Engine
* Docker Compose plugin
* Portainer, optional
* Telegram account
* Telegram bot created with BotFather
* Internet connection

Check the Docker version:

```bash
docker --version
```

Check the Docker Compose version:

```bash
docker compose version
```

Check the Docker service:

```bash
sudo systemctl status docker
```

---

## Project Structure

```text
pi-assistant-loruv/
├── bot.py
├── compose.yaml
├── Dockerfile
├── requirements.txt
├── .env.example
├── .gitignore
├── README.md
└── data/
```

### File descriptions

| File               | Description                                                 |
| ------------------ | ----------------------------------------------------------- |
| `bot.py`           | Main Python code for the Telegram bot and system monitoring |
| `compose.yaml`     | Docker Compose configuration                                |
| `Dockerfile`       | Defines how the Docker image is built                       |
| `requirements.txt` | Contains the required Python packages                       |
| `.env.example`     | Example environment configuration                           |
| `.env`             | Contains private settings such as the bot token and user ID |
| `.gitignore`       | Defines files that must not be committed                    |
| `data/`            | Stores persistent data such as the last known public IP     |

> The `.env` file contains sensitive information and must never be committed to GitHub.

---

## Creating a Telegram Bot

### 1. Open BotFather

Open the official Telegram bot:

```text
@BotFather
```

### 2. Create a new bot

Send:

```text
/newbot
```

Choose a name and username for your bot.

BotFather will provide a token similar to:

```text
123456789:AAxxxxxxxxxxxxxxxxxxxxxxxxxxxx
```

This value will be used as `BOT_TOKEN`.

### 3. Start the bot

Open your newly created bot and send:

```text
/start
```

### 4. Find your Telegram user ID

Use a Telegram user information bot or the Telegram API to determine your numeric user ID.

Example:

```text
123456789
```

This value will be used as `ALLOWED_USER_ID`.

---

## Installation with Git

This method clones the GitHub repository directly onto the Raspberry Pi.

### 1. Open the Docker directory

```bash
cd /srv/docker
```

Create it if it does not exist:

```bash
sudo mkdir -p /srv/docker
```

Grant ownership to the current user:

```bash
sudo chown -R $USER:$USER /srv/docker
```

Then:

```bash
cd /srv/docker
```

### 2. Clone the repository

```bash
git clone https://github.com/emrecagri/Pi-Assistant-Loruv.git
```

Example:

```bash
git clone https://github.com/emrecagri/Pi-Assistant-Loruv.git
```

### 3. Open the project directory

```bash
cd /srv/docker/pi-assistant-loruv
```

### 4. Create the environment file

```bash
cp .env.example .env
```

### 5. Edit the environment file

```bash
nano .env
```

Example configuration:

```env
BOT_TOKEN=YOUR_BOT_TOKEN
ALLOWED_USER_ID=YOUR_TELEGRAM_USER_ID

CHECK_INTERVAL=60
CPU_LIMIT=90
RAM_LIMIT=90
DISK_LIMIT=90
TEMP_LIMIT=75
PUBLIC_IP_CHECK_URL=https://api.ipify.org
```

Save in Nano:

```text
Ctrl + O
Enter
Ctrl + X
```

### 6. Build and start the container

```bash
sudo docker compose up -d --build
```

### 7. Check the container status

```bash
sudo docker compose ps
```

### 8. View logs

```bash
sudo docker compose logs -f
```

After a successful installation, a startup notification should be delivered through Telegram.

---

## Manual File Installation

This method is intended for users who want to upload the project files manually without using Git.

Files may be transferred using SFTP, SCP, File Browser, or another file transfer method.

### Target directory

```text
/srv/docker/pi-assistant-loruv
```

### 1. Create the project directory

```bash
sudo mkdir -p /srv/docker/pi-assistant-loruv
```

### 2. Configure directory ownership

```bash
sudo chown -R $USER:$USER /srv/docker/pi-assistant-loruv
```

### 3. Upload the project files

Upload the following files into `/srv/docker/pi-assistant-loruv`:

```text
bot.py
compose.yaml
Dockerfile
requirements.txt
.env.example
.gitignore
README.md
```

Create the persistent data directory:

```bash
mkdir -p /srv/docker/pi-assistant-loruv/data
```

### 4. Verify the files

```bash
ls -la /srv/docker/pi-assistant-loruv
```

### 5. Open the project directory

```bash
cd /srv/docker/pi-assistant-loruv
```

### 6. Create the `.env` file

```bash
cp .env.example .env
```

### 7. Configure the application

```bash
nano .env
```

### 8. Build the container

```bash
sudo docker compose up -d --build
```

### 9. Check the status

```bash
sudo docker compose ps
```

### 10. View logs

```bash
sudo docker compose logs -f
```

---

## Managing with Portainer

After the image has been built, the Pi Assistant container will appear in Portainer.

Open:

```text
Containers
→ pi-assistant-loruv
```

Portainer can be used to:

* Start the container
* Stop the container
* Restart the container
* View logs
* View resource statistics
* Inspect container details

### Important

Restarting the container in Portainer only restarts the existing Docker image.

When `bot.py`, `Dockerfile`, or `requirements.txt` is changed, rebuild the image:

```bash
cd /srv/docker/pi-assistant-loruv
sudo docker compose up -d --build
```

---

## Configuration

The application is configured through the `.env` file.

```env
BOT_TOKEN=YOUR_BOT_TOKEN
ALLOWED_USER_ID=YOUR_TELEGRAM_USER_ID

CHECK_INTERVAL=60
CPU_LIMIT=90
RAM_LIMIT=90
DISK_LIMIT=90
TEMP_LIMIT=75
PUBLIC_IP_CHECK_URL=https://api.ipify.org
```

### Environment variables

| Variable              | Description                              | Example                 |
| --------------------- | ---------------------------------------- | ----------------------- |
| `BOT_TOKEN`           | Telegram bot token provided by BotFather | `123456:AA...`          |
| `ALLOWED_USER_ID`     | Authorized Telegram user ID              | `123456789`             |
| `CHECK_INTERVAL`      | Monitoring interval in seconds           | `60`                    |
| `CPU_LIMIT`           | CPU alert threshold                      | `90`                    |
| `RAM_LIMIT`           | RAM alert threshold                      | `90`                    |
| `DISK_LIMIT`          | Disk alert threshold                     | `90`                    |
| `TEMP_LIMIT`          | Temperature threshold in Celsius         | `75`                    |
| `PUBLIC_IP_CHECK_URL` | Public IP lookup service                 | `https://api.ipify.org` |

---

## Updating the Code

### After changing `bot.py`

A normal container restart is not enough because `bot.py` is copied into the Docker image during the build process.

Rebuild the image:

```bash
cd /srv/docker/pi-assistant-loruv
sudo docker compose up -d --build
```

### After changing `requirements.txt`

When a Python dependency is added or changed:

```bash
cd /srv/docker/pi-assistant-loruv
sudo docker compose up -d --build
```

### After changing the `Dockerfile`

```bash
cd /srv/docker/pi-assistant-loruv
sudo docker compose up -d --build
```

### After changing `compose.yaml`

```bash
cd /srv/docker/pi-assistant-loruv
sudo docker compose up -d
```

Use the following when the change also affects the image:

```bash
sudo docker compose up -d --build
```

### After changing `.env`

Recreate the container:

```bash
cd /srv/docker/pi-assistant-loruv
sudo docker compose up -d --force-recreate
```

Alternatively:

```bash
sudo docker compose down
sudo docker compose up -d
```

### Updating from GitHub

```bash
cd /srv/docker/pi-assistant-loruv
git pull
sudo docker compose up -d --build
```

### Rebuilding without Docker cache

```bash
cd /srv/docker/pi-assistant-loruv
sudo docker compose build --no-cache
sudo docker compose up -d
```

### Verify after updating

```bash
sudo docker compose ps
```

```bash
sudo docker compose logs -f
```

---

## Viewing Logs

View live logs:

```bash
cd /srv/docker/pi-assistant-loruv
sudo docker compose logs -f
```

View the last 100 lines:

```bash
sudo docker compose logs --tail=100
```

View logs directly from the container:

```bash
sudo docker logs -f pi-assistant-loruv
```

Exit log streaming with:

```text
Ctrl + C
```

This does not stop the container.

---

## Troubleshooting

### No Telegram message is received

Check:

1. Is the bot token correct?
2. Is the authorized user ID correct?
3. Did you send `/start` to the bot?
4. Is the Raspberry Pi connected to the internet?
5. Is the container running?

```bash
sudo docker compose ps
```

View logs:

```bash
sudo docker compose logs -f
```

### The container keeps restarting

```bash
sudo docker logs --tail=100 pi-assistant-loruv
```

Verify the environment file:

```bash
cat .env
```

Do not share the output publicly because it may contain the bot token.

### Docker containers cannot be listed

Verify that the following volume exists in `compose.yaml`:

```yaml
volumes:
  - /var/run/docker.sock:/var/run/docker.sock
```

Check the Docker socket:

```bash
ls -l /var/run/docker.sock
```

### CPU temperature cannot be read

Verify the thermal volume:

```yaml
volumes:
  - /sys/class/thermal:/host/sys/class/thermal:ro
```

Check the temperature file:

```bash
cat /sys/class/thermal/thermal_zone0/temp
```

### Code changes are not applied

Rebuild the image:

```bash
cd /srv/docker/pi-assistant-loruv
sudo docker compose up -d --build
```

If necessary, rebuild without cache:

```bash
sudo docker compose build --no-cache
sudo docker compose up -d
```

---

## Security

Pi Assistant has powerful access because it connects to the Docker socket.

Follow these security recommendations:

* Never commit the `.env` file.
* Never publish the Telegram bot token.
* Allow only your own Telegram user ID.
* Do not store real credentials in public source files.
* Protect SSH access with a strong password or SSH key.
* Do not expose unnecessary ports to the internet.
* Do not expose Portainer directly to the public internet.
* Regenerate the bot token through BotFather if it is compromised.
* Understand that access to the Docker socket is close to root-level access.

### Recommended `.gitignore`

```gitignore
.env
data/
__pycache__/
*.pyc
```

---

## Roadmap

Planned improvements may include:

* Docker container logs through Telegram
* Container CPU and RAM statistics
* Inline Telegram buttons
* Scheduled system reports
* SSH login alerts
* Disk SMART monitoring
* Fan control
* Docker image update notifications
* Multiple authorized users
* Web dashboard
* Role-based access control
* Backup notifications
* Plugin system

---

## Contributing

Contributions, bug reports, suggestions, and feature requests are welcome.

Recommended workflow:

1. Fork the repository.
2. Create a new branch.
3. Make your changes.
4. Test the changes.
5. Submit a Pull Request.

Example:

```bash
git checkout -b feature/new-command
```

```bash
git add .
git commit -m "Add new Telegram command"
git push origin feature/new-command
```

---

## License

This project may be distributed under the MIT License.

Add a `LICENSE` file to the repository before publishing the project as open source.

---

## Support

If this project is useful to you, consider starring the repository.

A GitHub star helps other users discover the project and supports future development.
