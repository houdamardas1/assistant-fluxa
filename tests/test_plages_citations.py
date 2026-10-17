from rag.generation import normaliser_plages, retirer_citations_invalides


def test_plage_hors_limites_retiree():
    t = "Texte [Source 4, Source 457\u2011459]."
    assert normaliser_plages(t, 14) == "Texte [Source 4]."


def test_plage_valide_developpee():
    assert normaliser_plages("A [Source 2-4].", 14) == "A [Source 2, Source 3, Source 4]."
    assert normaliser_plages("A [Source 2\u20114].", 14) == "A [Source 2, Source 3, Source 4]."


def test_plage_seule_hors_limites_supprime_le_bloc():
    assert normaliser_plages("Texte [Source 20-22].", 14) == "Texte."


def test_blocs_sans_plage_inchanges():
    for t in ("Texte [Source 5].", "Texte [Source 5, Source 35].", "Voir [note 3-4]."):
        assert normaliser_plages(t, 14) == t


def test_chaine_complete_ne_laisse_rien_d_invalide():
    t = normaliser_plages("X [Source 4, Source 457\u2011459]. Y [Source 52].", 14)
    assert retirer_citations_invalides(t, 14) == "X [Source 4]. Y."
