# Reddit Miner Bulut Kurulum Rehberi (VPS Deployment)

Bu rehber, Reddit Miner pipeline'ını 7/24 otonom çalışacak şekilde bir bulut sunucusuna (VPS) nasıl kuracağınızı anlatır.

## 1. Sunucu Hazırlığı

- **Önerilen**: Ubuntu 22.04 LTS (DigitalOcean Droplet, AWS EC2 nano vb.)
- **Gereksinimler**: Python 3.10+, Redis, Git.

### Paket Kurulumu (Ubuntu Örneği)
```bash
sudo apt update && sudo apt upgrade -y
sudo apt install python3-pip python3-venv redis-server redis-tools git -y
```

## 2. Projeyi Klonlama ve Ortam Kurulumu

```bash
git clone <sizin-repo-urlniz>
cd reddit-miner
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

## 3. Ortam Değişkenleri (.env)

Sunucuda bir `.env` dosyası oluşturun ve aşağıdaki değişkenleri ekleyin (Local'deki `.env` içeriğini kopyalayabilirsiniz):

```ini
GEMINI_API_KEY=your_gemini_key
TELEGRAM_BOT_TOKEN=your_bot_token
TELEGRAM_CHAT_ID=your_chat_id
REDIS_URL=redis://localhost:6379
# Opsiyonel:
# PRAW_CLIENT_ID=...
# PRAW_CLIENT_SECRET=...
```

## 4. Otonom Çalıştırma (7/24)

### Seçenek A: tmux (En Basit)
Sunucu bağlantınız kopsa bile işlemin devam etmesi için `tmux` kullanın:

```bash
tmux new -s reddit-miner
# tmux içine girince:
source venv/bin/activate
python main.py schedule --hour 7 --minute 0
```
*(Ayrılmak için: `Ctrl+B` sonra `D`)*

### Seçenek B: systemd (Profesyonel/Kalıcı)
Sunucu yeniden başlasa bile otomatik devreye girmesi için bir servis dosyası oluşturun:

`/etc/systemd/system/reddit-miner.service`:
```ini
[Unit]
Description=Reddit Miner Autonomous Pipeline
After=network.target redis.service

[Service]
User=ubuntu
WorkingDirectory=/home/ubuntu/reddit-miner
ExecStart=/home/ubuntu/reddit-miner/venv/bin/python main.py schedule --hour 7 --minute 0
Restart=always

[Install]
WantedBy=multi-user.target
```

### Seçenek C: Docker Compose (EN HIZLI & ÖNERİLEN) 🚀
Eğer sunucuda Docker ve Docker Compose yüklüyse, tek komutla her şeyi (Redis dahil) ayağa kaldırabilirsiniz:

```bash
# Sadece .env dosyanızı hazırlayın
docker-compose up -d --build
```
Bu yöntemle:
- Redis otomatik kurulur ve yapılandırılır.
- Pipeline her zaman arka planda çalışır.
- Sunucu kapansa bile otomatik kalkar.

### Seçenek D: Render.com — Ücretsiz Cron Job (EN HIZLI & ÜCRETSİZ) ☁️
Eğer bir VPS ile uğraşmak istemiyorsanız, Render.com üzerinden ücretsiz bir Cron Job olarak deploy edebilirsiniz:

1. **GitHub'a Push Edin**: Kodunuzu bir GitHub reposuna yükleyin.
2. **Render.com Paneli**: "New +" -> "Cron Job" seçeneğini seçin.
3. **Yapılandırma**:
   - **Runtime**: `Python 3`
   - **Build Command**: `pip install -r requirements.txt`
   - **Schedule Command**: `python main.py run`  *(Sadece run, schedule değil!)*
   - **Schedule**: `0 5 * * *` (Her sabah 08:00 TR saati)
4. **Environment Variables**: "Advanced" kısmından `GEMINI_API_KEY`, `TELEGRAM_BOT_TOKEN` vb. tüm `.env` içeriğini ekleyin.

---

## 5. İzleme ve Loglar

- **Manuel Loglar**: `docker-compose logs -f` veya Render panelindeki "Logs" sekmesinden.
- **LangSmith**: `LANGCHAIN_API_KEY` tanımlanmışsa web üzerinden izlemeye devam edebilirsiniz.
