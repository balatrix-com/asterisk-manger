# Asterisk Config Manager

Focused FastAPI application for safely managing only `/etc/asterisk/pjsip.conf` and `/etc/asterisk/extensions.conf`.

## Features

- Structured extension, destination/trunk, context, and route editing
- Repeated PJSIP section names and comment preservation
- Raw editors, version-conflict detection, validation, and unified diffs
- Timestamped backups, comparison, restore, atomic writes, and failed-reload rollback
- Argon2 login, expiring secure sessions, CSRF protection, audit log
- Fixed allowlisted Asterisk commands; no arbitrary paths, commands, or shell interpolation
- Five-second external-file monitoring that preserves unsaved browser edits

## Install

```bash
sudo useradd --system --home /opt/asterisk-config-manager --shell /usr/sbin/nologin asterisk-config-manager
sudo install -d -o asterisk-config-manager -g asterisk-config-manager /opt/asterisk-config-manager /var/backups/asterisk-config-manager /var/log/asterisk-config-manager
sudo cp -a . /opt/asterisk-config-manager/
cd /opt/asterisk-config-manager
sudo -u asterisk-config-manager python3 -m venv .venv
sudo -u asterisk-config-manager .venv/bin/pip install -r requirements.txt
sudo -u asterisk-config-manager .venv/bin/python -m app.security 'LONG-ADMIN-PASSWORD'
openssl rand -hex 32
sudo install -m 0600 .env.example /etc/asterisk-config-manager.env
sudoedit /etc/asterisk-config-manager.env
```

Put the generated Argon2 value in `ADMIN_PASSWORD_HASH` and the random value in `SECRET_KEY`. Configure HTTPS through nginx or another local reverse proxy; cookies are deliberately `Secure` and the service binds to localhost.

Grant the restricted account access without running the web application as root:

```bash
sudo setfacl -m u:asterisk-config-manager:rw /etc/asterisk/pjsip.conf /etc/asterisk/extensions.conf
sudo usermod -a -G asterisk asterisk-config-manager
sudo chown -R asterisk-config-manager:asterisk-config-manager /var/backups/asterisk-config-manager /var/log/asterisk-config-manager
sudo cp asterisk-config-manager.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now asterisk-config-manager
```

Atomic replacement also requires directory write permission. The safest deployment is a dedicated ACL-controlled include directory containing only these two managed files. If sudo is mandatory, grant only parameterless audited wrappers for `asterisk -rx "pjsip reload"` and `asterisk -rx "dialplan reload"`; never grant generic shell, Asterisk, or systemctl access.

## Testing

```bash
python -m venv .venv
.venv/bin/pip install -r requirements.txt
.venv/bin/pytest -q tests
```

Tests use only temporary/workspace files and never touch `/etc/asterisk`. Rotate the `1234` passwords shown in the supplied configuration. Also correct `rewrite_contact=yes.`; structured editing normalizes it automatically.
"# asterisk-manger" 
