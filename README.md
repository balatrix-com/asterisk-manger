# Asterisk Config Manager

FastAPI application for managing `/etc/asterisk/pjsip.conf` and `/etc/asterisk/extensions.conf`, with an optional Asterisk call testing dialer.

## Features

- Structured extension, destination/trunk, context, and route editing
- Repeated PJSIP section names and comment preservation
- Raw editors, version-conflict detection, validation, and unified diffs
- Timestamped backups, comparison, restore, atomic writes, and failed-reload rollback
- Argon2 login, expiring secure sessions, CSRF protection, audit log
- Fixed allowlisted Asterisk CLI commands; no arbitrary paths, commands, or shell interpolation
- Five-second external-file monitoring that preserves unsaved browser edits
- Call dialer tab that originates one Asterisk call at a time, redials after hangup, and clears its target on Stop

## Asterisk call dialer setup

The Call dialer tab uses Asterisk AMI over localhost. It does not use SIPp. The entered number and SIP target are held only in application memory and are omitted from the audit log. Use one Uvicorn worker; multiple workers would have separate call state.

Enable AMI on `127.0.0.1:5038` in `/etc/asterisk/manager.conf`, keeping any existing AMI settings. Add a dedicated account with a long random secret:

```ini
[config-manager-dialer]
secret=REPLACE_WITH_RANDOM_SECRET
deny=0.0.0.0/0.0.0.0
permit=127.0.0.1/255.255.255.255
read=call
write=call,originate
```

Add these settings to `/etc/asterisk-config-manager.env` using the same secret:

```ini
AMI_HOST=127.0.0.1
AMI_PORT=5038
AMI_USERNAME=config-manager-dialer
AMI_SECRET=REPLACE_WITH_RANDOM_SECRET
DIALER_ENDPOINT=dialer-test
```

The dialer sends an explicit SIP URI through `DIALER_ENDPOINT`. For generic unauthenticated G.711 A-law tests, add a dedicated PJSIP endpoint to `/etc/asterisk/pjsip.conf` (or its existing included custom file):

```ini
[dialer-test]
type=endpoint
transport=transport-udp
context=default
disallow=all
allow=alaw
direct_media=no
```

Use an existing outbound endpoint instead when the target requires specific caller identity, codecs, or authentication. Asterisk's existing UDP transport sends from its bound SIP port, which is 5060 on the server shown in this setup. The dialer uses AMI `Originate` with `Application: Echo`, watches `Newstate` and `Hangup`, and uses `Hangup` on Stop. If AMI connectivity is lost while a call may still be active, automatic redial stops to prevent a duplicate call; Stop reconnects and checks the exact channel before clearing the target.

After configuring AMI and the endpoint:

```bash
sudo asterisk -rx 'manager reload'
sudo asterisk -rx 'pjsip reload'
sudo systemctl restart asterisk-config-manager
sudo systemctl status asterisk-config-manager
```

The separate `sip-loop-dialer` prototype is not required for this integrated tab. Do not run both dialers against the same test number.

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
"# asterisk-manger" 
