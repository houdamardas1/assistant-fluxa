"""Acces PostgreSQL (psycopg 3), partage par les modules qui le supportent.

psycopg est facultatif : sans lui (ou sans URL), les services restent sur SQLite.
"""

from contextlib import contextmanager

try:
    import psycopg
    from psycopg.rows import dict_row
except ImportError:
    psycopg = None
    dict_row = None


class CxPg:
    """Adapte une connexion psycopg a l'API utilisee ailleurs : placeholders '?'
    et lignes accessibles par nom."""

    def __init__(self, raw):
        self._raw = raw

    def execute(self, sql, params=()):
        return self._raw.execute(sql.replace("?", "%s"), params or None)


@contextmanager
def connexion_pg(url):
    """Connexion qui valide (commit) puis se ferme a la sortie."""
    raw = psycopg.connect(url, row_factory=dict_row, connect_timeout=5)
    try:
        yield CxPg(raw)
        raw.commit()
    except Exception:
        raw.rollback()
        raise
    finally:
        raw.close()
