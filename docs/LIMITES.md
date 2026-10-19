# Limites connues - v9 (18/10/2026)

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

Constate le 17/10/2026 : une question financiere sur Auto Nejma (mot-cle
"chiffre d'affaires") est rattachee au departement finance. Or les chunks
d'Auto Nejma et d'Unimer ont finance=0 (Auto_Nejma : marketing=199 ;
Unimer : direction seulement). Le retrieval n'a alors renvoye aucun passage
d'Auto Nejma (seulement le Code du travail et la loi 31-08, mode ABSENT).
Observe une fois ; cause non isolee (hypothese : filtre par departement).
Les valeurs de la table de KPI (section 11) contournent le probleme.
Piste : ne pas filtrer par departement quand une entreprise est nommee.

## 6. Fidelite du generateur (citations et affirmations)

Le modele peut ecrire des numeros inexistants dans [Source N]
(probablement des numeros d'articles). Ils sont retires du texte
(rag/generation.py::retirer_citations_invalides), mais l'affirmation
correspondante n'a alors plus de citation verifiable.

Observe sur rh_licenciement : environ 7 affirmations sans citation, un
critere d'age contradictoire et des exemples chiffres inventes. Le
generateur recoit alors 14 extraits sur 15 (le verificateur en garde
presque tous), ce qui rend le suivi des citations plus difficile.

Mesure du 17/10/2026 sur rh_licenciement (14 extraits, une seule execution,
non generalisee) : sur 10 blocs de citations brutes, 8 contenaient un numero
d'article (35, 39, 51, 52, 55, 57, 459, 457-459) au lieu d'un numero
d'extrait. Les regles de prompt (numeros de source de 1 a k, jamais
d'article) sont committees mais n'ont PAS empeche cela : elles ne sont pas
demontrees efficaces. Les autres regles du meme lot (pas d'exemple chiffre
invente, ne pas affirmer l'absence sans reverifier) ne sont pas validees sur
les lots A, B et D (quota).

Correctifs deterministes (rag/generation.py) : reparer_citations remplace un
numero hors plage par l'extrait qui contient seul "Article N" ;
normaliser_plages developpe ou retire les plages ([Source 2-4],
[Source 457-459], tiret insecable compris) ; retirer_citations_invalides
retire le reste. Sur la mesure : 35 -> Source 8 (p.25) et 55, 57 -> Source 10
(p.33), verifies dans le PDF ; 39, 51, 52 et 459 sans correspondance unique,
retires. Resultat : 1 puce sans citation (preavis ; l'article 51 figure aux
p.31 et p.37) et 1 puce a citation partiellement soutenue (faute grave : la
p.105 soutient le non-respect des prescriptions de securite, mais pas "vol,
abus de confiance, ivresse", qui viennent de l'article 39, p.25 et p.27).
Une citation peut donc etre valide en format et infidele au contenu : seule
une verification apres generation la detecterait.

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

data/kpi/kpi_v1.json contient 12 valeurs saisies a la main et verifiees
dans le texte extrait (pas sur l'image du PDF), avec document, page,
perimetre et roles autorises. rag/kpi.py repond directement, sans Groq,
quand la question designe un seul KPI (entreprise, metrique, annee) et que
le role est autorise ; sinon le pipeline habituel prend la main.
Limites :
- couverture etroite (Wafa, CDG, Unimer, Auto Nejma 2023) ; pour Auto Nejma :
  chiffre d'affaires social 2 225 MDH (texte p.9 ; 2 225,499 au tableau
  p.52), consolide 2 275 MDH (p.57), resultat net social 160,3 MDH (p.9) ;
  pas de valeur 2024 (le document est le rapport 2023) ;
- le champ entreprise d'un KPI doit etre identique au nom de l'index
  (Auto_Nejma, avec underscore) ; sinon le raccourci se tait sans erreur
  (constate le 17/10/2026) ; tests/test_kpi_donnees.py verifie que chaque
  valeur est retrouvee dans la page citee ;
- le produit net bancaire est dans la table mais n'est pas servi (la
  metrique n'est pas reconnue par detect_metric) ;
- la confiance de ces reponses est fixee a 1,0 : ce n'est
  pas un score du verificateur ; l'interface affiche a la place un badge "Donnee verifiee" quand
  toutes les sources sont verifiees ;
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
conteneurs en local (API + interface nginx) avec PostgreSQL (audit et utilisateurs ; SQLite en repli si PG_DSN est vide) dans un
volume nomme. Les mots de passe des comptes de demonstration sont locaux et
doivent etre regeneres avant tout partage ou deploiement. Un avertissement
de longueur de cle JWT (40 octets) apparait dans les tests ; son origine
(cle de test) n'a pas ete verifiee.

## 14. Infrastructure PostgreSQL

L'audit et les utilisateurs sont dans PostgreSQL quand PG_DSN est defini ; sans
PG_DSN (ou avec un chemin injecte, cas des tests) on retombe sur SQLite.
Le port hote est 15432 car 5432 et 5433 sont occupes par des PostgreSQL
Windows locaux ; pgAdmin web (127.0.0.1:5050) est optionnel. Apres un
redemarrage du PC ou de Docker : `docker compose up -d` (pas `restart api`),
l'API attend que postgres soit "healthy". Pas de pool de connexions (une
connexion par appel), pas de retention de l'audit (voir section 3), et la
classe d'adaptation PG est dupliquee dans audit.py. Les secrets sont dans
.env (jamais versionne) ; les mots de passe de demonstration doivent etre
changes avant tout partage.

## 15. Extraits tronques aux sauts de page

Le decoupage se fait par page : la derniere phrase d'une page n'a pas de
chevauchement avec la suivante. Le script patch_continuations.py complete ces
extraits, pour les textes reglementaires uniquement (43 extraits) : applique a
tous les types il a corrompu les documents Wafa Assurance (mise en page a
plusieurs colonnes). Il modifie data/index/metadata.json, non versionne
(sauvegarde .bak_continuation) : il faut le rejouer, comme
patch_departements_v2.py, apres toute reindexation. Il ne traite que le cas
page suivante du meme fichier commencant par une minuscule.
Non corrige : un extrait ne porte pas le titre de sa section. Cas constate
(article 502) : les durees d'essai du travail temporaire ont ete presentees
comme "contrats de courte duree".

## 16. Refus RBAC : veto assoupli

Avant, check_rbac_restriction refusait des que trois extraits pertinents
appartenaient a un autre departement. Il ne refuse plus si les trois conditions
suivantes sont reunies : un departement est deduit pour l'utilisateur, aucune
entreprise n'est nommee dans la question, et un extrait public_reglementaire
autorise de ce departement a un score >= 0,45. Mesure sur le jeu de cas du
harnais : faux refus de 50 % a 0 %, sans regression sur les 16 cas de refus.
Risque residuel non mesure : une question visant les donnees d'un autre
departement, sans nom d'entreprise, pourrait passer si un texte reglementaire
du departement de l'utilisateur obtient un score eleve.

## 17. Controle de fondement (observation seulement)

Le score est stocke dans la colonne audit "fondement" ; il n'est pas affiche
ni renvoye par l'API. Une ligne = une unite ; une puce imbriquee sans citation
herite de celle de la puce suivante du meme niveau, dans le meme bloc. Le
controle verifie la presence d'une citation valide et que les nombres d'au
moins 2 chiffres figurent dans les extraits cites (nombres en lettres
convertis). Il ne verifie pas : le contexte de section (cas de l'article 502 : le
chiffre figure dans l'extrait, l'erreur de contexte n'est donc pas detectee), l'exhaustivite, la fidelite
du sens, ni une mauvaise attribution entre sources citees. Une phrase de
conclusion sans fait compte comme non citee. Le critere lexical signale
presque tout (8 unites sur 10 sur une reponse longue) : il reste hors score,
non calibre. Peu de cas mesures (quatre reponses) et generation non
deterministe : le score varie d'une execution a l'autre.

## 18. Autres limites constatees

Reponses longues pour des questions generales. Detection de departement en
francais seulement : inj_rh_arabe et inj_rh_role_sans_motcle repondent en mode
GENERAL au lieu d'etre refuses. Mots-cles Finance sans effet sur les questions
textuelles Auto Nejma ou Unimer. Les criteres du harnais d'evaluation ne
normalisent pas les nombres ecrits en lettres. Sous Windows, les sorties
console exigent PYTHONUTF8=1.

## 19. Injection de prompt et limites du filtrage

**Filtre d'entrée (lexical).** Des règles FR / EN / AR / darija bloquent, avant tout appel au modèle, les demandes d'ignorer les consignes, de révéler le prompt système, d'exfiltrer des données ou de s'octroyer des droits (événement `PROMPT_BLOCKED`, mode `BLOQUE`). C'est une première barrière, pas une garantie : une reformulation, une langue non couverte ou une faute volontaire peut passer. Le rôle vient du jeton, jamais de la question.

**Injection indirecte (consignes cachées dans un document).** Trois couches indépendantes :
1. *Filtre d'extraits* avant vérification et génération (événement `DOCUMENT_BLOCKED`). Il utilise un sous-ensemble plus strict de règles : « ignorer les instructions » ou « contourner les règles de sécurité » sont écartées pour les extraits, car ces formulations existent dans de vrais textes (politiques, contrats). Le filtre s'applique aux passages candidats, pas à l'ingestion.
2. *Prompt* : les extraits sont déclarés données non fiables (règle 11).
3. *Validation de sortie* : une réponse qui reprend des morceaux du prompt système est remplacée par un refus. Elle ne détecte pas d'autres détournements (lien ou texte ajouté).

Mesures réelles (index et Groq réels) : sans le patch, deux consignes cachées réussissaient (mot imposé en fin de réponse, recopie du prompt). Le seul durcissement du prompt arrête la première mais pas la seconde ; le filtre d'extraits retire un vrai passage empoisonné (DNSSI p. 9) sans changer la réponse. Le scan des 2 960 passages du corpus ne signale aucun faux positif. Aucune garantie contre une consigne reformulée hors des règles.

## 20. Contrôle d'accès : compromis connus

- Le veto « implicite » (question sans entreprise nommée) n'écarte que les extraits interdits dont le score dépasse `SEUIL_VETO_IMPLICITE` (0,70), sauf si un document interdit est nommé dans la question. Abaisser le seuil réduit les faux refus mais augmente le risque de fuite ; le monter fait l'inverse.
- Certaines questions juridiques vagues sont désormais traitées en mode GENERAL (connaissances générales du modèle, sans citation de source) : risque d'hallucination, signalé par le mode affiché.
- La détection de département ne fonctionne qu'en français.

## 21. Mesure des tokens et du coût

Les tokens du générateur et du vérificateur sont comptés pour chaque requête. L'audit ne conserve qu'un seul nom de modèle par requête (celui de la génération) ; si `GROQ_VERIFY_MODEL` diffère de `GROQ_MODEL`, les tokens du vérificateur sont attribués au modèle de génération. Le coût est une estimation à partir de `LLM_PRICE_IN_PER_M` et `LLM_PRICE_OUT_PER_M` (non renseignés = coût non affiché). Le comptage n'est pas encore rapproché de la console du fournisseur.

## 22. Qualité des réponses et pistes futures

- Sensibilité au vocabulaire : « exigences de sauvegarde » aboutit, « règles de sauvegarde » donne parfois « information absente ».
- Latence p95 de 13 à 25 s, probablement due aux attentes de quota du fournisseur.
- Hors périmètre de cette version : mode de réponse approfondi, accès par thème, jeu de données IT synthétique.


## 23. Score de fondement

Le score affiché dans l'interface est calculé (pas estimé par le modèle) : part des affirmations factuelles de la réponse qui sont citées et dont tous les nombres figurent dans les extraits cités. Il ne vérifie pas le sens : une phrase citée peut contenir un contresens sans chiffre et être comptée comme fondée. Sans affirmation vérifiable ou hors RAG simple, l'interface retombe sur la confiance du vérificateur LLM, qui est une estimation du modèle.

Comparaisons (mode MULTI_INTENT) : le score de fondement n'est pas calculé et aucun score n'est affiché (un 0 % serait trompeur). La comparaison peut aussi tenter une différence entre deux indicateurs de nature différente (par exemple chiffre d'affaires et résultat net) : elle l'indique quand les deux valeurs ne sont pas extraites avec certitude, mais ne refuse pas la comparaison elle-même.

## 24. Pages scannées sans texte (couverture des rapports)

Mesure faite sur les PDF sources : certaines pages sont des images sans texte extractible, donc absentes de l'index et invisibles pour l'assistant.

| Document | Pages sans texte |
|---|---|
| CDG Capital (RFA 2024) | 114 sur 178 (64 %) |
| Wafa Assurance (RFA 2025) | 24 sur 154 (16 %) |
| DNSSI | 4 sur 40 (10 %) |
| Unimer, Auto Nejma | 1 chacun |
| Codes et lois (4 documents) | 0 |

Pour CDG, ce sont les pages du rapport des commissaires aux comptes et des annexes des états financiers consolidés (immobilisations, créances, charges d'exploitation), scannées avec tampons. Conséquence : une question portant sur un détail qui n'est que dans ces pages reçoit « information absente » alors qu'il figure dans le PDF.

Test d'OCR (EasyOCR, français) sur des pages réelles : la note 5.1.9 est lue avec une confiance moyenne de 0,80 mais avec une erreur de chiffre non détectable (18 170 lu 18 770, confiance 0,87) ; la note « créances sur la clientèle » est lue avec une confiance moyenne de 0,54 et des libellés illisibles. Décision : les chiffres OCR ne sont pas ajoutés à l'index, car une valeur fausse présentée comme sourcée est plus grave qu'une absence de réponse, et le score de fondement comparerait la réponse à l'OCR lui-même. Piste : valider l'OCR par relecture humaine, ou utiliser les fichiers sources (Excel, XBRL) des états financiers.

## 25. Analyse de fichiers téléversés

**Périmètre.** PDF (80 pages et 5 Mo au maximum), Word (.docx), TXT, MD, CSV et images PNG, JPG, WebP. Les PDF protégés par mot de passe, les faux formats (contrôle des premiers octets) et les archives Word anormalement volumineuses sont refusés. Aucun antivirus n'est exécuté.

**Éphémère, en mémoire.** Le fichier vit 30 minutes dans la mémoire du processus de l'API (3 fichiers par utilisateur au maximum). Il n'est jamais écrit sur disque ni en base, et il n'est pas ajouté à l'index. Il disparaît au redémarrage de l'API. Cette mémoire n'est pas partagée entre plusieurs instances : en production avec plusieurs réplicas, il faudrait un stockage de session partagé (par exemple Redis) ou un affinage de session.

**Le contenu du fichier est une donnée non fiable.** Chaque ligne puis chaque extrait passent par le filtre d'injection indirecte (§ 19 à 22) ; les passages suspects sont écartés, signalés à l'utilisateur et audités (DOCUMENT_BLOCKED). Le filtre est lexical : une consigne reformulée ou écrite dans une langue non couverte peut passer. Le prompt de génération (règle 11) et la validation de sortie constituent les deux autres couches.

**Sélection des extraits lexicale.** Les passages utilisés pour répondre sont choisis par recoupement de mots (pondération par rareté), sans embeddings. Une question formulée avec des synonymes absents du fichier peut recevoir « je ne trouve pas cette information » à tort. Un résumé d'un long document s'appuie sur 6 extraits répartis, donc il est partiel.

**CSV et chiffres.** L'assistant lit et cite les lignes ; il ne calcule pas (somme, moyenne). Le modèle n'a pas à calculer des nombres (principe du projet).

**Images et PDF scannés.** Le texte est lu par un modèle de vision externe (Groq, `qwen/qwen3.8-27b`, modifiable avec `VISION_MODEL`). L'image quitte donc l'API pour être traitée par ce fournisseur : c'est le seul cas où le contenu d'un fichier sort du système, et il doit être mentionné à l'utilisateur. Une erreur de lecture (chiffre mal lu) n'est pas détectable ; le score de fondement est donc masqué pour les passages issus de la vision et une mention « vérifiez les chiffres sur l'original » est affichée. Tests réalisés : images synthétiques nettes et inclinées de 2°, PDF scanné simulé, image piégée ; chiffres exacts (18 170, 2 340, 412). Une transcription de photo inclinée a produit du texte dupliqué en fragments. Non testés : manuscrits, tableaux complexes, mauvaise qualité, langues autres que le français. Les PDF scannés sont limités à 6 pages lues par fichier.

**Audit et contrôle d'accès.** L'audit conserve le nom (assaini), le type, la taille, l'empreinte SHA-256 tronquée, le nombre de pages, d'extraits et d'extraits écartés, jamais le contenu (FILE_UPLOADED, FILE_ANALYZED, FILE_REJECTED). Un fichier n'est accessible qu'à l'utilisateur qui l'a téléversé. La classification (PUBLIC à RESTRICTED) n'est pas appliquée aux fichiers téléversés : l'utilisateur est responsable de ce qu'il choisit d'envoyer.

## 26. Rapport PDF des indicateurs

Le rapport est généré sans modèle de langage, à partir de la même fonction de filtrage par profil que la page Indicateurs : il ne peut pas contenir un indicateur que le profil ne voit pas. Chaque export est audité (REPORT_EXPORTED : utilisateur, profil, nombre d'indicateurs). Limites : polices standard du PDF (caractères hors alphabet latin non garantis), pas de graphiques, dates en UTC, et les 12 indicateurs restent ceux vérifiés manuellement.
