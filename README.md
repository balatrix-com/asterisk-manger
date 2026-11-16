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
- Call dialer tab for 1–10 numbers, each with one active call, independent redial after hangup, a 10 digit caller ID, and an Echo or continuous audio mode

## Asterisk call dialer setup

The Call dialer tab uses Asterisk AMI over localhost. It does not use SIPp. Enter 1–10 distinct destination numbers (one per line or comma separated), a 10 digit caller ID, and one SIP server IP and port. Each number runs in its own call loop and is redialed only after its previous call ends. Stop hangs up all test calls. Entered numbers, caller ID, and SIP target are held only in application memory and are omitted from the audit log. Use one Uvicorn worker; multiple workers would have separate call state.

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

Use an existing outbound endpoint instead when the target requires specific caller identity, codecs, or authentication. Asterisk's existing UDP transport sends from its bound SIP port, which is 5060 on the server shown in this setup. The dialer sends the entered caller ID in AMI's `Originate` action; the endpoint or provider may still override the identity in the outbound SIP INVITE. The dialer watches `Newstate` and `Hangup`, and uses `Hangup` on Stop. If AMI connectivity is lost while a call may still be active, automatic redial stops for that number to prevent a duplicate call; Stop reconnects and checks its exact channel before clearing the target.

For media tests, select **Send test audio continuously**. Once the far end answers, the AMI Originate runs `MusicOnHold(default)` on that call. Asterisk sends the default hold music until the call ends. All destinations use the same media mode for a test run. Confirm the Asterisk `res_musiconhold` module is loaded and the `default` music class has playable files:

```bash
sudo asterisk -rx 'module show like res_musiconhold'
sudo asterisk -rx 'moh show classes'
```

If `default` is absent, configure it in Asterisk's `musiconhold.conf` and install audio files in its configured directory before testing. A connected status means SIP answered; it does not prove RTP reached the far end. Listen at the receiving endpoint or inspect RTP at both ends to verify audio delivery. **Echo audio sent by the remote side** runs `Echo()` instead, returning media received from the far end. Use it with a remote endpoint that sends audio to check the return path. A single call cannot run both applications simultaneously.

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
