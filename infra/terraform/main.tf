# Nervora — Secure MCP Gateway · Azure reference deployment (Terraform).
#
# Provisions the production topology described in docs/azure-deployment.md:
#   * Resource group
#   * Azure Database for PostgreSQL Flexible Server (audit + job store)
#   * Azure Service Bus namespace + queue (with dead-letter / max delivery)
#   * Container Apps environment + apps (gateway, worker)
#   * Log Analytics + Application Insights (OpenTelemetry backend)
#
# This is reference IaC: review networking, private endpoints, and secret
# handling (Key Vault) before any real deployment. Auth uses Entra ID at
# runtime (AUTH_MODE=entra); no signing secrets are provisioned here.

terraform {
  required_version = ">= 1.6"
  required_providers {
    azurerm = {
      source  = "hashicorp/azurerm"
      version = "~> 3.110"
    }
  }
}

provider "azurerm" {
  features {}
}

variable "prefix"   { type = string  default = "smcpgw" }
variable "location" { type = string  default = "westeurope" }
variable "pg_admin_login"    { type = string  default = "smgadmin" }
variable "pg_admin_password" { type = string  sensitive = true }
variable "gateway_image" { type = string  description = "Fully-qualified gateway container image" }
variable "worker_image"  { type = string  description = "Fully-qualified worker container image" }
variable "entra_tenant_id" { type = string }
variable "entra_audience"  { type = string  default = "api://secure-mcp-gateway" }
variable "entra_issuer"    { type = string }
variable "entra_jwks_url"  { type = string }

resource "azurerm_resource_group" "rg" {
  name     = "${var.prefix}-rg"
  location = var.location
}

# --- PostgreSQL ------------------------------------------------------------
resource "azurerm_postgresql_flexible_server" "pg" {
  name                          = "${var.prefix}-pg"
  resource_group_name           = azurerm_resource_group.rg.name
  location                      = azurerm_resource_group.rg.location
  version                       = "16"
  administrator_login           = var.pg_admin_login
  administrator_password        = var.pg_admin_password
  sku_name                      = "B_Standard_B1ms"
  storage_mb                    = 32768
  public_network_access_enabled = false
  zone                          = "1"
}

resource "azurerm_postgresql_flexible_server_database" "db" {
  name      = "smg"
  server_id = azurerm_postgresql_flexible_server.pg.id
  charset   = "UTF8"
  collation = "en_US.utf8"
}

# --- Service Bus -----------------------------------------------------------
resource "azurerm_servicebus_namespace" "sb" {
  name                = "${var.prefix}-sb"
  resource_group_name = azurerm_resource_group.rg.name
  location            = azurerm_resource_group.rg.location
  sku                 = "Standard"
}

resource "azurerm_servicebus_queue" "jobs" {
  name         = "tool-jobs"
  namespace_id = azurerm_servicebus_namespace.sb.id

  # Retry / DLQ contract: messages dead-letter after max_delivery_count
  # failed deliveries, and on lock/TTL expiry.
  max_delivery_count                      = 5
  dead_lettering_on_message_expiration    = true
  lock_duration                           = "PT30S"
  default_message_ttl                     = "P1D"
}

# --- Observability ---------------------------------------------------------
resource "azurerm_log_analytics_workspace" "law" {
  name                = "${var.prefix}-law"
  resource_group_name = azurerm_resource_group.rg.name
  location            = azurerm_resource_group.rg.location
  sku                 = "PerGB2018"
  retention_in_days   = 30
}

resource "azurerm_application_insights" "appi" {
  name                = "${var.prefix}-appi"
  resource_group_name = azurerm_resource_group.rg.name
  location            = azurerm_resource_group.rg.location
  workspace_id        = azurerm_log_analytics_workspace.law.id
  application_type    = "web"
}

# --- Container Apps --------------------------------------------------------
resource "azurerm_container_app_environment" "cae" {
  name                       = "${var.prefix}-cae"
  resource_group_name        = azurerm_resource_group.rg.name
  location                   = azurerm_resource_group.rg.location
  log_analytics_workspace_id = azurerm_log_analytics_workspace.law.id
}

locals {
  database_url = "postgresql+psycopg://${var.pg_admin_login}:${var.pg_admin_password}@${azurerm_postgresql_flexible_server.pg.fqdn}:5432/smg"
  common_env = {
    APP_ENV                       = "prod"
    AUTH_MODE                     = "entra"
    QUEUE_BACKEND                 = "azure"
    SERVICEBUS_QUEUE_NAME         = "tool-jobs"
    QUEUE_MAX_DELIVERY_COUNT      = "5"
    DATABRICKS_MODE               = "mock"
    ENTRA_TENANT_ID               = var.entra_tenant_id
    ENTRA_AUDIENCE                = var.entra_audience
    ENTRA_ISSUER                  = var.entra_issuer
    ENTRA_JWKS_URL                = var.entra_jwks_url
    OTEL_ENABLED                  = "true"
    APPLICATIONINSIGHTS_CONNECTION_STRING = azurerm_application_insights.appi.connection_string
  }
}

resource "azurerm_container_app" "gateway" {
  name                         = "${var.prefix}-gateway"
  container_app_environment_id = azurerm_container_app_environment.cae.id
  resource_group_name          = azurerm_resource_group.rg.name
  revision_mode                = "Single"

  ingress {
    external_enabled = true
    target_port      = 8000
    traffic_weight { latest_revision = true  percentage = 100 }
  }

  secret {
    name  = "database-url"
    value = local.database_url
  }
  secret {
    name  = "servicebus-connection"
    value = azurerm_servicebus_namespace.sb.default_primary_connection_string
  }

  template {
    min_replicas = 1
    max_replicas = 5
    container {
      name   = "gateway"
      image  = var.gateway_image
      cpu    = 0.5
      memory = "1Gi"
      dynamic "env" {
        for_each = local.common_env
        content {
          name  = env.key
          value = env.value
        }
      }
      env { name = "DATABASE_URL"                 secret_name = "database-url" }
      env { name = "SERVICEBUS_CONNECTION_STRING" secret_name = "servicebus-connection" }
    }
  }
}

resource "azurerm_container_app" "worker" {
  name                         = "${var.prefix}-worker"
  container_app_environment_id = azurerm_container_app_environment.cae.id
  resource_group_name          = azurerm_resource_group.rg.name
  revision_mode                = "Single"

  secret {
    name  = "database-url"
    value = local.database_url
  }
  secret {
    name  = "servicebus-connection"
    value = azurerm_servicebus_namespace.sb.default_primary_connection_string
  }

  template {
    # KEDA-style scaling on Service Bus queue length would be configured here.
    min_replicas = 1
    max_replicas = 10
    container {
      name   = "worker"
      image  = var.worker_image
      cpu    = 0.5
      memory = "1Gi"
      dynamic "env" {
        for_each = local.common_env
        content {
          name  = env.key
          value = env.value
        }
      }
      env { name = "DATABASE_URL"                 secret_name = "database-url" }
      env { name = "SERVICEBUS_CONNECTION_STRING" secret_name = "servicebus-connection" }
    }
  }
}

output "gateway_fqdn" {
  value = azurerm_container_app.gateway.ingress[0].fqdn
}
