"""Name-pattern dictionaries for fast-food provenance detection.

Conservative list — misses are OK. Over-match is a bug.
Patterns are matched case-insensitively against meal/item names.
"""

FASTFOOD_NAME_PATTERNS: frozenset[str] = frozenset(
    {
        "чизбург",
        "чизбургер",
        "наггет",
        "наггетс",
        "воппер",
        "биг хи",
        "биг ма",
        "биг тей",
        "роллы",
        "стрипс",
        "баскет",
        "картофель фри",
        "фри",
        "донер б",
        "доши",
        "субм",
        "хрустящий бург",
    }
)
