// Journalisation centralisée : espace Log Analytics.
// Reçoit les journaux de la plateforme de conteneurs et du Key Vault.

@description('Préfixe des noms de ressources (ex. fluxa-prod).')
param name string

param location string

@description('Durée de conservation des journaux, en jours.')
@minValue(30)
@maxValue(730)
param retentionDays int = 30

param tags object = {}

resource workspace 'Microsoft.OperationalInsights/workspaces@2023-09-01' = {
  name: '${name}-law'
  location: location
  tags: tags
  properties: {
    sku: {
      name: 'PerGB2018'
    }
    retentionInDays: retentionDays
    features: {
      enableLogAccessUsingOnlyResourcePermissions: true
    }
  }
}

output workspaceId string = workspace.id
output workspaceName string = workspace.name
