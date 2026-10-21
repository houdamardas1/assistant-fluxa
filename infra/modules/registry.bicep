// Registre privé des images (api, web). Pas de compte administrateur :
// l'accès se fait par identité managée (rôle AcrPull).

@description('Nom global, lettres et chiffres uniquement.')
param name string
param location string
param tags object = {}

@allowed([
  'Basic'
  'Standard'
  'Premium'
])
param sku string = 'Basic'

@description('Identité autorisée à tirer les images.')
param pullPrincipalId string

var acrPullRoleId = '7f951dda-4ed3-4680-a7ca-43fe172d538d'

resource registry 'Microsoft.ContainerRegistry/registries@2023-07-01' = {
  name: name
  location: location
  tags: tags
  sku: {
    name: sku
  }
  properties: {
    // Pas de compte administrateur ; l'accès anonyme est désactivé par défaut.
    adminUserEnabled: false
    publicNetworkAccess: 'Enabled'
  }
}

resource pull 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  scope: registry
  name: guid(registry.id, pullPrincipalId, acrPullRoleId)
  properties: {
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', acrPullRoleId)
    principalId: pullPrincipalId
    principalType: 'ServicePrincipal'
  }
}

output loginServer string = registry.properties.loginServer
output name string = registry.name
