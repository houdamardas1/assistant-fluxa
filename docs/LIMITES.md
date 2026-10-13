# Limites connues - v5

## 1. Quota Groq (tier gratuit)

Le tier gratuit Groq limite a :
- 200 000 tokens/jour (TPD)
- 8 000 tokens/minute (TPM)

**Effet observe** : quand le quota TPM est depasse, le verificateur LLM
echoue silencieusement (le pipeline retourne ABSENT au lieu de RAG).

**Solution appliquee** : --eval-pause 15 (ou plus) entre les cas.

**Piste d'amelioration** : Dev Tier Groq (2M tokens/jour, 100k tokens/minute)
ou GROQ_MAX_RETRIES=8.

## 2. tenant_id non applique aux donnees

Le tenant_id est present dans le JWT et journalise dans l'audit,
mais il ne filtre pas encore les documents. Deux tenants voient
aujourd'hui le meme corpus.

**Piste d'amelioration** : ajouter un champ tenant_id sur chaque
chunk de l'index, et un filtre dans rag/retrieval.py::search().

## 3. Journal d'audit sans retention

Le journal conserve les questions et des extraits de reponses sans
duree de retention ni acces restreint.

**Piste d'amelioration** : purge automatique apres X mois, chiffrement
des colonnes sensibles, acces administrateur uniquement.
