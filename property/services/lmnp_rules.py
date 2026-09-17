"""
Dated LMNP (location meublée non professionnelle) tax rules.

Every constant carries the legal source it comes from so that a human can
cross-check the value. Values are keyed by the year of the *revenues*, not by
the year of the declaration (revenues 2025 are declared in spring 2026).

Update this module, and only this module, when a finance act changes a rule.
"""

from decimal import Decimal

# Version of the rule set embedded in frozen declarations (see LmnpDeclarationSnapshot).
RULES_VERSION = "2026"

# ── Régime réel ───────────────────────────────────────────────────────────────

# BIC non professionnel deficits can only be offset against BIC non professionnel
# profits of the following ten years (art. 156 I 1° ter CGI).
DEFICIT_CARRYFORWARD_YEARS = 10

# Amortization deferred under art. 39 C II CGI (amortissements réputés différés)
# is carried forward without time limit (BOI-BIC-AMT-20-40-10-30).
ARD_CARRYFORWARD_YEARS: int | None = None

# Social levies on rental income: CSG 10.6 % + CRDS 0.5 % + prélèvement de
# solidarité 7.5 % = 18.6 % since revenues 2025 (LFSS 2026). Informational only.
SOCIAL_LEVIES_RATE = Decimal("0.186")

# Since finance act 2025 (art. 84), amortization deducted under the régime réel is
# added back to the taxable capital gain on sales made from 15 February 2025
# (art. 150 VB II 8° CGI). Informational only: Glad does not compute capital gains.
AMORTIZATION_RECAPTURE_ON_SALE_SINCE = "2025-02-15"

# ── Micro-BIC (informational: Glad only computes the régime réel) ─────────────
#
# Thresholds are revalued every three years in line with the income tax scale
# (art. 50-0 CGI). Meublés de tourisme non classés were cut to 15 000 € / 30 %
# by the loi "Le Meur" of 19 November 2024 (revenues 2025 onwards).
# Each entry: (revenue ceiling in €, flat-rate allowance).
MICRO_BIC: dict[int, dict[str, tuple[int, Decimal]]] = {
    2025: {
        "long_term": (77_700, Decimal("0.50")),
        "classified_tourism": (77_700, Decimal("0.50")),
        "unclassified_tourism": (15_000, Decimal("0.30")),
    },
    2026: {
        "long_term": (83_600, Decimal("0.50")),
        "classified_tourism": (83_600, Decimal("0.50")),
        "unclassified_tourism": (15_000, Decimal("0.30")),
    },
}
# The flat-rate allowance can never be lower than 305 € (art. 50-0 1 CGI).
MICRO_BIC_MIN_ABATEMENT = Decimal(305)

# ── Amortization by components ───────────────────────────────────────────────
#
# Default breakdown of a dwelling into components, with the share of the total
# value and the useful life in years. Land is never depreciated. The shares and
# durations follow the administrative guidance on components (BOI 4 A-13-05 of
# 30 December 2005) and match the reference workbook used to validate Glad.
# The land share is replaced by AmortizationSetup.land_percentage; the other
# shares are rescaled proportionally to the remaining depreciable share.
DEFAULT_COMPONENTS: tuple[dict, ...] = (
    {"label": "Terrain", "pct": 15, "duration": None, "cerfa_category": "terrains"},
    {
        "label": "Gros œuvre",
        "pct": 45,
        "duration": 70,
        "cerfa_category": "constructions",
    },
    {
        "label": "Étanchéité",
        "pct": 7,
        "duration": 25,
        "cerfa_category": "constructions",
    },
    {"label": "Toiture", "pct": 8, "duration": 25, "cerfa_category": "constructions"},
    {
        "label": "Agencements intérieurs",
        "pct": 19,
        "duration": 12,
        "cerfa_category": "installations",
    },
    {
        "label": "Installations électriques",
        "pct": 6,
        "duration": 30,
        "cerfa_category": "installations",
    },
)

# Furniture and works below this amount (excl. VAT) may be expensed instead of
# being capitalised (tolerance of BOI-BIC-CHG-20-30-10 § 90).
SMALL_EQUIPMENT_THRESHOLD = Decimal(600)
