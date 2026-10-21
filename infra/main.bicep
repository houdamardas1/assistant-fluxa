// Fluxa Intelligence : infrastructure Azure (un groupe de ressources par environnement).
//
// Déploiement en deux phases (voir docs/ARCHITECTURE_AZURE.md) :
//   1. deployApps = false : réseau, registre, coffre, PostgreSQL, stockage, environnement ;
//   2. images poussées + index téléversé, puis deployApps = true : les deux applications.
//
// Ce modèle est validé par compilation (bicep build) ; il n'a pas été déployé.

targetScope = 'resourceGroup'

@description('dev, staging ou prod : choisit le dimensionnement (voir la variable profils).')
@allowed([
  'dev'
  'staging'
  'prod'
])
param environmentName string

@description('Région. France Centre : Union européenne, proche du Maroc, offre de services complète.')
param location string = resourceGroup().location

@description('Préfixe des noms.')
@minLength(3)
@maxLength(8)
param namePrefix string = 'fluxa'

@description('Phase 2 : créer les applications (les images doivent exister dans le registre).')
param deployApps bool = false

param apiImage string = 'fluxa-api:latest'
param webImage string = 'fluxa-web:latest'

param postgresAdminLogin string = 'fluxaadmin'
param databaseName string = 'fluxa'

@secure()
@minLength(16)
param postgresAdminPassword string

@description('Clé de signature des jetons (au moins 32 caractères).')
@secure()
@minLength(32)
param secretKey string

@secure()
@minLength(20)
param groqApiKey string

var profils = {
  dev: {
    appEnvironment: 'development'
    pgSku: 'Standard_B1ms'
    pgTier: 'Burstable'
    pgStorageGb: 32
    pgBackupDays: 7
    pgHa: 'Disabled'
    acrSku: 'Basic'
    storageSku: 'Standard_LRS'
    privateNetwork: false
    purgeProtection: false
    softDeleteDays: 7
    logDays: 30
    apiCpu: '1.0'
    apiMemory: '2Gi'
    apiMin: 0
    apiMax: 1
    webMin: 0
  }
  staging: {
    appEnvironment: 'staging'
    pgSku: 'Standard_B2s'
    pgTier: 'Burstable'
    pgStorageGb: 32
    pgBackupDays: 7
    pgHa: 'Disabled'
    acrSku: 'Basic'
    storageSku: 'Standard_LRS'
    privateNetwork: false
    purgeProtection: false
    softDeleteDays: 30
    logDays: 30
    apiCpu: '2.0'
    apiMemory: '4Gi'
    apiMin: 1
    apiMax: 2
    webMin: 1
  }
  prod: {
    appEnvironment: 'production'
    pgSku: 'Standard_D2ds_v5'
    pgTier: 'GeneralPurpose'
    pgStorageGb: 64
    pgBackupDays: 35
    pgHa: 'ZoneRedundant'
    acrSku: 'Standard'
    storageSku: 'Standard_ZRS'
    privateNetwork: true
    purgeProtection: true
    softDeleteDays: 90
    logDays: 90
    apiCpu: '2.0'
    apiMemory: '4Gi'
    apiMin: 1
    apiMax: 3
    webMin: 1
  }
}

var profil = profils[environmentName]
var base = '${namePrefix}-${environmentName}'
var unique = take(uniqueString(resourceGroup().id), 6)
var tags = {
  application: 'fluxa-intelligence'
  environnement: environmentName
}

module monitoring 'modules/monitoring.bicep' = {
  name: 'monitoring'
  params: {
    name: base
    location: location
    tags: tags
    retentionDays: profil.logDays
  }
}

module identity 'modules/identity.bicep' = {
  name: 'identity'
  params: {
    name: base
    location: location
    tags: tags
  }
}

module network 'modules/network.bicep' = if (profil.privateNetwork) {
  name: 'network'
  params: {
    name: base
    location: location
    tags: tags
    privateDnsZoneName: '${base}.private.postgres.database.azure.com'
  }
}

module registry 'modules/registry.bicep' = {
  name: 'registry'
  params: {
    name: toLower('${namePrefix}${environmentName}${unique}')
    location: location
    tags: tags
    sku: profil.acrSku
    pullPrincipalId: identity.outputs.principalId
  }
}

module postgres 'modules/postgres.bicep' = {
  name: 'postgres'
  params: {
    name: '${base}-${unique}-pg'
    location: location
    tags: tags
    skuName: profil.pgSku
    skuTier: profil.pgTier
    storageGb: profil.pgStorageGb
    backupDays: profil.pgBackupDays
    highAvailability: profil.pgHa
    databaseName: databaseName
    adminLogin: postgresAdminLogin
    adminPassword: postgresAdminPassword
    delegatedSubnetId: network.?outputs.postgresSubnetId ?? ''
    privateDnsZoneId: network.?outputs.privateDnsZoneId ?? ''
  }
}

module vault 'modules/keyvault.bicep' = {
  name: 'vault'
  params: {
    name: '${base}-${unique}-kv'
    location: location
    tags: tags
    readerPrincipalId: identity.outputs.principalId
    enablePurgeProtection: profil.purgeProtection
    softDeleteDays: profil.softDeleteDays
    workspaceId: monitoring.outputs.workspaceId
    jwtSigningKey: secretKey
    groqApiKey: groqApiKey
    postgresDsn: 'postgresql://${postgresAdminLogin}:${uriComponent(postgresAdminPassword)}@${postgres.outputs.fqdn}:5432/${databaseName}?sslmode=require'
  }
}

module storage 'modules/storage.bicep' = {
  name: 'storage'
  params: {
    name: toLower('${namePrefix}${environmentName}${take(uniqueString(resourceGroup().id), 8)}')
    location: location
    tags: tags
    skuName: profil.storageSku
  }
}

module containerEnv 'modules/containerenv.bicep' = {
  name: 'container-env'
  params: {
    name: base
    location: location
    tags: tags
    workspaceName: monitoring.outputs.workspaceName
    infrastructureSubnetId: network.?outputs.appsSubnetId ?? ''
    storageAccountName: storage.outputs.accountName
    shareName: storage.outputs.shareName
  }
}

module apps 'modules/apps.bicep' = if (deployApps) {
  name: 'apps'
  params: {
    name: base
    location: location
    tags: tags
    environmentId: containerEnv.outputs.id
    environmentDomain: containerEnv.outputs.defaultDomain
    identityId: identity.outputs.id
    registryServer: registry.outputs.loginServer
    vaultUri: vault.outputs.vaultUri
    mountName: containerEnv.outputs.mountName
    appEnvironment: profil.appEnvironment
    apiImage: '${registry.outputs.loginServer}/${apiImage}'
    webImage: '${registry.outputs.loginServer}/${webImage}'
    apiCpu: profil.apiCpu
    apiMemory: profil.apiMemory
    apiMinReplicas: profil.apiMin
    apiMaxReplicas: profil.apiMax
    webMinReplicas: profil.webMin
  }
}

output registryLoginServer string = registry.outputs.loginServer
output registryName string = registry.outputs.name
output keyVaultName string = vault.outputs.vaultName
output storageAccountName string = storage.outputs.accountName
output indexShareName string = storage.outputs.shareName
output postgresServerName string = postgres.outputs.serverName
output postgresFqdn string = postgres.outputs.fqdn
output environmentDomain string = containerEnv.outputs.defaultDomain
output apiUrl string = apps.?outputs.apiUrl ?? ''
output webUrl string = apps.?outputs.webUrl ?? ''
