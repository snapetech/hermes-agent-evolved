# Hindsight Example Profile

This directory contains public-safe Hindsight configuration scaffolding for the
evolved deployment shape.

Hindsight is optional. Use it when you want structured long-term memory instead
of relying only on prompt-visible `MEMORY.md` and `USER.md` summaries.

## Integration Steps

1. Deploy a Hindsight API and database using your own secret management.
2. Copy `hindsight-config.example.json` into the Hermes home as
   `/opt/data/hindsight/config.json`.
3. Change Hermes `config.yaml`:

   ```yaml
   memory:
     memory_enabled: true
     user_profile_enabled: true
     provider: hindsight
   ```

4. Set the Hindsight API URL to your service endpoint.
5. Validate memory write/read behavior before relying on it for operations.

The private deployment has a full in-cluster Hindsight manifest under
`deploy/k8s/hindsight.yaml`. Treat it as an implementation reference, not a
public-ready manifest, because it includes live-cluster image and endpoint
assumptions that public users must replace.

