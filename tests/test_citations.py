from rag.generation import retirer_citations_invalides as f


def test_supprime_numeros_hors_liste():
    assert f("Faute grave [Source 293, Source 39].", 15) == "Faute grave."


def test_garde_les_valides_dans_un_bloc_mixte():
    assert f("A [Source 2, Source 99] b", 15) == "A [Source 2] b"


def test_bloc_valide_inchange():
    s = "A [Source 1, Source 2] et [Sources 3 et 4]."
    assert f(s, 15) == s


def test_format_long_inchange():
    s = "A [Source 1 - doc.pdf, page 125]."
    assert f(s, 15) == s


def test_sans_citation():
    assert f("rien", 3) == "rien"
