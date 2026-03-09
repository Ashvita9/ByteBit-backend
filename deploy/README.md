# ByteBit Backend — GCE Deployment Guide

Stack: **Daphne** (ASGI) → **Nginx** (reverse proxy) → **systemd** (process manager)  
DB: MongoDB Atlas (remote) · Channel layer: Redis (local on VM) · CI: GitHub Actions

---

## Directory layout on the VM

```
/opt/bytebit/
├── app/                    ← git clone of this repo
│   └── ByteBit-backend/
│       ├── deploy/         ← these scripts
│       └── ...
├── venv/                   ← Python virtual environment
└── .env                    ← production secrets (never commit)
```

---

## 1. Create the GCE VM

In the GCP Console (or `gcloud`):

| Setting | Recommended value |
|---------|------------------|
| Machine type | `e2-small` (2 vCPU, 2 GB) or larger |
| OS | Ubuntu 22.04 LTS |
| Boot disk | 20 GB SSD |
| Firewall | Allow HTTP (80) and HTTPS (443) |
| Region | Pick closest to your users |

```bash
gcloud compute instances create bytebit-backend \
  --machine-type=e2-small \
  --image-family=ubuntu-2204-lts \
  --image-project=ubuntu-os-cloud \
  --boot-disk-size=20GB \
  --tags=http-server,https-server \
  --zone=us-central1-a
```

---

## 2. Run the bootstrap script (once)

SSH into the VM and run (as root):

```bash
sudo bash /path/to/gce-setup.sh https://github.com/YOU/ByteBit.git main
```

The script will:
- Install Python 3.12, Nginx, Redis
- Create the `bytebit` OS user
- Clone the repo to `/opt/bytebit/app`
- Create the virtualenv and install dependencies
- Install the systemd service and Nginx config
- Generate and print a deploy SSH key pair

---

## 3. Configure secrets

```bash
sudo nano /opt/bytebit/.env
```

Fill in every value from `gce.env.example`.  
Set permissions: `sudo chmod 600 /opt/bytebit/.env`

---

## 4. Update Nginx config

```bash
sudo nano /etc/nginx/sites-available/bytebit-backend
# Replace YOUR_DOMAIN_OR_IP with your VM's external IP or domain
sudo nginx -t && sudo systemctl reload nginx
```

---

## 5. Start the service

```bash
sudo systemctl enable --now bytebit-backend
sudo systemctl status bytebit-backend
```

Check logs: `sudo journalctl -u bytebit-backend -f`

---

## 6. (Optional) HTTPS with Let's Encrypt

```bash
sudo apt-get install -y certbot python3-certbot-nginx
sudo certbot --nginx -d your.domain.com
```

---

## 7. Configure GitHub Actions

Go to **Settings → Secrets and variables → Actions** in your GitHub repo and add:

| Secret name | Value |
|-------------|-------|
| `GCE_SSH_HOST` | VM external IP (e.g. `34.123.45.67`) |
| `GCE_SSH_USER` | `bytebit` |
| `GCE_SSH_KEY` | Full contents of the private deploy key (printed by `gce-setup.sh`) |
| `GCE_SSH_PORT` | `22` |

Every push to `main` that changes anything inside `ByteBit-backend/` will now:
1. SSH into the VM
2. Run `deploy.sh` (git pull → pip install → collectstatic → migrate → restart)
3. Hit the `/api/health/` endpoint to confirm the service came up

---

## Useful commands on the VM

```bash
# Service status / logs
sudo systemctl status bytebit-backend
sudo journalctl -u bytebit-backend -n 100 -f

# Manual re-deploy
bash /opt/bytebit/app/ByteBit-backend/deploy/deploy.sh

# Nginx
sudo nginx -t
sudo systemctl reload nginx
sudo tail -f /var/log/nginx/error.log

# Redis
redis-cli ping        # → PONG
redis-cli INFO server
```
