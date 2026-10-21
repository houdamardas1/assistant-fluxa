using '../main.bicep'

param environmentName = 'dev'
param namePrefix = 'fluxa'
param location = 'francecentral'

// Phase 1 : FLUXA_DEPLOY_APPS absent (ou différent de 'true') : infrastructure seule.
// Phase 2 : FLUXA_DEPLOY_APPS=true, après avoir poussé les images et téléversé l'index.
param deployApps = readEnvironmentVariable('FLUXA_DEPLOY_APPS', 'false') == 'true'

// Les secrets viennent de variables d'environnement de la session de déploiement :
// ils ne sont jamais écrits dans ce fichier ni dans Git.
param postgresAdminPassword = readEnvironmentVariable('FLUXA_PG_PASSWORD', '')
param secretKey = readEnvironmentVariable('FLUXA_SECRET_KEY', '')
param groqApiKey = readEnvironmentVariable('FLUXA_GROQ_API_KEY', '')
