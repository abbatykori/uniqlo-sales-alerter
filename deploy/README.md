# Deployment templates

## Portainer App Template

Add this fork as a one-click app in Portainer:

1. Open Portainer → **Settings** → **App Templates**.
2. Paste the raw URL of `portainer-template.json` into the **App Templates URL** field:

   ```
   https://raw.githubusercontent.com/abbatykori/uniqlo-sales-alerter/main/deploy/portainer-template.json
   ```

3. Save. The "Uniqlo Sales Alerter (Abbaty Fork)" template appears under **App Templates**.
4. Click **Deploy the stack**. Fill in `ALERTER_SECRET` (or leave blank to auto-generate), `STORE_COUNTRY`, and one or more comma-separated `NOTIFICATIONS_APPRISE_URLS`.
5. The container exposes port 8000. Visit `http://<host>:8000/ui/` for the Deals view and `http://<host>:8000/health` to confirm it's running.

### Reverse proxy notes

Behind Caddy (the typical Synology setup):

```
uniqlo.example.com {
    reverse_proxy localhost:8000
}
```

Set `SERVER_URL=https://uniqlo.example.com` in the container env so the signed action URLs in notifications point at the public hostname.

## Plain docker-compose

The root `docker-compose.yml` deploys the same image with named volumes. Edit it directly or copy it into your stack.
