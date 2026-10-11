"""Client Groq : initialisation, appel (_chat) et QuotaError (quota epuise != information absente)."""

import os
import sys
from groq import Groq
from groq import RateLimitError

from .config import GROQ_MODEL, _dbg


class QuotaError(Exception):
    """Quota Groq epuise (429) : ce n'est PAS une 'information absente'."""


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

    return Groq(api_key=api_key)


groq_client = _init_groq()


def _chat(messages: list, temperature: float, max_tokens: int):
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
