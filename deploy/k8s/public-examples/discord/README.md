# Discord Example Overlay

This overlay adds Discord gateway environment variables to the minimal public
profile.

Before applying, create the token secret:

```bash
kubectl -n hermes create secret generic hermes-discord \
  --from-literal=DISCORD_BOT_TOKEN='replace-with-bot-token' \
  --dry-run=client -o yaml | kubectl apply -f -
```

Then replace the placeholders in `patch-discord-env.yaml`:

- `<discord-user-id>`
- `<discord-channel-id>`

Apply:

```bash
kubectl apply -k deploy/k8s/public-examples/discord
```

