// Nervora — Secure MCP Gateway · Azure reference deployment (Bicep).
// Equivalent to infra/terraform/main.tf. Reference only; harden networking,
// secrets (Key Vault) and identity (managed identity) before production use.

@description('Resource name prefix')
param prefix string = 'smcpgw'

@description('Deployment location')
param location string = resourceGroup().location

@description('PostgreSQL admin login')
param pgAdminLogin string = 'smgadmin'

@secure()
@description('PostgreSQL admin password')
param pgAdminPassword string

@description('Gateway container image (fully qualified)')
param gatewayImage string

@description('Worker container image (fully qualified)')
param workerImage string

param entraTenantId string
param entraAudience string = 'api://secure-mcp-gateway'
param entraIssuer string
param entraJwksUrl string

// --- PostgreSQL ------------------------------------------------------------
resource pg 'Microsoft.DBforPostgreSQL/flexibleServers@2023-06-01-preview' = {
  name: '${prefix}-pg'
  location: location
  sku: { name: 'Standard_B1ms', tier: 'Burstable' }
  properties: {
    version: '16'
    administratorLogin: pgAdminLogin
    administratorLoginPassword: pgAdminPassword
    storage: { storageSizeGB: 32 }
    network: { publicNetworkAccess: 'Disabled' }
  }
}

resource pgDb 'Microsoft.DBforPostgreSQL/flexibleServers/databases@2023-06-01-preview' = {
  parent: pg
  name: 'smg'
}

// --- Service Bus -----------------------------------------------------------
resource sb 'Microsoft.ServiceBus/namespaces@2022-10-01-preview' = {
  name: '${prefix}-sb'
  location: location
  sku: { name: 'Standard', tier: 'Standard' }
}

resource jobsQueue 'Microsoft.ServiceBus/namespaces/queues@2022-10-01-preview' = {
  parent: sb
  name: 'tool-jobs'
  properties: {
    maxDeliveryCount: 5
    lockDuration: 'PT30S'
    defaultMessageTimeToLive: 'P1D'
    deadLetteringOnMessageExpiration: true
  }
}

// --- Observability ---------------------------------------------------------
resource law 'Microsoft.OperationalInsights/workspaces@2022-10-01' = {
  name: '${prefix}-law'
  location: location
  properties: { sku: { name: 'PerGB2018' }, retentionInDays: 30 }
}

resource appi 'Microsoft.Insights/components@2020-02-02' = {
  name: '${prefix}-appi'
  location: location
  kind: 'web'
  properties: { Application_Type: 'web', WorkspaceResourceId: law.id }
}

// --- Container Apps --------------------------------------------------------
resource cae 'Microsoft.App/managedEnvironments@2024-03-01' = {
  name: '${prefix}-cae'
  location: location
  properties: {
    appLogsConfiguration: {
      destination: 'log-analytics'
      logAnalyticsConfiguration: {
        customerId: law.properties.customerId
        sharedKey: law.listKeys().primarySharedKey
      }
    }
  }
}

var databaseUrl = 'postgresql+psycopg://${pgAdminLogin}:${pgAdminPassword}@${pg.properties.fullyQualifiedDomainName}:5432/smg'
var sbConnection = listKeys('${sb.id}/AuthorizationRules/RootManageSharedAccessKey', sb.apiVersion).primaryConnectionString

var commonEnv = [
  { name: 'APP_ENV', value: 'prod' }
  { name: 'AUTH_MODE', value: 'entra' }
  { name: 'QUEUE_BACKEND', value: 'azure' }
  { name: 'SERVICEBUS_QUEUE_NAME', value: 'tool-jobs' }
  { name: 'QUEUE_MAX_DELIVERY_COUNT', value: '5' }
  { name: 'DATABRICKS_MODE', value: 'mock' }
  { name: 'ENTRA_TENANT_ID', value: entraTenantId }
  { name: 'ENTRA_AUDIENCE', value: entraAudience }
  { name: 'ENTRA_ISSUER', value: entraIssuer }
  { name: 'ENTRA_JWKS_URL', value: entraJwksUrl }
  { name: 'OTEL_ENABLED', value: 'true' }
  { name: 'APPLICATIONINSIGHTS_CONNECTION_STRING', value: appi.properties.ConnectionString }
  { name: 'DATABASE_URL', secretRef: 'database-url' }
  { name: 'SERVICEBUS_CONNECTION_STRING', secretRef: 'servicebus-connection' }
]

resource gateway 'Microsoft.App/containerApps@2024-03-01' = {
  name: '${prefix}-gateway'
  location: location
  properties: {
    managedEnvironmentId: cae.id
    configuration: {
      ingress: { external: true, targetPort: 8000 }
      secrets: [
        { name: 'database-url', value: databaseUrl }
        { name: 'servicebus-connection', value: sbConnection }
      ]
    }
    template: {
      containers: [ { name: 'gateway', image: gatewayImage, resources: { cpu: json('0.5'), memory: '1Gi' }, env: commonEnv } ]
      scale: { minReplicas: 1, maxReplicas: 5 }
    }
  }
}

resource worker 'Microsoft.App/containerApps@2024-03-01' = {
  name: '${prefix}-worker'
  location: location
  properties: {
    managedEnvironmentId: cae.id
    configuration: {
      secrets: [
        { name: 'database-url', value: databaseUrl }
        { name: 'servicebus-connection', value: sbConnection }
      ]
    }
    template: {
      containers: [ { name: 'worker', image: workerImage, resources: { cpu: json('0.5'), memory: '1Gi' }, env: commonEnv } ]
      // KEDA scale rule on Service Bus queue length would be added here.
      scale: { minReplicas: 1, maxReplicas: 10 }
    }
  }
}

output gatewayFqdn string = gateway.properties.configuration.ingress.fqdn
