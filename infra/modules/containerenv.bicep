// Environnement d'exécution des conteneurs (Azure Container Apps, profil
// « Consommation ») : journaux vers Log Analytics, réseau privé en production,
// et montage du partage Azure Files qui contient l'index FAISS.

param name string
param location string
param tags object = {}

param workspaceName string

@description('Sous-réseau délégué ; vide = réseau géré par Azure.')
param infrastructureSubnetId string = ''

param storageAccountName string
param shareName string

@description('Nom du montage, référencé par les applications.')
param mountName string = 'faiss-index'

resource workspace 'Microsoft.OperationalInsights/workspaces@2023-09-01' existing = {
  name: workspaceName
}

resource account 'Microsoft.Storage/storageAccounts@2023-05-01' existing = {
  name: storageAccountName
}

resource environment 'Microsoft.App/managedEnvironments@2024-03-01' = {
  name: '${name}-env'
  location: location
  tags: tags
  properties: {
    appLogsConfiguration: {
      destination: 'log-analytics'
      logAnalyticsConfiguration: {
        customerId: workspace.properties.customerId
        sharedKey: workspace.listKeys().primarySharedKey
      }
    }
    vnetConfiguration: empty(infrastructureSubnetId) ? null : {
      infrastructureSubnetId: infrastructureSubnetId
      internal: false
    }
    workloadProfiles: [
      {
        name: 'Consumption'
        workloadProfileType: 'Consumption'
      }
    ]
    zoneRedundant: false
  }
}

resource indexMount 'Microsoft.App/managedEnvironments/storages@2024-03-01' = {
  parent: environment
  name: mountName
  properties: {
    azureFile: {
      accountName: account.name
      accountKey: account.listKeys().keys[0].value
      shareName: shareName
      accessMode: 'ReadOnly'
    }
  }
}

output id string = environment.id
output defaultDomain string = environment.properties.defaultDomain
output mountName string = indexMount.name
