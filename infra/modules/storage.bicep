// Partage de fichiers pour l'index FAISS (lecture seule côté API).
// L'index est un artefact de build : on le téléverse après chaque réindexation.

@description('Nom global, 3 à 24 caractères, minuscules et chiffres.')
param name string
param location string
param tags object = {}

@allowed([
  'Standard_LRS'
  'Standard_ZRS'
])
param skuName string = 'Standard_LRS'

param shareName string = 'faiss-index'

resource account 'Microsoft.Storage/storageAccounts@2023-05-01' = {
  name: name
  location: location
  tags: tags
  kind: 'StorageV2'
  sku: {
    name: skuName
  }
  properties: {
    minimumTlsVersion: 'TLS1_2'
    supportsHttpsTrafficOnly: true
    allowBlobPublicAccess: false
    // Le montage Azure Files d'un environnement de conteneurs exige la clé du compte.
    allowSharedKeyAccess: true
    defaultToOAuthAuthentication: true
  }
}

resource files 'Microsoft.Storage/storageAccounts/fileServices@2023-05-01' = {
  parent: account
  name: 'default'
}

resource share 'Microsoft.Storage/storageAccounts/fileServices/shares@2023-05-01' = {
  parent: files
  name: shareName
  properties: {
    shareQuota: 5
    enabledProtocols: 'SMB'
  }
}

output accountName string = account.name
output shareName string = share.name
