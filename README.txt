PI ASSISTANT - KURULUM

1) Bu klasörü Raspberry Pi üzerinde şuraya çıkar:
   /srv/docker/pi-assistant-loruv

2) .env.example dosyasının kopyasını .env adıyla oluştur:
   cp .env.example .env

3) .env dosyasına BotFather tokenini ve Telegram kullanıcı ID'ni yaz.

4) Portainer:
   Stacks > Add stack > Name: pi-assistant-loruv
   Build method: Repository yerine Web editor seçilecekse compose.yaml içeriğini yapıştırmak
   yerel build context'i desteklemeyebilir. En sağlam yöntem terminalde bir kez:
       cd /srv/docker/pi-assistant-loruv
       docker compose up -d --build

5) Bundan sonra Portainer > Containers > pi-assistant-loruv üzerinden:
   logları gör, durdur, başlat veya yeniden oluştur.

Telegram komutları:
 /durum
 /docker
 /baslat nginx
 /durdur nginx
 /yenidenbaslat nginx
 /ip
 /yardim

GÜVENLİK:
- .env dosyasını paylaşma.
- Bot yalnızca ALLOWED_USER_ID değerindeki Telegram hesabını kabul eder.
- Docker socket erişimi güçlü bir yetkidir. Bot tokeni ele geçirilirse tokeni BotFather'dan yenile.
- Bu sürüm host Raspberry Pi'yi yeniden başlatmaz; yalnızca seçilen Docker container'ını yeniden başlatır.
