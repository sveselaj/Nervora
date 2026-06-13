# Terraform — Azure reference deployment

Reference IaC for the production topology. **Not** a turnkey production module —
review networking (private endpoints / VNet integration), secret management
(prefer Key Vault references over inline secrets), and identity (managed
identity for Service Bus / Postgres) before any real use.

```bash
cd infra/terraform
terraform init
terraform plan \
  -var "pg_admin_password=$(openssl rand -base64 24)" \
  -var "gateway_image=<registry>/mcp-gateway:latest" \
  -var "worker_image=<registry>/mcp-worker:latest" \
  -var "entra_tenant_id=<tenant-guid>" \
  -var "entra_issuer=https://login.microsoftonline.com/<tenant-guid>/v2.0" \
  -var "entra_jwks_url=https://login.microsoftonline.com/<tenant-guid>/discovery/v2.0/keys"
terraform apply
```

A Bicep equivalent lives in `../bicep/main.bicep` for teams standardised on
Bicep/ARM.
