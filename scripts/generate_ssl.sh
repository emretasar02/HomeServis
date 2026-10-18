#!/usr/bin/env bash
# HomeServis - Self-Signed SSL Sertifika Oluşturma Scripti
# Mobil bildirimler (Web Push) ve güvenli kamera erişimi için gereklidir.

set -e

echo "🔐 HomeServis için SSL sertifikası üretiliyor..."

openssl req -x509 -newkey rsa:4096 -nodes \
  -keyout key.pem \
  -out cert.pem \
  -days 365 \
  -subj "/C=TR/ST=Istanbul/L=Home/O=HomeServis/OU=IoT/CN=homeservis.local"

chmod 600 key.pem
chmod 644 cert.pem

echo "✅ 'cert.pem' ve 'key.pem' başarıyla oluşturuldu!"
