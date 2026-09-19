# Local tunnel

Hem listens at `http://127.0.0.1:8010`. Download the Windows cloudflared binary from
https://github.com/cloudflare/cloudflared/releases into `data/tools/cloudflared.exe`.
The data directory is ignored by Git.

Start the API from the repository root using the command in README.md, then run:

```powershell
./data/tools/cloudflared.exe tunnel --url http://127.0.0.1:8010 --no-autoupdate 2> data/tunnel.log
```

Quick tunnels have temporary URLs and require both processes to remain running.
Use a stable named tunnel or deployment for ongoing service.

Register the tunnel using an API-owned Linq line (not the recipient's personal number):

```powershell
.venv/Scripts/python.exe scripts/register_webhook.py +YOUR_LINQ_NUMBER
```

The script saves the one-time signing secret to `.env` and backs up the response
in `data/linq-subscription.json`. It refuses duplicate registration if that file
exists. Restart the API after registration. If the tunnel URL changes, update the
existing subscription in Linq before testing delivery. Set `HEM_SEND_MESSAGES=true`
and restart the server to enable replies to incoming texts.
