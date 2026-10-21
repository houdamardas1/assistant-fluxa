// Réseau privé (production) : l'environnement de conteneurs et PostgreSQL
// vivent dans un réseau virtuel ; PostgreSQL n'a aucune adresse publique.

param name string
param location string
param tags object = {}

@description('Zone DNS privée de PostgreSQL ; doit se terminer par .postgres.database.azure.com.')
param privateDnsZoneName string

resource vnet 'Microsoft.Network/virtualNetworks@2024-01-01' = {
  name: '${name}-vnet'
  location: location
  tags: tags
  properties: {
    addressSpace: {
      addressPrefixes: [
        '10.20.0.0/16'
      ]
    }
    subnets: [
      {
        name: 'snet-apps'
        properties: {
          addressPrefix: '10.20.0.0/23'
          delegations: [
            {
              name: 'container-apps'
              properties: {
                serviceName: 'Microsoft.App/environments'
              }
            }
          ]
        }
      }
      {
        name: 'snet-postgres'
        properties: {
          addressPrefix: '10.20.2.0/24'
          delegations: [
            {
              name: 'postgres'
              properties: {
                serviceName: 'Microsoft.DBforPostgreSQL/flexibleServers'
              }
            }
          ]
        }
      }
    ]
  }
}

resource dnsZone 'Microsoft.Network/privateDnsZones@2020-06-01' = {
  name: privateDnsZoneName
  location: 'global'
  tags: tags
}

resource dnsLink 'Microsoft.Network/privateDnsZones/virtualNetworkLinks@2020-06-01' = {
  parent: dnsZone
  name: '${name}-link'
  location: 'global'
  tags: tags
  properties: {
    registrationEnabled: false
    virtualNetwork: {
      id: vnet.id
    }
  }
}

output appsSubnetId string = vnet.properties.subnets[0].id
output postgresSubnetId string = vnet.properties.subnets[1].id
output privateDnsZoneId string = dnsZone.id
