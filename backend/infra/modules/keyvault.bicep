// Coffre des secrets. Les applications y lisent leurs secrets avec leur
// identité managée (rôle « Key Vault Secrets User ») : aucun secret dans les
// variables d'environnement du déploiement ni dans Git.

@description('Nom global, 3 à 24 caractères.')
param name string
param location string
param tags object = {}

@description('Identité des applications (lecture des secrets).')
param readerPrincipalId string

@description('Protection contre la purge (recommandée en production ; irréversible).')
param enablePurgeProtection bool = false

@minValue(7)
@maxValue(90)
param softDeleteDays int = 7

param workspaceId string

@secure()
param jwtSigningKey string

@secure()
param groqApiKey string

@secure()
param postgresDsn string

var secretsUserRoleId = '4633458b-17de-40e2-b2e1-c54ffa7f5f52'

resource vault 'Microsoft.KeyVault/vaults@2023-07-01' = {
  name: name
  location: location
  tags: tags
  properties: {
    tenantId: subscription().tenantId
    sku: {
      family: 'A'
      name: 'standard'
    }
    enableRbacAuthorization: true
    enableSoftDelete: true
    softDeleteRetentionInDays: softDeleteDays
    enablePurgeProtection: enablePurgeProtection ? true : null
    publicNetworkAccess: 'Enabled'
    networkAcls: {
      defaultAction: 'Allow'
      bypass: 'AzureServices'
    }
  }
}

resource secretKey 'Microsoft.KeyVault/vaults/secrets@2023-07-01' = {
  parent: vault
  name: 'secret-key'
  properties: {
    value: jwtSigningKey
    contentType: 'text/plain'
  }
}

resource groqKey 'Microsoft.KeyVault/vaults/secrets@2023-07-01' = {
  parent: vault
  name: 'groq-api-key'
  properties: {
    value: groqApiKey
    contentType: 'text/plain'
  }
}

resource pgDsn 'Microsoft.KeyVault/vaults/secrets@2023-07-01' = {
  parent: vault
  name: 'pg-dsn'
  properties: {
    value: postgresDsn
    contentType: 'text/plain'
  }
}

resource reader 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  scope: vault
  name: guid(vault.id, readerPrincipalId, secretsUserRoleId)
  properties: {
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', secretsUserRoleId)
    principalId: readerPrincipalId
    principalType: 'ServicePrincipal'
  }
}

// Journal d'audit du coffre : qui a lu ou modifié quel secret.
resource audit 'Microsoft.Insights/diagnosticSettings@2021-05-01-preview' = {
  scope: vault
  name: 'audit-vers-log-analytics'
  properties: {
    workspaceId: workspaceId
    logs: [
      {
        categoryGroup: 'audit'
        enabled: true
      }
    ]
  }
}

output vaultUri string = vault.properties.vaultUri
output vaultName string = vault.name
