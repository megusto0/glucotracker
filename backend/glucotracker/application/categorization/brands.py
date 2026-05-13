"""Brand-slug dictionaries for provenance classification.

Maintained manually as new brand_slugs appear in the product database.
The CLI command `glucotracker admin list-unclassified-brands` surfaces
unrecognized slugs for review before adding them here.
"""

KNOWN_RESTAURANT_BRANDS: frozenset[str] = frozenset(
    {
        "bk",
        "mc",
        "kfc",
        "rostics",
        "rostic",
        "popeyes",
        "vkusno_i_tochka",
    }
)

KNOWN_PACKAGED_BRANDS: frozenset[str] = frozenset(
    {
        "shagi",
        "royal_cake",
        "protein_rex",
        "cheetos",
        "bus_bros",
    }
)
