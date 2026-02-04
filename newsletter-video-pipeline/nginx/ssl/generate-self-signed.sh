#!/bin/bash
# Generate self-signed SSL certificate for development
# For production, use Let's Encrypt or a proper CA

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DOMAIN="${1:-localhost}"

echo "Generating self-signed SSL certificate for: $DOMAIN"

openssl req -x509 -nodes -days 365 -newkey rsa:2048 \
    -keyout "$SCRIPT_DIR/privkey.pem" \
    -out "$SCRIPT_DIR/fullchain.pem" \
    -subj "/C=US/ST=State/L=City/O=Newsletter Video Pipeline/CN=$DOMAIN" \
    -addext "subjectAltName=DNS:$DOMAIN,DNS:localhost,IP:127.0.0.1"

echo "Certificate generated successfully!"
echo "  - Certificate: $SCRIPT_DIR/fullchain.pem"
echo "  - Private Key: $SCRIPT_DIR/privkey.pem"
echo ""
echo "For production, replace these with certificates from Let's Encrypt:"
echo "  certbot certonly --webroot -w /var/www/certbot -d your-domain.com"
