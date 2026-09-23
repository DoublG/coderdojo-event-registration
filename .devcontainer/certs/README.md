# Local dev TLS for coolregistration.localhost

This is a purely local-dev CA and certificate — not for any real environment.
It lets the `proxy` container in `docker-compose.yml` serve `https://coolregistration.localhost`
without browser warnings, once `pki/ca.crt` is trusted by your host.

`fullchain.pem` and `server.key` (used by nginx, see `../nginx/nginx.conf`) are generated
from `pki/`. Everything under `pki/private/`, `server.key`, and `fullchain.pem` is git-ignored —
regenerate them locally, never commit them.

## Regenerating

```sh
cd .devcontainer/certs
rm -rf pki fullchain.pem server.key
mkdir -p pki/private pki/issued
cd pki

# CA (10 year, unencrypted key — local dev only)
openssl genrsa -out private/ca.key 4096
openssl req -x509 -new -nodes -key private/ca.key -sha256 -days 3650 \
  -subj "/CN=coolregistration.localhost Dev CA/O=CoderDojo Belgium Dev" \
  -out ca.crt

# Server key + cert, with the SAN modern browsers require
openssl genrsa -out private/coolregistration.localhost.key 2048
cat > server-ext.cnf <<'EOF'
[req]
distinguished_name = req_distinguished_name
req_extensions = v3_req
prompt = no

[req_distinguished_name]
CN = coolregistration.localhost

[v3_req]
subjectAltName = @alt_names
basicConstraints = CA:FALSE
keyUsage = digitalSignature, keyEncipherment
extendedKeyUsage = serverAuth

[alt_names]
DNS.1 = coolregistration.localhost
EOF

openssl req -new -key private/coolregistration.localhost.key -out coolregistration.localhost.csr -config server-ext.cnf
openssl x509 -req -in coolregistration.localhost.csr -CA ca.crt -CAkey private/ca.key -CAcreateserial \
  -out issued/coolregistration.localhost.crt -days 825 -sha256 \
  -extfile server-ext.cnf -extensions v3_req
rm -f coolregistration.localhost.csr

cd ..
cat pki/issued/coolregistration.localhost.crt pki/ca.crt > fullchain.pem
cp pki/private/coolregistration.localhost.key server.key
```

(We previously used `easy-rsa` for this, per its own README convention of
`easyrsa build-server-full coolregistration.localhost nopass` — but current
`easy-rsa` + OpenSSL 3.5 on this box hits a provider bug that forces an
interactive passphrase prompt even for `nopass` keys, so we generate the CA
and cert with plain `openssl` instead. Functionally identical result.)

## Trusting the CA on your host

The container trusts `pki/ca.crt` automatically (`.devcontainer/start.sh`). Your
**host** OS/browser also needs to trust it to avoid HTTPS warnings:

**Linux (Debian/Ubuntu):**
```sh
sudo cp .devcontainer/certs/pki/ca.crt /usr/local/share/ca-certificates/coolregistration-dev-ca.crt
sudo update-ca-certificates
```
Firefox uses its own trust store, not the OS one — import `pki/ca.crt` under
Settings → Privacy & Security → Certificates → View Certificates → Authorities → Import.

**Windows:**
```
certutil -addstore -user Root .devcontainer\certs\pki\ca.crt
```
then restart the browser.

**macOS:**
```sh
sudo security add-trusted-cert -d -r trustRoot -k /Library/Keychains/System.keychain .devcontainer/certs/pki/ca.crt
```
