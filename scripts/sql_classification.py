from rag.classification import CLASSIFICATION_DOCUMENTS as C

print("ALTER TABLE corpus.documents ADD COLUMN IF NOT EXISTS classification text;")
for fichier, niveau in C.items():
    print("UPDATE corpus.documents SET classification='%s' WHERE fichier_source='%s';" % (niveau, fichier))
