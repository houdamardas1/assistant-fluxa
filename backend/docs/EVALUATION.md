# Évaluation du RAG : résultats

Jeu de référence : `data/eval/v1.json`, 55 cas, exécuté le 2026-10-21 sur le vrai pipeline et le vrai modèle (Groq), index réel de 2 960 passages.
Rapport : `eval_v4-fusion_20261021_121539.json` (fusion de : eval_final_20261021_113851.json, eval_inj-filtre_20261021_115752.json). Rapport complet : oui.

## Indicateurs globaux

| Indicateur | Résultat |
|---|---|
| Taux de réussite global | 100.0 % |
| Mode de traitement attendu obtenu | 100.0 % |
| Source attendue retrouvée par la recherche | 100.0 % |
| Source attendue présente dans le contexte final | 100.0 % |
| Valeur attendue présente dans la réponse | 100.0 % |
| Réponses sourcées avec citation | 100.0 % |
| Accès croisés refusés (RBAC) | 100.0 % |
| Injections neutralisées avant le modèle | 100.0 % |
| Refus corrects (accès + injections) | 100.0 % |
| Faux refus (plus bas = mieux) | 0.0 % |

## Résultats par famille de questions

| Famille | Cas réussis |
|---|---|
| Questions factuelles sur les rapports d'entreprise | 20 / 20 |
| Textes réglementaires et sécurité SI | 13 / 13 |
| Accès croisés (RBAC) | 8 / 8 |
| Questions générales et robustesse | 3 / 3 |
| Injections de prompt | 9 / 9 |
| Faux refus (questions vagues) | 2 / 2 |

## Latence

| Mesure | Valeur |
|---|---|
| Moyenne sur tous les cas | 13.7 s |
| Réponses nécessitant le modèle (> 3 s) : médiane / p95 | 40.1 s / 65.2 s (n = 19) |
| Cas rapides (refus, blocages, chiffres clés, questions hors sujet) | < 3 s |

## Cas non réussis

Aucun.

## Limites de la mesure

- Le jeu compte 55 cas : il détecte les régressions mais ne prouve pas la qualité sur des questions inédites.
- Les cas ont été ajoutés au fil des défauts découverts et le système a été réglé sur ce jeu : le taux de 100 % mesure l'absence de régression, pas une performance sur des questions inédites.
- Le modèle n'est pas déterministe : un même cas peut réussir une fois et échouer la suivante (observé sur `unimer_conseil_admin`, vérification du contenu, 1 exécution sur 2).
- L'évaluation passe par la même barrière d'entrée que l'API ; une question légitime bloquée à tort ferait échouer son cas.
- Le palier gratuit du fournisseur limite le modèle à 200 000 tokens par jour : une exécution complète en consomme une grande partie.
- Les départements IT, RH, commerce et juridique n'ont que des textes réglementaires (pas de documents internes réels).
- Les résultats portent sur le corpus de démonstration (4 rapports d'entreprise, 5 textes réglementaires).

## Configuration de l'exécution

- groq_model : openai/gpt-oss-120b
- groq_verify_model : openai/gpt-oss-120b
- verify_chars : 1200
- embedding_model : paraphrase-multilingual-MiniLM-L12-v2
- top_k_retrieval : 30
- top_k_verify : 15
- top_k_context : 10
- poids_faiss : 0.5
- poids_lexical : 0.5
- seuil_detection_departement : 2
- seuil_embedding_departement : 0.45
- marge_embedding_departement : 0.05
