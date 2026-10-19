"""Client Groq : initialisation, appel (_chat) et QuotaError (quota epuise != information absente)."""

import os
import sys
import threading
from contextlib import contextmanager
from contextvars import ContextVar

from groq import Groq
from groq import RateLimitError

from .config import GROQ_MODEL, _dbg


class QuotaError(Exception):
    """Quota Groq epuise (429) : ce n'est PAS une 'information absente'."""


class Usage:
    """Tokens consommes pendant UNE requete (somme des appels Groq)."""

    def __init__(self):
        self.appels = 0
        self.tokens_in = 0
        self.tokens_out = 0
        self.model = GROQ_MODEL
        self._lock = threading.Lock()

    def ajouter(self, reponse) -> None:
        usage = getattr(reponse, "usage", None)
        with self._lock:
            self.appels += 1
            if usage is not None:
                self.tokens_in += int(getattr(usage, "prompt_tokens", 0) or 0)
                self.tokens_out += int(getattr(usage, "completion_tokens", 0) or 0)

    def as_audit(self) -> dict:
        """Champs d'audit ; vide si aucun appel au modele (refus, raccourci KPI)."""
        if self.appels == 0:
            return {}
        return {"model": self.model, "tokens_in": self.tokens_in,
                "tokens_out": self.tokens_out}


_USAGE: ContextVar = ContextVar("fluxa_usage", default=None)


@contextmanager
def mesurer_usage():
    """Compte les tokens des appels Groq faits dans ce bloc (meme thread)."""
    usage = Usage()
    jeton = _USAGE.set(usage)
    try:
        yield usage
    finally:
        _USAGE.reset(jeton)


def _compter(reponse):
    usage = _USAGE.get()
    if usage is not None:
        usage.ajouter(reponse)
    return reponse


def _init_groq() -> Groq:
    api_key = os.getenv("GROQ_API_KEY")

    if not api_key:
        print(
            "Erreur : GROQ_API_KEY est absente.\n"
            "Ajoute la cle dans backend/.env :\n"
            "    GROQ_API_KEY=gsk_...",
            file=sys.stderr,
        )
        sys.exit(1)

    # Nouvelles tentatives automatiques du SDK sur 429 / 5xx (avec attente).
    # Defaut 2 = valeur du SDK. Avec un plafond de 8 000 tokens par minute,
    # une question RAG (~7 000 tokens) peut buter sur la limite par minute :
    # GROQ_MAX_RETRIES=8 laisse la fenetre se vider au lieu d'echouer.
    try:
        max_retries = max(0, int(os.getenv("GROQ_MAX_RETRIES", "2")))
    except ValueError:
        max_retries = 2

    return Groq(api_key=api_key, max_retries=max_retries)


groq_client = _init_groq()


def _chat(messages: list, temperature: float, max_tokens: int):
    """Appel Groq avec comptage des tokens (voir mesurer_usage)."""
    return _compter(_chat_brut(messages, temperature, max_tokens))


def _chat_brut(messages: list, temperature: float, max_tokens: int):
    """Appel Groq. Le modele (gpt-oss) consomme des tokens de raisonnement
    sur le budget max_tokens : on limite l'effort de reflexion pour eviter
    les reponses vides ou tronquees. Si le SDK ou le modele refuse
    "reasoning_effort", on retente sans ce parametre."""
    try:
        return groq_client.chat.completions.create(
            model=GROQ_MODEL,
            messages=messages,
            temperature=temperature,
            max_tokens=max_tokens,
            reasoning_effort="low",
        )
    except RateLimitError as e:
        raise QuotaError(str(e)) from e
    except Exception as e:
        _dbg(f"reasoning_effort refuse ({e}) : nouvel essai sans ce parametre.")
        return groq_client.chat.completions.create(
            model=GROQ_MODEL,
            messages=messages,
            temperature=temperature,
            max_tokens=max_tokens,
        )
