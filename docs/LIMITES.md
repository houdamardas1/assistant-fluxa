# Limites connues - v6

## 1. Quota Groq (tier gratuit)

Le tier gratuit Groq limite le modele openai/gpt-oss-120b a :
- 200 000 tokens/jour (TPD), reconstitues en continu sur 24 h (environ
  2,3 tokens/seconde ; estimation deduite des delais annonces par l'API)
- 8 000 tokens/minute (TPM)

Une question RAG complete (verificateur + generateur) consomme environ
4 000 a 5 000 tokens. Une serie de tests ou une evaluation complete peut
donc epuiser le quota de la journee.

**Effets observes (16/10/2026)** :
- le depassement du quota journalier est signale par une erreur 429
  (QuotaError) ; en evaluation, les cas concernes sont comptes en erreur ;
- un depassement du TPM provoque de nouvelles tentatives (jusqu'a
  GROQ_MAX_RETRIES=8) et des latences de 30 a 67 s.

**Mesures appliquees** : --eval-pause 30 entre les cas, evaluation par
lots, aucun test lance juste avant une demonstration.

**Piste d'amelioration** : plan payant Groq (limites a verifier sur la
console Groq).

## 2. tenant_id non applique aux donnees

Le tenant_id est present dans le JWT et journalise dans l'audit,
mais il ne filtre pas encore les documents. Deux tenants voient
aujourd'hui le meme corpus.

**Piste d'amelioration** : ajouter un champ tenant_id sur chaque
chunk de l'index, et un filtre dans rag/retrieval.py::search().

## 3. Journal d'audit sans retention

Le journal conserve les questions et des extraits de reponses sans
duree de retention ni acces restreint. Il contient aussi les requetes
de test.

**Piste d'amelioration** : purge automatique apres X mois, chiffrement
des colonnes sensibles, acces administrateur uniquement.

## 4. Verificateur LLM intermittent

Le verificateur (rag/verification.py::verify_relevance) est un appel LLM.
Quand la reponse est repartie sur plusieurs passages, il peut repondre
can_answer=false a tort. Exemple : rh_conges_annuels (la regle de duree
est a l'article 231, rang 11 sur 15 des extraits fournis) : 4 echecs sur
15 essais le 16/10/2026, regroupes dans le temps, puis 6 reussites sur 6
le 17/10/2026. La cause exacte n'est pas etablie.

Essais : une seconde verification sur refus n'a pas ameliore le resultat
(non retenue) ; une regle de prompt supplementaire n'a pas pu etre validee
(quota).

**Contournement** : reposer la question.
**Piste d'amelioration** : ameliorer le classement des passages plutot que
le verificateur.

## 5. Departements dependants de l'indexation

Le champ departements des chunks d'entreprise est ajoute par
patch_departements_v2.py (957 chunks) et n'est pas produit par
l'ingestion. Apres toute reindexation, relancer :
    python patch_departements_v2.py --apply
Sinon, les documents Wafa, Unimer et CDG sont ecartes pour les questions
de type finance posees par la direction.

Par ailleurs, les departements it, rh, commerce et juridique ne
contiennent que des textes reglementaires (aucun document interne reel).

## 6. Citations inventees par le modele

Le modele peut ecrire des numeros inexistants dans [Source N]
(probablement des numeros d'articles). Ils sont retires du texte
(rag/generation.py::retirer_citations_invalides), mais l'affirmation
correspondante n'a alors plus de citation verifiable.

## 7. Annee deduite du nom de fichier

rag/temporel.py (_report_year) utilise \b20\d{2}\b sur le nom de fichier :
une annee collee a un underscore (ex. RFA_2024.pdf) n'est pas reconnue.
Correctif propose (non applique, a evaluer separement) :
(?<!\d)20\d{2}(?!\d).