// Les deux applications : API (FastAPI) et interface (nginx).
// Les noms de variables d'environnement sont ceux de docker-compose.yml et
// de .env.example ; les secrets sont des références Key Vault (identité managée).

param name string
param location string
param tags object = {}

param environmentId string
param environmentDomain string
param identityId string
param registryServer string
param vaultUri string
param mountName string

@description('Valeur de ENVIRONMENT pour l\'API.')
param appEnvironment string

param apiImage string
param webImage string

@description('Processeurs de l\'API (format décimal, ex. 2.0). Mémoire = 2 Gio par processeur.')
param apiCpu string
param apiMemory string
param apiMinReplicas int
param apiMaxReplicas int
param webMinReplicas int = 1

param groqModel string = 'openai/gpt-oss-120b'
param groqVerifyModel string = 'openai/gpt-oss-120b'
param priceInPerMillion string = '0.15'
param priceOutPerMillion string = '0.60'

var apiName = '${name}-api'
var webName = '${name}-web'

// L'adresse d'une application est prévisible : <nom>.<domaine de l'environnement>.
var apiUrl = 'https://${apiName}.${environmentDomain}'
var webUrl = 'https://${webName}.${environmentDomain}'

resource api 'Microsoft.App/containerApps@2024-03-01' = {
  name: apiName
  location: location
  tags: tags
  identity: {
    type: 'UserAssigned'
    userAssignedIdentities: {
      '${identityId}': {}
    }
  }
  properties: {
    managedEnvironmentId: environmentId
    workloadProfileName: 'Consumption'
    configuration: {
      activeRevisionsMode: 'Single'
      ingress: {
        external: true
        targetPort: 8000
        transport: 'auto'
        allowInsecure: false
        // Les fichiers téléversés et les limiteurs de débit sont en mémoire,
        // par réplique : on garde un même utilisateur sur la même réplique.
        stickySessions: {
          affinity: 'sticky'
        }
      }
      registries: [
        {
          server: registryServer
          identity: identityId
        }
      ]
      secrets: [
        {
          name: 'secret-key'
          keyVaultUrl: '${vaultUri}secrets/secret-key'
          identity: identityId
        }
        {
          name: 'groq-api-key'
          keyVaultUrl: '${vaultUri}secrets/groq-api-key'
          identity: identityId
        }
        {
          name: 'pg-dsn'
          keyVaultUrl: '${vaultUri}secrets/pg-dsn'
          identity: identityId
        }
      ]
    }
    template: {
      containers: [
        {
          name: 'api'
          image: apiImage
          resources: {
            cpu: json(apiCpu)
            memory: apiMemory
          }
          env: [
            { name: 'ENVIRONMENT', value: appEnvironment }
            { name: 'DEBUG', value: 'False' }
            { name: 'ALGORITHM', value: 'HS256' }
            { name: 'SECRET_KEY', secretRef: 'secret-key' }
            { name: 'GROQ_API_KEY', secretRef: 'groq-api-key' }
            { name: 'PG_DSN', secretRef: 'pg-dsn' }
            { name: 'CORS_ORIGINS', value: webUrl }
            { name: 'PUBLIC_API_URL', value: apiUrl }
            { name: 'GROQ_MODEL', value: groqModel }
            { name: 'GROQ_VERIFY_MODEL', value: groqVerifyModel }
            { name: 'GROQ_MAX_RETRIES', value: '2' }
            { name: 'LLM_PRICE_IN_PER_M', value: priceInPerMillion }
            { name: 'LLM_PRICE_OUT_PER_M', value: priceOutPerMillion }
          ]
          volumeMounts: [
            {
              volumeName: 'index'
              mountPath: '/app/data/index'
            }
          ]
          // Le chargement de torch, de FAISS et du modèle d'embeddings dure
          // environ une minute : la sonde de démarrage laisse près de 4 minutes.
          probes: [
            {
              type: 'Startup'
              httpGet: {
                path: '/health'
                port: 8000
              }
              initialDelaySeconds: 60
              periodSeconds: 15
              failureThreshold: 10
              timeoutSeconds: 5
            }
            {
              type: 'Liveness'
              httpGet: {
                path: '/health'
                port: 8000
              }
              periodSeconds: 30
              failureThreshold: 3
              timeoutSeconds: 5
            }
            {
              type: 'Readiness'
              httpGet: {
                path: '/health'
                port: 8000
              }
              periodSeconds: 10
              failureThreshold: 3
              timeoutSeconds: 5
            }
          ]
        }
      ]
      volumes: [
        {
          name: 'index'
          storageType: 'AzureFile'
          storageName: mountName
          // Utilisateur non root du conteneur (uid 1000) ; fichiers en lecture seule.
          mountOptions: 'uid=1000,gid=1000,file_mode=0444,dir_mode=0555,nobrl'
        }
      ]
      scale: {
        minReplicas: apiMinReplicas
        maxReplicas: apiMaxReplicas
        rules: [
          {
            name: 'charge-http'
            http: {
              metadata: {
                concurrentRequests: '20'
              }
            }
          }
        ]
      }
    }
  }
}

resource web 'Microsoft.App/containerApps@2024-03-01' = {
  name: webName
  location: location
  tags: tags
  identity: {
    type: 'UserAssigned'
    userAssignedIdentities: {
      '${identityId}': {}
    }
  }
  properties: {
    managedEnvironmentId: environmentId
    workloadProfileName: 'Consumption'
    configuration: {
      activeRevisionsMode: 'Single'
      ingress: {
        external: true
        targetPort: 8080
        transport: 'auto'
        allowInsecure: false
      }
      registries: [
        {
          server: registryServer
          identity: identityId
        }
      ]
    }
    template: {
      containers: [
        {
          name: 'web'
          image: webImage
          resources: {
            cpu: json('0.25')
            memory: '0.5Gi'
          }
          probes: [
            {
              type: 'Liveness'
              httpGet: {
                path: '/'
                port: 8080
              }
              periodSeconds: 30
              failureThreshold: 3
            }
          ]
        }
      ]
      scale: {
        minReplicas: webMinReplicas
        maxReplicas: 3
        rules: [
          {
            name: 'charge-http'
            http: {
              metadata: {
                concurrentRequests: '100'
              }
            }
          }
        ]
      }
    }
  }
}

output apiUrl string = apiUrl
output webUrl string = webUrl
output apiName string = api.name
output webName string = web.name
