# Deployment Guide (Lightsail + HTTPS)

This guide assumes Ubuntu, a `deploy` user, and the domain `ordinarium.com`.

## Server setup

```bash
sudo apt update
sudo apt install -y python3 python3-venv python3-pip apache2 certbot python3-certbot-apache git

sudo adduser deploy
sudo usermod -aG www-data deploy
```

### SSH key for deploy

```bash
sudo mkdir -p /home/deploy/.ssh
sudo chmod 700 /home/deploy/.ssh
sudo nano /home/deploy/.ssh/authorized_keys
sudo chmod 600 /home/deploy/.ssh/authorized_keys
sudo chown -R deploy:deploy /home/deploy/.ssh
```

## App install

```bash
sudo mkdir -p /srv/ordinarium
sudo chown deploy:deploy /srv/ordinarium
su - deploy

cd /srv/ordinarium
git clone git@github.com:rwillers/ordinarium.git .
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

### Repo deploy key (server -> GitHub)

```bash
su - deploy
ssh-keygen -t ed25519 -C "ordinarium-server"
cat ~/.ssh/id_ed25519.pub
```

Add the public key as a Deploy Key in GitHub (read-only is fine).

Create `/srv/ordinarium/.env`:
```
FLASK_ENV=production
SECRET_KEY=REPLACE_WITH_LONG_RANDOM
```

## systemd (gunicorn)

Create `/etc/systemd/system/ordinarium.service`:
```
[Unit]
Description=Ordinarium Gunicorn
After=network.target

[Service]
User=deploy
Group=www-data
WorkingDirectory=/srv/ordinarium
EnvironmentFile=/srv/ordinarium/.env
ExecStart=/srv/ordinarium/venv/bin/gunicorn -w 3 -b 127.0.0.1:8000 app:app
Restart=always

[Install]
WantedBy=multi-user.target
```

```bash
sudo systemctl daemon-reload
sudo systemctl enable ordinarium
sudo systemctl start ordinarium
```

## Apache (virtual host)

Enable Apache proxy modules:

```bash
sudo a2enmod proxy proxy_http headers rewrite ssl
sudo systemctl restart apache2
```

Create `/etc/apache2/sites-available/ordinarium.com.conf`:
```
<VirtualHost *:80>
    ServerName ordinarium.com
    ServerAlias www.ordinarium.com

    ProxyPreserveHost On
    ProxyPass / http://127.0.0.1:8000/
    ProxyPassReverse / http://127.0.0.1:8000/

    RequestHeader set X-Forwarded-Proto "http"
</VirtualHost>
```

```bash
sudo a2ensite ordinarium.com.conf
sudo apache2ctl configtest
sudo systemctl reload apache2
```

## HTTPS (Let’s Encrypt)

```bash
sudo certbot --apache -d ordinarium.com -d www.ordinarium.com
```

## GitHub Actions deployment

Add GitHub secrets:
- `LIGHTSAIL_HOST`
- `LIGHTSAIL_USER` (set to `deploy`)
- `LIGHTSAIL_SSH_KEY` (private key for deploy)

The workflow in `.github/workflows/deploy.yml` runs `./scripts/deploy.sh` on push to `main`.

If `deploy` cannot run `sudo systemctl restart ordinarium`, add a sudoers entry:
```
deploy ALL=NOPASSWD: /bin/systemctl restart ordinarium
```
