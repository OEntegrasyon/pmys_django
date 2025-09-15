#!/usr/bin/env bash
set -euo pipefail

echo "==> 1) Servisi durdur ve otomatik başlatmayı kapat"
sudo systemctl stop rabbitmq-server 2>/dev/null || true
sudo systemctl disable --now rabbitmq-server 2>/dev/null || true

echo "==> 2) Paketleri ve bağımlılıkları tamamen kaldır"
sudo apt-get purge -y rabbitmq-server || true
# Erlang da tamamen silinsin (başka uygulama kullanmıyorsa sorun değil)
sudo apt-get autoremove -y --purge 'erlang-*' esl-erlang 2>/dev/null || true

echo "==> 3) Eski veri/konfig/log ve repo dosyalarını sil"
sudo rm -rf /var/lib/rabbitmq /etc/rabbitmq /var/log/rabbitmq
sudo rm -f  /etc/apt/sources.list.d/rabbitmq*.list /etc/apt/sources.list.d/erlang*.list
sudo pkill -9 epmd 2>/dev/null || true
sudo apt-get update -y

echo "==> 4) Gerekli araçlar"
sudo apt-get install -y curl gnupg apt-transport-https

echo "==> 5) OS bilgisini al (Ubuntu/Mint/Debian uyumlu)"
. /etc/os-release
ID_LIKE_LOWER="$(echo "${ID_LIKE:-}" | tr '[:upper:]' '[:lower:]')"
BASE_ID="debian"
if [[ "${ID:-}" == "ubuntu" || "$ID_LIKE_LOWER" == *"ubuntu"* ]]; then
  BASE_ID="ubuntu"
fi
# Mint vb. için UBUNTU_CODENAME'i kullan
CODENAME="${UBUNTU_CODENAME:-${VERSION_CODENAME:-noble}}"
# Destekli değilse Ubuntu 24.04 varsay
case "$CODENAME" in
  noble|jammy|focal|trixie|bookworm|bullseye) ;;
  *) CODENAME="noble" ;;
esac

echo "==> 6) Team RabbitMQ imza anahtarı"
sudo install -d -m 0755 /usr/share/keyrings
curl -1sLf "https://keys.openpgp.org/vks/v1/by-fingerprint/0A9AF2115F4687BD29803A206B73A36E6026DFCA" \
  | sudo gpg --dearmor > /tmp/com.rabbitmq.team.gpg
sudo mv /tmp/com.rabbitmq.team.gpg /usr/share/keyrings/com.rabbitmq.team.gpg

echo "==> 7) Resmi apt depolarını ekle (RabbitMQ + modern Erlang)"
sudo tee /etc/apt/sources.list.d/rabbitmq.list >/dev/null <<EOF
## Modern Erlang/OTP
deb [arch=amd64 signed-by=/usr/share/keyrings/com.rabbitmq.team.gpg] https://deb1.rabbitmq.com/rabbitmq-erlang/${BASE_ID}/${CODENAME} ${CODENAME} main
deb [arch=amd64 signed-by=/usr/share/keyrings/com.rabbitmq.team.gpg] https://deb2.rabbitmq.com/rabbitmq-erlang/${BASE_ID}/${CODENAME} ${CODENAME} main
## Latest RabbitMQ
deb [arch=amd64 signed-by=/usr/share/keyrings/com.rabbitmq.team.gpg] https://deb1.rabbitmq.com/rabbitmq-server/${BASE_ID}/${CODENAME} ${CODENAME} main
deb [arch=amd64 signed-by=/usr/share/keyrings/com.rabbitmq.team.gpg] https://deb2.rabbitmq.com/rabbitmq-server/${BASE_ID}/${CODENAME} ${CODENAME} main
EOF

echo "==> 8) Paket listelerini güncelle"
sudo apt-get update -y

echo "==> 9) Modern Erlang + RabbitMQ kur"
sudo apt-get install -y \
  erlang-base erlang-asn1 erlang-crypto erlang-eldap erlang-ftp erlang-inets \
  erlang-mnesia erlang-os-mon erlang-parsetools erlang-public-key \
  erlang-runtime-tools erlang-snmp erlang-ssl erlang-syntax-tools \
  erlang-tftp erlang-tools erlang-xmerl

sudo apt-get install -y rabbitmq-server --fix-missing

echo "==> 10) Servisi etkinleştir ve başlat"
sudo systemctl enable --now rabbitmq-server
sudo rabbitmq-diagnostics ping
sudo rabbitmq-diagnostics status

echo "==> 11) Yönetim eklentisi (opsiyonel ama önerilir)"
sudo rabbitmq-plugins enable rabbitmq_management

echo "==> 12) Admin kullanıcı (örnek)"
sudo rabbitmqctl add_user giys giys 2>/dev/null || true
sudo rabbitmqctl set_user_tags giys administrator
sudo rabbitmqctl set_permissions -p / giys ".*" ".*" ".*"

echo "==> Bitti. Management UI: http://localhost:15672  (giys/giys)"
