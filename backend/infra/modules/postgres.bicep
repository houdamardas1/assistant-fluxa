// PostgreSQL 16 managé : journal d'audit, utilisateurs, corpus (schéma corpus).
// Sauvegardes automatiques ; haute disponibilité inter-zones en production.
// En production la base n'a aucune adresse publique (réseau privé délégué).

@description('Nom global du serveur.')
param name string
param location string
param tags object = {}

param skuName string
@allowed([
  'Burstable'
  'GeneralPurpose'
  'MemoryOptimized'
])
param skuTier string
param storageGb int
@minValue(7)
@maxValue(35)
param backupDays int
@allowed([
  'Disabled'
  'ZoneRedundant'
])
param highAvailability string = 'Disabled'

param databaseName string
param adminLogin string

@secure()
param adminPassword string

@description('Sous-réseau délégué ; vide = accès public restreint aux services Azure.')
param delegatedSubnetId string = ''

@description('Zone DNS privée ; obligatoire si le sous-réseau est renseigné.')
param privateDnsZoneId string = ''

var privateAccess = !empty(delegatedSubnetId)

resource server 'Microsoft.DBforPostgreSQL/flexibleServers@2024-08-01' = {
  name: name
  location: location
  tags: tags
  sku: {
    name: skuName
    tier: skuTier
  }
  properties: {
    version: '16'
    administratorLogin: adminLogin
    administratorLoginPassword: adminPassword
    storage: {
      storageSizeGB: storageGb
      autoGrow: 'Enabled'
    }
    backup: {
      backupRetentionDays: backupDays
      geoRedundantBackup: 'Disabled'
    }
    highAvailability: {
      mode: highAvailability
    }
    authConfig: {
      passwordAuth: 'Enabled'
      activeDirectoryAuth: 'Disabled'
    }
    network: privateAccess ? {
      delegatedSubnetResourceId: delegatedSubnetId
      privateDnsZoneArmResourceId: privateDnsZoneId
      publicNetworkAccess: 'Disabled'
    } : {
      publicNetworkAccess: 'Enabled'
    }
  }
}

resource database 'Microsoft.DBforPostgreSQL/flexibleServers/databases@2024-08-01' = {
  parent: server
  name: databaseName
  properties: {
    charset: 'UTF8'
    collation: 'en_US.utf8'
  }
}

// Sans réseau privé : seuls les services Azure (dont les conteneurs) passent.
resource azureServices 'Microsoft.DBforPostgreSQL/flexibleServers/firewallRules@2024-08-01' = if (!privateAccess) {
  parent: server
  name: 'AllowAzureServices'
  properties: {
    startIpAddress: '0.0.0.0'
    endIpAddress: '0.0.0.0'
  }
}

output fqdn string = server.properties.fullyQualifiedDomainName
output serverName string = server.name
