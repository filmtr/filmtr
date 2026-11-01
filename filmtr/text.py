"""Normalization of titles and names for matching across sources."""

import re
import unicodedata

ARTICLES = (
    "the a an le la les l il lo gli i el los las der die das den det ein eine "
    "un une una uno o os"
).split()
_TRAILING_ARTICLE = re.compile(r",\s*(" + "|".join(ARTICLES) + r")'?$")
_LEADING_ARTICLE = re.compile(r"^(" + "|".join(ARTICLES) + r")\s+")


def fold(s: str) -> str:
    """Lowercase and strip diacritics: 'Règle' -> 'regle'."""
    s = unicodedata.normalize("NFKD", s)
    s = "".join(c for c in s if not unicodedata.combining(c))
    return s.lower().replace("ø", "o").replace("æ", "ae").replace("ß", "ss")


def norm_title(s: str) -> str:
    """Comparable form of a title: 'Rules of the Game, The' -> 'rules of game'."""
    s = fold(s).replace("&", " and ").replace("½", " 1/2")
    s = _TRAILING_ARTICLE.sub("", s.strip())
    s = re.sub(r"l'|d'", " ", s)
    s = re.sub(r"[^\w/]+", " ", s).strip()
    s = _LEADING_ARTICLE.sub("", s)
    words = [w for w in s.split() if w not in ARTICLES or len(s.split()) == 1]
    return " ".join(words)


def name_tokens(s: str) -> set[str]:
    """Tokens of a personal name, order-insensitive: 'Hitchcock, Alfred' -> {alfred, hitchcock}."""
    return {t for t in re.split(r"[^\w]+", fold(s)) if len(t) > 1}


_DISAMBIGUATION = re.compile(
    r"\s*\((?:[^()]*\b)?(?:фильм|мультфильм|сериал|мини-сериал|телефильм|телесериал|"
    r"киноальманах|документальный фильм)\b[^()]*\)$", re.I)
_PATRONYMIC = re.compile(r"^\w+(?:вич|вна|ична|инична|оглы|кызы)$")


def clean_ru_title(s: str) -> str:
    """Drop Wikipedia-style disambiguation: 'Война и мир (фильм, 1967)' -> 'Война и мир'."""
    return _DISAMBIGUATION.sub("", s).strip()


def clean_ru_name(s: str) -> str:
    """Bring Russian labels to 'Имя Фамилия'.

    'Серый, Александр Иванович' -> 'Александр Серый',
    'Сергей Фёдорович Бондарчук' -> 'Сергей Бондарчук'.
    """
    s = re.sub(r"\s*\([^()]*\)$", "", s).strip()
    if s.count(",") == 1 and not re.search(r"\d", s):  # not peerage titles like '18-й барон
        last, _, first = s.partition(",")
        s = f"{first.strip()} {last.strip()}"
    words = s.split()
    if len(words) == 3 and _PATRONYMIC.match(words[1]):
        words.pop(1)
    return " ".join(words)
