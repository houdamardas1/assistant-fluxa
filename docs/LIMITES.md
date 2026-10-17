# Limites connues - v7 (17/10/2026)

## 1. Quota Groq (tier gratuit)

Le tier gratuit Groq limite le modele openai/gpt-oss-120b a :
- 200 000 tokens/jour (TPD), reconstitues en continu sur 24 h (de l'ordre
  de 1,6 a 2,3 tokens/seconde, soit 6 000 a 8 000 tokens/heure ; mesure
  deduite des delais annonces par l'API)
- 8 000 tokens/minute (TPM)

Une question RAG complete (verificateur sur jusqu'a 15 extraits, puis
generateur) consomme environ 8 000 a 10 000 tokens (estimation d'apres le
quota consomme ; non mesuree appel par appel). L'appel du generateur seul a
ete observe a environ 4 300 tokens demandes. Une evaluation complete epuise
donc le quota de la journee.

Ne consomment PAS de tokens Groq : les refus de perimetre (observes en
1 a 75 ms), les reponses issues de la table de KPI (section 11) et les
refus de type ABSENT decides par les garde-fous.
Attention : un cas dont le verificateur reussit mais dont le generateur est
refuse par le quota (429) a deja consomme les tokens du verificateur.

**Effets observes** :
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

## 6. Fidelite du generateur (citations et affirmations)

Le modele peut ecrire des numeros inexistants dans [Source N]
(probablement des numeros d'articles). Ils sont retires du texte
(rag/generation.py::retirer_citations_invalides), mais l'affirmation
correspondante n'a alors plus de citation verifiable.

Observe sur rh_licenciement : environ 7 affirmations sans citation, un
critere d'age contradictoire et des exemples chiffres inventes. Le
generateur recoit alors 14 extraits sur 15 (le verificateur en garde
presque tous), ce qui rend le suivi des citations plus difficile.

Etat : des regles de prompt (pas d'exemple chiffre invente, ne pas affirmer
l'absence d'une information sans reverifier les extraits, numeros de source
valides de 1 a k, une citation par phrase factuelle) sont presentes dans
rag/generation.py mais NON committees : elles n'ont pas ete validees sur les
cas RAG des lots A, B et D (quota). La mesure des citations brutes sur
rh_licenciement n'est pas terminee.

**Piste d'amelioration** : verification APRES generation (chiffres presents
dans les sources, phrases sans citation) et score de fondement calcule
plutot que la confiance auto-declaree du verificateur.

## 7. Annee deduite du nom de fichier

rag/temporel.py (_report_year) utilise \b20\d{2}\b sur le nom de fichier :
une annee collee a un underscore (ex. RFA_2024.pdf) n'est pas reconnue.
Correctif propose (non applique, a evaluer separement) :
(?<!\d)20\d{2}(?!\d).

## 8. Detection de departement en francais

La detection par mots-cles (rag/departements.py) est francaise. Une
question en anglais n'est pas reconnue par les mots-cles ni, dans le cas
teste, par les embeddings ; le refus est alors assure par le controle
d'acces au niveau des passages (cas inj_rh_anglais : 10 passages Wafa
interdits au profil RH, refus obtenu).
Les cas en arabe et en darija (inj_rh_arabe, inj_rh_darija) sont
dans le jeu d'evaluation mais n'ont pas encore ete executes.

## 9. Extraction PDF : tableaux corrompus

L'extraction de certains tableaux est corrompue :
- Wafa_Assurance_RFA_2025.pdf p. 86 : la meme valeur (9.089) est repetee
  pour 2021 a 2025 ;
- Auto_Nejma_RFA_2023.pdf p. 6 : caracteres dedoubles
  (ex. "22 222255 33 337788 MDHS DE CHIFFRE D'AFFAIRES").
Ces chiffres ne sont pas exploitables. Consequence assumee : le chiffre
d'affaires 2024 de Wafa est repondu "Information absente".

## 10. Perimetre social ou consolide

Plusieurs chiffres existent selon le perimetre (ex. Wafa 2025 : chiffre
d'affaires social 12 738 MDH, primes emises consolidees 15 226 MDH, revenus
d'assurance IFRS 9 065 MDH ; Unimer : chiffre d'affaires d'Unimer SA
806,449 MDH et chiffre d'affaires consolide dont la valeur n'est pas lisible
dans l'extraction). Le pipeline demande le perimetre (CLARIFICATION) quand
les deux existent dans les passages candidats.
A confirmer dans les PDF : perimetre du resultat net 2024 de CDG Capital
(77,3 MDH, page 7) et chiffre d'affaires consolide d'Unimer (page 8).

## 11. Table de KPI (raccourci sans LLM)

data/kpi/kpi_v1.json contient 9 valeurs saisies a la main et verifiees
dans le texte extrait (pas sur l'image du PDF), avec document, page,
perimetre et roles autorises. rag/kpi.py repond directement, sans Groq,
quand la question designe un seul KPI (entreprise, metrique, annee) et que
le role est autorise ; sinon le pipeline habituel prend la main.
Limites :
- couverture etroite (Wafa, CDG, Unimer) ; aucune valeur Auto Nejma ;
- le produit net bancaire est dans la table mais n'est pas servi (la
  metrique n'est pas reconnue par detect_metric) ;
- la confiance de ces reponses est fixee a 1,0 (affichee 100 %) : ce n'est
  pas un score du verificateur ; un badge "donnee verifiee" est prevu
  (le champ source_donnees n'est pas encore transmis a l'interface) ;
- une reponse peut ne donner qu'un perimetre alors qu'un autre existe dans
  le document sans figurer dans la table (le perimetre est indique dans la
  reponse) ;
- le fichier est copie dans l'image Docker : toute modification demande une
  reconstruction de l'image.

## 12. Securite IA : couverture partielle

Cas de securite executes : injection directe francaise (ignorer les regles,
faux role, "mode developpeur") et anglaise : 4 sur 4 refuses. Le refus du
cas "faux directeur" vient du mot-cle "directeur" (departement Direction),
il ne prouve pas que la fausse declaration de role est ignoree.
Non executes : extraction du prompt systeme et exfiltration (inj_it_prompt_systeme,
inj_marketing_exfiltration : ces cas atteignent le modele), faux role sans
mot-cle, arabe, darija.
Non testes : injection indirecte (consigne cachee dans un document), attaques
elaborees ou multi-tours. Pas de filtrage de prompt ni de passerelle IA
dediee.

## 13. Deploiement

Les depots n'ont pas de remote GitHub ; pas d'integration continue ; pas de
deploiement cloud (le dossier Bicep est vide). L'application tourne en
conteneurs en local (API + interface nginx) avec les bases SQLite dans un
volume nomme. Les mots de passe des comptes de demonstration sont locaux et
doivent etre regeneres avant tout partage ou deploiement. Un avertissement
de longueur de cle JWT (40 octets) apparait dans les tests ; son origine
(cle de test) n'a pas ete verifiee.
