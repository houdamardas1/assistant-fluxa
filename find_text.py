import json

with open("data/index/metadata.json", "r", encoding="utf-8") as f:
    metadata = json.load(f)

terms = [
    "résultat net",
    "resultat net",
    "résultat consolidé",
    "resultat consolidé"
]

for term in terms:
    print("\n" + "=" * 70)
    print(f"RECHERCHE : {term}")
    print("=" * 70)

    count = 0

    for i, chunk in enumerate(metadata):
        content = chunk.get("content", "")

        if term.lower() in content.lower():
            count += 1

            print(f"\nChunk : {i}")
            print(f"Entreprise : {chunk.get('entreprise')}")
            print(f"Page : {chunk.get('page')}")
            print(f"Fichier : {chunk.get('fichier_source')}")
            print(f"Roles : {chunk.get('allowed_roles')}")
            print("-" * 50)
            print(content[:1500])

    print(f"\nTOTAL : {count}")