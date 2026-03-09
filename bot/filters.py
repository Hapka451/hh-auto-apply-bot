from config import (
    IGNORED_EMPLOYERS,
    ALLOWED_TITLE_KEYWORDS,
    BLOCKED_TITLE_KEYWORDS,
)


def _normalize(text):
    return (text or "").strip().lower()


def employer_is_ignored(employer):
    employer = _normalize(employer)

    for ignored in IGNORED_EMPLOYERS:
        if _normalize(ignored) in employer:
            return True

    return False


def title_has_blocked_keyword(title):
    title = _normalize(title)

    for keyword in BLOCKED_TITLE_KEYWORDS:
        if _normalize(keyword) in title:
            return True

    return False


def title_has_allowed_keyword(title):
    title = _normalize(title)

    for keyword in ALLOWED_TITLE_KEYWORDS:
        if _normalize(keyword) in title:
            return True

    return False


def vacancy_passes_filters(vacancy):
    if employer_is_ignored(vacancy.employer):
        return False, "ignored employer"

    if title_has_blocked_keyword(vacancy.title):
        return False, "blocked title keyword"

    if not title_has_allowed_keyword(vacancy.title):
        return False, "no allowed title keyword"

    return True, "ok"