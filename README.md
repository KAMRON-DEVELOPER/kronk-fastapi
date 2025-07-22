# 🐳 Docker Swarm Deployment Guide for Kronk

## TLS

> **Note**: The `ca.pem` file is the Certificate Authority certificate used to verify signed certificates.
>
> **Warning**: The `ca-key.pem` file is the CA private key. **Store it securely** and **never store it as a Docker secret** in production.

```bash
# **************** 1. 🔐 Certificate Authority (CA) ****************
mkdir -p ~/certs/ca && cd ~/certs/ca
openssl genrsa -aes256 -out ca-key.pem 4096

cat > ca.cnf <<EOF
[req]
distinguished_name = dn
[dn]
[ext]
basicConstraints = critical,CA:true
keyUsage = critical,keyCertSign,cRLSign
EOF

cat > ca.cnf <<EOF
[ req ]
default_bits = 4096
prompt = no
default_md = sha256
distinguished_name = dn

[ dn ]
C = US
ST = California
L = San Francisco
O = YourOrg
CN = YourCA

[ v3_ca ]
subjectKeyIdentifier = hash
authorityKeyIdentifier = keyid:always,issuer
basicConstraints = critical, CA:TRUE
keyUsage = critical, digitalSignature, cRLSign, keyCertSign
EOF
 
openssl req -new -x509 -days 3650 -key ca-key.pem -sha256 -out ca.pem -subj "/CN=Kronk Root CA" -config ca.cnf -extensions ext
openssl req -new -x509 -days 3650 -key ca-key.pem -sha256 -out ca.pem -subj "/CN=Kronk Root CA" -config ca.cnf -extensions v3_ca


# **************** 2. 🔐 Docker Daemon TLS (for Prometheus) ****************
# Server certificate
mkdir -p ~/certs/docker && cd ~/certs/docker
openssl genrsa -out docker-server-key.pem 4096
openssl req -new -key docker-server-key.pem -out docker-server.csr -subj "/CN=127.0.0.1"
echo "subjectAltName = DNS:localhost,IP:127.0.0.1" > docker-ext.cnf
echo "extendedKeyUsage = serverAuth" >> docker-ext.cnf
openssl x509 -req -in docker-server.csr -CA ../ca/ca.pem -CAkey ../ca/ca-key.pem -CAcreateserial -out docker-server-cert.pem -days 3650 -sha256 -extfile docker-ext.cnf

# Client certificate
openssl genrsa -out docker-client-key.pem 4096
openssl req -new -key docker-client-key.pem -out docker-client.csr -subj "/CN=prometheus"
echo "extendedKeyUsage = clientAuth" > docker-client-ext.cnf
openssl x509 -req -in docker-client.csr -CA ../ca/ca.pem -CAkey ../ca/ca-key.pem -CAcreateserial -out docker-client-cert.pem -days 3650 -sha256 -extfile docker-client-ext.cnf


# **************** 3. 🔐 Redis and PostgreSQL TLS (for FastAPI) ****************

# Redis
mkdir -p ~/certs/redis && cd ~/certs/redis
openssl genrsa -out redis-server-key.pem 4096
openssl req -new -key redis-server-key.pem -out redis-server.csr -subj "/CN=redis.kronk.uz"

cat > redis-ext.cnf <<EOF
subjectAltName = DNS:localhost,DNS:redis.kronk.uz,IP:127.0.0.1
extendedKeyUsage = serverAuth
EOF

echo "subjectAltName = DNS:localhost,DNS:redis.kronk.uz,IP:127.0.0.1" > redis-ext.cnf
echo "extendedKeyUsage = serverAuth" >> redis-ext.cnf

openssl x509 -req -in redis-server.csr -CA ../ca/ca.pem -CAkey ../ca/ca-key.pem -CAcreateserial -out redis-server-cert.pem -days 3650 -sha256 -extfile redis-ext.cnf

# PostgreSQL
mkdir -p ~/certs/postgres && cd ~/certs/postgres
openssl genrsa -out pg-server-key.pem 4096
openssl req -new -key pg-server-key.pem -out pg-server.csr -subj "/CN=postgres.kronk.uz"
echo "subjectAltName = DNS:localhost,DNS:postgres.kronk.uz,IP:127.0.0.1" > pg-ext.cnf
echo "extendedKeyUsage = serverAuth" >> pg-ext.cnf
openssl x509 -req -in pg-server.csr -CA ../ca/ca.pem -CAkey ../ca/ca-key.pem -CAcreateserial -out pg-server-cert.pem -days 3650 -sha256 -extfile pg-ext.cnf

# FastAPI Client (shared for Redis and PostgreSQL)
mkdir -p ~/certs/fastapi && cd ~/certs/fastapi
openssl genrsa -out fastapi-client-key.pem 4096
openssl req -new -key fastapi-client-key.pem -out fastapi-client.csr -subj "/CN=kamronbek"

cat > client-ext.cnf <<EOF
extendedKeyUsage = clientAuth
EOF

echo "extendedKeyUsage = clientAuth" > client-ext.cnf

openssl x509 -req -in fastapi-client.csr -CA ../ca/ca.pem -CAkey ../ca/ca-key.pem -CAcreateserial -out fastapi-client-cert.pem -days 3650 -sha256 -extfile client-ext.cnf
```

---
---

## Small Configurations & Usage Guide

### Copy apropriate files like this

```bash
### 1. Move certificates to Docker's directory (accessible by root)
sudo mkdir -p /etc/docker/certs
sudo cp ~/certs/docker/docker-server-cert.pem /etc/docker/certs/
sudo cp ~/certs/docker/docker-server-key.pem /etc/docker/certs/
sudo cp ~/certs/ca/ca.pem /etc/docker/certs/
```

### 2. Set proper permissions

```bash
sudo chmod 600 /etc/docker/certs/*.pem
sudo chown root:root /etc/docker/certs/*.pem
```

### 3. Create `/etc/docker/daemon.json` configuration

```bash
sudo tee /etc/docker/daemon.json <<EOF
{
  "tls": true,
  "tlsverify": true,
  "tlscacert": "/etc/docker/certs/ca.pem",
  "tlscert": "/etc/docker/certs/docker-server-cert.pem",
  "tlskey": "/etc/docker/certs/docker-server-key.pem",
  "hosts": ["fd://", "tcp://127.0.0.1:2376"]
}
EOF
```

#### or

```json
{
  "hosts": [
    "unix:///var/run/docker.sock",
    "tcp://0.0.0.0:2376"
  ],
  "tls": true,
  "tlsverify": true,
  "tlscacert": "/etc/docker/certs/ca.pem",
  "tlscert": "/etc/docker/certs/docker-server-cert.pem",
  "tlskey": "/etc/docker/certs/docker-server-key.pem"
}
```

### 4. Fix systemd conflict (critical!)

```bash
sudo mkdir -p /etc/systemd/system/docker.service.d
sudo tee /etc/systemd/system/docker.service.d/override.conf <<EOF
[Service]
ExecStart=
ExecStart=/usr/bin/dockerd --containerd=/run/containerd/containerd.sock
EOF
```

### 5. Reload and restart

```bash
sudo systemctl daemon-reload
sudo systemctl restart docker
```

### Prometheus Docker TLS Configuration

```yaml
scrape_configs:
  - job_name: 'docker-swarm'
    dockerswarm_sd_configs:
      - host: "tcp://docker-api.kronk.uz:2376"
        role: manager
        tls_config:
          ca_file: /run/secrets/ca.pem
          cert_file: /run/secrets/client-cert.pem
          key_file: /run/secrets/client-key.pem
    scheme: https
```

---
---

## 🔧 Local Development Secret Setup

> For FastAPI to run locally with secrets, it expects files at `/run/secrets/`. Docker secrets do **not** appear there during development - you must simulate them.

### 📁 Create Local `/run/secrets` Directory

```bash
sudo mkdir -p /run/secrets
```

### 🔑 Populate Dummy Secrets for Development

You can link or copy secrets manually:

```bash
# POSTGRES
sudo cp certs/ca/ca.pem /run/secrets/ca.pem
sudo cp certs/fastapi/fastapi-client-cert.pem /run/secrets/fastapi_client_cert.pem
sudo cp certs/fastapi/fastapi-client-key.pem /run/secrets/fastapi_client_key.pem

echo "postgresql+asyncpg://kamronbek:kamronbek2003@localhost:5432/kronk_db" | sudo tee /run/secrets/DATABASE_URL

# REDIS
echo "localhost" | sudo tee /run/secrets/REDIS_HOST

# S3
echo "fra1.digitaloceanspaces.com" | sudo tee /run/secrets/S3_ENDPOINT
echo "fra1" | sudo tee /run/secrets/S3_REGION
echo "DO00J2BEN93Y8P6LBEYR" | sudo tee /run/secrets/S3_ACCESS_KEY_ID
echo "n7zzLc5yZcnXA9f/v+vIVnP3pjxkE6NDNi4CEEnTM+E" | sudo tee /run/secrets/S3_SECRET_KEY
echo "kronk-bucket" | sudo tee /run/secrets/S3_BUCKET_NAME

# S3 LOCAL
echo "localhost:9000" | sudo tee /run/secrets/S3_ENDPOINT
echo "fra1" | sudo tee /run/secrets/S3_REGION
echo "DO00J2BEN93Y8P6LBEYR" | sudo tee /run/secrets/S3_ACCESS_KEY_ID
echo "n7zzLc5yZcnXA9f/v+vIVnP3pjxkE6NDNi4CEEnTM+E" | sudo tee /run/secrets/S3_SECRET_KEY
echo "kronk-digitalocean-bucket" | sudo tee /run/secrets/S3_BUCKET_NAME

# FASTAPI-JWT
echo "f94b638b565c503932b657534d1f044b7f1c8acfb76170e80851704423a49186" | sudo tee /run/secrets/SECRET_KEY

# EMAIL
echo "wSsVR61z+0b3Bq9+mzWtJOc+yAxSUgv1HEx93Qaoun79Sv7KosduxECdBw/1HPBLGDNpQWAU9bN/yx0C0GUN2dh8mVAGDSiF9mqRe1U4J3x17qnvhDzIWWtYlxGNLIkLzwlumWdiEssi+g==" |sudo tee /run/secrets/EMAIL_SERVICE_API_KEY
```

---
---

## 4. 🔑 Docker Secrets Creation

### 🐳 On VPS Manager (only secrets needed by fastapi)

```bash
# for prometheus & fastapi
cd ~/certs/docker
docker secret create ca.pem ~/certs/ca/ca.pem
docker secret create docker-client-cert.pem ~/certs/docker/docker-client-cert.pem
docker secret create docker-client-key.pem ~/certs/docker/docker-client-key.pem
# docker secret create fastapi-client-cert.pem ~/certs/fastapi/fastapi-client-cert.pem
# docker secret create fastapi-client-key.pem ~/certs/fastapi/fastapi-client-key.pem

# POSTGRES
echo "postgresql+asyncpg://kamronbek:kamronbek2003@postgres.kronk.uz:5432/kronk_db" | docker secret create DATABASE_URL -

# REDIS
echo "redis.kronk.uz" | docker secret create REDIS_HOST -

# FIREBASE
docker secret create FIREBASE_ADMINSDK ~/certs/kronk-production-firebase-adminsdk.json

# S3 -
echo "fra1.digitaloceanspaces.com" | docker secret create S3_ENDPOINT -
echo "fra1" | docker secret create S3_REGION -
echo "DO00J2BEN93Y8P6LBEYR" | docker secret create S3_ACCESS_KEY_ID -
echo "n7zzLc5yZcnXA9f/v+vIVnP3pjxkE6NDNi4CEEnTM+E" | docker secret create S3_SECRET_KEY -
echo "kronk-digitalocean-bucket" | docker secret create S3_BUCKET_NAME -

# FASTAPI-JWT
echo "f94b638b565c503932b657534d1f044b7f1c8acfb76170e80851704423a49186" | docker secret create SECRET_KEY -

# EMAIL
echo "wSsVR61z+0b3Bq9+mzWtJOc+yAxSUgv1HEx93Qaoun79Sv7KosduxECdBw/1HPBLGDNpQWAU9bN/yx0C0GUN2dh8mVAGDSiF9mqRe1U4J3x17qnvhDzIWWtYlxGNLIkLzwlumWdiEssi+g==" | docker secret create EMAIL_SERVICE_API_KEY -

# MONITORING
echo "$(htpasswd -nbB kamronbek kamronbek2003)" | docker secret create MONITORING_CREDENTIALS -
echo "kamronbek" | docker secret create GF_SECURITY_ADMIN_USER -
echo "kamronbek2003" | docker secret create GF_SECURITY_ADMIN_PASSWORD -
```

### 🐳 On VPS with Redis & PostgreSQL (Prod Swarm Node)

```bash
docker network create -d bridge local_network_bridge

mkdir -p volumes/redis_storage
mkdir -p volumes/postgres_storage

docker compose up -d
```

---
---

## 5. 🔧 Initialize Docker Swarm

```bash
docker swarm init --advertise-addr <MANAGER_NODE_PUBLIC_IP>
docker swarm join-token worker
docker swarm join --token <TOKEN> <MANAGER_NODE_PUBLIC_IP>:2377
```

---
---

## 6. 🌐 Create Overlay Network

```bash
docker network create --driver=overlay --attachable traefik-network
```

---
---

## 7. 🔐 Set Permissions on ACME File

```bash
chmod 600 cluster/swarm/traefik/config/acme.json
```

---
---

## 8. 📆 Deploy Services

```bash
docker context use dev-kronk

docker stack deploy -c cluster/swarm/traefik/docker-compose.traefik.yml traefik -d
docker stack deploy -c cluster/swarm/prometheus/docker-compose.prometheus.yml prometheus -d
docker stack deploy -c cluster/swarm/grafana/docker-compose.grafana.yml grafana -d
docker stack deploy -c cluster/swarm/monitoring/docker-compose.cadvisor.yml cadvisor -d
docker stack deploy -c cluster/swarm/monitoring/docker-compose.node_exporter.yml node_exporter -d
docker stack deploy -c cluster/swarm/backend/docker-compose.fastapi.yml fastapi -d
docker stack deploy -c cluster/swarm/backend/docker-compose.taskiq_scheduler.yml taskiq_scheduler -d
docker stack deploy -c cluster/swarm/backend/docker-compose.taskiq_worker.yml taskiq_worker -d

docker stack deploy -c traefik/docker-compose.traefik.yml traefik -d
docker stack deploy -c prometheus/docker-compose.prometheus.yml prometheus -d
docker stack deploy -c grafana/docker-compose.grafana.yml grafana -d
docker stack deploy -c monitoring/docker-compose.cadvisor.yml cadvisor -d
docker stack deploy -c monitoring/docker-compose.node_exporter.yml node_exporter -d
docker stack deploy -c backend/docker-compose.fastapi.yml fastapi -d
docker stack deploy -c backend/docker-compose.taskiq_scheduler.yml taskiq_scheduler -d
docker stack deploy -c backend/docker-compose.taskiq_worker.yml taskiq_worker -d
```

---
---

## Tips & Tricks

### Connecting to postgres

```bash
# first
~/Documents/fastapi/kronk-backend-production/service master !3 ❯ CONTAINER_ID=$(docker ps -qf "name=postgres_postgres")                                            ✘ INT
~/Documents/fastapi/kronk-backend-production/service master !3 ❯ docker exec -it $CONTAINER_ID /bin/sh -c '
export PGPASSWORD=$(cat /run/secrets/POSTGRES_PASSWORD)
export PGSSLMODE=verify-full
export PGSSLROOTCERT=/run/secrets/ca.pem
export PGSSLCERT=/run/secrets/fastapi_client_cert.pem
export PGSSLKEY=/var/lib/postgresql/certs/fastapi_client_key.pem
psql -h localhost -d $(cat /run/secrets/POSTGRES_DB) -U $(cat /run/secrets/POSTGRES_USER)
'

# second
~/Documents/fastapi/kronk-backend-production/service master !3 ❯ PGPASSWORD=kamronbek2003 \                                                                           5s
PGSSLMODE=verify-full \
PGSSLROOTCERT=~/certs/ca/ca.pem \
PGSSLCERT=~/certs/fastapi/fastapi-client-cert.pem \
PGSSLKEY=~/certs/fastapi/fastapi-client-key.pem \
psql -h 127.0.0.1 -U kamronbek -d kronk_db

# third
psql "sslmode=verify-full sslrootcert=/home/kamronbek/certs/ca/ca.pem sslcert=/home/kamronbek/certs/fastapi/fastapi-client-cert.pem sslkey=/home/kamronbek/certs/fastapi/fastapi-client-key.pem host=localhost hostaddr=127.0.0.1 port=5432 user=kamronbek dbname=kronk_db"
```

### Connecting to redis

```bash
redis-cli --tls --cacert ~/certs/ca/ca.pem --cert ~/certs/fastapi/fastapi-client-cert.pem --key ~/certs/fastapi/fastapi-client-key.pem -a kamronbek2003
```

---
---
