// Identité managée partagée par les applications : elle lit les secrets dans
// le Key Vault et tire les images du registre. Aucun mot de passe de service.

param name string
param location string
param tags object = {}

resource identity 'Microsoft.ManagedIdentity/userAssignedIdentities@2023-01-31' = {
  name: '${name}-id'
  location: location
  tags: tags
}

output id string = identity.id
output principalId string = identity.properties.principalId
