"""Render a frozen LMNP liasse (see ``lmnp_snapshot``) as a PDF with fpdf2.

One A4 page per cerfa form. The renderer only reads the frozen payload, so a
live PDF and the PDF of a stored snapshot are produced by the same code.
"""

from decimal import Decimal
from pathlib import Path
from typing import Any

from fpdf import FPDF
from fpdf.enums import TableBordersLayout
from fpdf.fonts import FontFace

FONT_DIR = Path(__file__).parent / "fonts"
FONT = "DejaVu"

# Cerfa line labels shared by every rendering of the 2033-B.
LINES_2033B = (
    ("218", "Production vendue – services (loyers, charges refacturées)", "recettes"),
    ("242", "Autres charges externes", "autres_charges_externes"),
    ("244", "Impôts, taxes et versements assimilés", "impots_taxes"),
    ("243", "  dont CFE", "cfe"),
    ("254", "Dotations aux amortissements", "amortization_total"),
    ("270", "Résultat d'exploitation", "resultat_exploitation_270"),
    ("294", "Charges financières (intérêts d'emprunt)", "charges_financieres"),
    ("310", "Bénéfice ou perte (résultat comptable)", "cerfa_310"),
    ("318", "Réintégration : amortissements non déductibles (art. 39 C)", "cerfa_318"),
    ("350", "Déduction : amortissements différés antérieurs imputés", "cerfa_350"),
    ("352", "Résultat fiscal avant imputation des déficits antérieurs", "cerfa_352"),
    ("360", "Déficits antérieurs imputés", "cerfa_360"),
    ("370", "Résultat fiscal après imputation des déficits antérieurs", "cerfa_370"),
)
TOTAL_LINES = {"270", "310", "352", "370"}


def money(value: Any) -> str:
    """Format a frozen amount as ``1 234,56 €`` (empty for None)."""
    if value is None or value == "":
        return ""
    amount = Decimal(str(value)).quantize(Decimal("0.01"))
    text = f"{amount:,.2f}".replace(",", " ").replace(".", ",")
    return f"{text} €"


class LmnpPdf(FPDF):
    """A4 portrait document with a header naming the year and the properties."""

    def __init__(self, payload: dict) -> None:
        super().__init__(orientation="P", unit="mm", format="A4")
        self.payload = payload
        self.add_font(FONT, "", FONT_DIR / "DejaVuSans.ttf")
        self.add_font(FONT, "B", FONT_DIR / "DejaVuSans-Bold.ttf")
        self.set_auto_page_break(auto=True, margin=18)
        self.alias_nb_pages()

    def header(self) -> None:
        year = self.payload["fiscal_year"]
        names = ", ".join(p["name"] for p in self.payload["properties"])
        self.set_font(FONT, "B", 11)
        self.cell(
            0, 6, f"Liasse LMNP réel — exercice {year}", new_x="LMARGIN", new_y="NEXT"
        )
        self.set_font(FONT, "", 8)
        self.set_text_color(90)
        generated = self.payload["generated_at"][:16].replace("T", " ")
        self.cell(
            0,
            5,
            f"Biens : {names} · généré le {generated} · règles {self.payload['rules_version']}",
            new_x="LMARGIN",
            new_y="NEXT",
        )
        self.set_text_color(0)
        self.ln(3)

    def footer(self) -> None:
        self.set_y(-14)
        self.set_font(FONT, "", 7)
        self.set_text_color(120)
        self.cell(
            0,
            5,
            "Document généré par Glad – aide à la déclaration, ne remplace pas la liasse "
            f"officielle ni l'avis d'un expert-comptable · page {self.page_no()}/{{nb}}",
            align="C",
        )
        self.set_text_color(0)

    # ── helpers ──────────────────────────────────────────────────────────────

    def heading(self, text: str) -> None:
        self.set_font(FONT, "B", 13)
        self.cell(0, 9, text, new_x="LMARGIN", new_y="NEXT")
        self.ln(1)

    def subheading(self, text: str) -> None:
        self.set_font(FONT, "B", 10)
        self.cell(0, 7, text, new_x="LMARGIN", new_y="NEXT")

    def note(self, text: str) -> None:
        self.set_font(FONT, "", 8)
        self.set_text_color(70)
        self.multi_cell(0, 4.2, text, new_x="LMARGIN", new_y="NEXT")
        self.set_text_color(0)
        self.ln(2)

    def simple_table(
        self,
        headings: list[str],
        rows: list[list[Any]],
        col_widths: list[float],
        bold_rows: set[int] | None = None,
        text_columns: int = 1,
    ) -> None:
        """Draw a table: the first ``text_columns`` are left-aligned, the others right-aligned."""
        self.set_font(FONT, "", 8.5)
        bold = FontFace(emphasis="BOLD", fill_color=(235, 238, 243))
        align = ["LEFT"] * text_columns + ["RIGHT"] * (len(headings) - text_columns)
        with self.table(
            col_widths=col_widths,
            text_align=align,
            borders_layout=TableBordersLayout.MINIMAL,
            headings_style=FontFace(
                emphasis="BOLD", fill_color=(52, 104, 152), color=255
            ),
            line_height=5.5,
            padding=1,
        ) as table:
            head = table.row()
            for heading in headings:
                head.cell(heading)
            for index, values in enumerate(rows):
                style = bold if bold_rows and index in bold_rows else None
                row = table.row(style=style)
                for value in values:
                    row.cell("" if value is None else str(value))
        self.ln(4)


# ── pages ───────────────────────────────────────────────────────────────────


def _page_summary(pdf: LmnpPdf) -> None:
    acc = pdf.payload["accounting"]
    b, c = acc["form_2033b"], acc["form_2042c"]
    pdf.add_page()
    pdf.heading("Synthèse")
    pdf.note(
        "Régime réel simplifié, location meublée non professionnelle. Les montants sont "
        "calculés pour l'ensemble de l'activité (une seule liasse par contribuable)."
    )
    pdf.simple_table(
        ["Élément", "Montant"],
        [
            ["Recettes (2033-B 218)", money(b["recettes"])],
            [
                "Dotation aux amortissements (2033-B 254)",
                money(b["amortization_total"]),
            ],
            ["Résultat comptable (2033-B 310)", money(b["cerfa_310"])],
            ["Plafond d'amortissement déductible (art. 39 C)", money(b["plafond_39c"])],
            [
                "Amortissements différés en fin d'exercice (SUIV39C)",
                money(b["deferred_balance"]),
            ],
            [
                "Résultat fiscal avant déficits antérieurs (2033-B 352)",
                money(b["cerfa_352"]),
            ],
            [
                "Résultat fiscal après déficits antérieurs (2033-B 370)",
                money(b["cerfa_370"]),
            ],
            ["2042-C PRO 5NA — revenus imposables", money(c["case_5na"])],
            ["2042-C PRO 5NY — déficit de l'année", money(c["case_5ny"])],
            ["2042-C PRO 5CD — durée de l'exercice (mois)", str(c["case_5cd"])],
            [
                "Déficits antérieurs encore reportables",
                money(c["deficit_carryforward"]),
            ],
        ],
        [130, 50],
        bold_rows={5, 6, 7, 8},
    )
    checklist = pdf.payload.get("checklist") or {}
    if checklist.get("properties"):
        pdf.subheading("Vérification des données")
        rows = []
        for prop_data in checklist["properties"]:
            for check in prop_data["checks"]:
                rows.append(
                    [
                        prop_data["property"]["name"],
                        check["label"],
                        check["status"],
                        check["form_ref"],
                    ]
                )
        pdf.set_font(FONT, "", 8)
        with pdf.table(
            col_widths=[35, 85, 25, 35],
            text_align=["LEFT", "LEFT", "CENTER", "LEFT"],
            borders_layout=TableBordersLayout.MINIMAL,
            headings_style=FontFace(emphasis="BOLD", fill_color=(235, 238, 243)),
            line_height=5,
            padding=1,
        ) as table:
            head = table.row()
            for heading in ("Bien", "Vérification", "Statut", "Formulaire"):
                head.cell(heading)
            for values in rows:
                row = table.row()
                for value in values:
                    row.cell(str(value))


def _page_2033a(pdf: LmnpPdf) -> None:
    a = pdf.payload["accounting"]["form_2033a"]
    pdf.add_page()
    pdf.heading("2033-A — Bilan simplifié")
    pdf.subheading("Actif")
    pdf.simple_table(
        ["", "Brut", "Amortissements", "Net"],
        [
            [
                "Immobilisations corporelles (028 / 030)",
                money(a["immobilisations_brutes"]),
                money(a["amortissements_cumules"]),
                money(a["valeur_nette_comptable"]),
            ],
            [
                "Total actif immobilisé",
                money(a["immobilisations_brutes"]),
                money(a["amortissements_cumules"]),
                money(a["valeur_nette_comptable"]),
            ],
        ],
        [85, 32, 32, 32],
        bold_rows={1},
    )
    pdf.subheading("Passif")
    pdf.simple_table(
        ["", "Montant"],
        [
            ["Capital social ou individuel (120)", money(a["capital_individuel"])],
            ["Résultat de l'exercice (136)", money(a["resultat_exercice"])],
            ["Total capitaux propres (142)", money(a["total_capitaux_propres"])],
            ["Emprunts et dettes assimilées (156)", money(a["emprunts"])],
            ["Total passif", money(a["valeur_nette_comptable"])],
            [
                "Coût de revient des immobilisations acquises dans l'exercice (182)",
                money(a["cout_revient_acquisitions"]),
            ],
        ],
        [130, 50],
        bold_rows={2, 4},
    )


def _page_2033b(pdf: LmnpPdf) -> None:
    b = pdf.payload["accounting"]["form_2033b"]
    per_prop = b.get("per_prop") or []
    pdf.add_page()
    pdf.heading("2033-B — Compte de résultat simplifié")
    pdf.note(
        "Plafond art. 39 C = produits − charges afférentes au bien (hors frais de "
        f"comptabilité) − impôts − intérêts = {money(b['plafond_39c'])}. Dotation "
        f"{money(b['amortization_total'])}, déduite {money(b['amortization_deductible'])}, "
        f"différée {money(b['cerfa_318'])} (ligne 318). Déficits antérieurs disponibles "
        f"{money(b['deficits_anterieurs'])}."
    )
    has_cfe = Decimal(str(b.get("cfe") or 0)) != 0
    rows = [
        [line, label, money(b[key])]
        for line, label, key in LINES_2033B
        if line != "243" or has_cfe
    ]
    bold_rows = {i for i, row in enumerate(rows) if row[0] in TOTAL_LINES}
    pdf.simple_table(
        ["Ligne", "Libellé", "Montant"], rows, [16, 124, 40], bold_rows, text_columns=2
    )
    if len(per_prop) > 1:
        pdf.subheading("Détail par bien (partie A)")
        pdf.simple_table(
            ["Bien", "Recettes", "242", "244", "254", "294", "310"],
            [
                [
                    item["property"]["name"],
                    money(item["summary"]["recettes"]),
                    money(item["summary"]["by_line"].get("242", 0)),
                    money(item["summary"]["by_line"].get("244", 0)),
                    money(item["summary"]["amortization_total"]),
                    money(item["summary"]["charges_financieres"]),
                    money(item["summary"]["cerfa_310"]),
                ]
                for item in per_prop
            ],
            [40, 25, 23, 23, 23, 23, 23],
        )


def _page_2033c(pdf: LmnpPdf) -> None:
    c = pdf.payload["accounting"]["form_2033c"]
    labels = {
        "terrains": "Terrains",
        "constructions": "Constructions",
        "installations": "Installations générales, agencements",
        "autres": "Autres immobilisations corporelles",
    }
    pdf.add_page()
    pdf.heading("2033-C — Immobilisations et amortissements")
    pdf.subheading("I — Immobilisations")
    rows = [
        [
            label,
            money(c["by_cerfa_category"][cat]["value_start"]),
            money(c["by_cerfa_category"][cat]["acquisitions"]),
            money(c["by_cerfa_category"][cat]["diminutions"]),
            money(c["by_cerfa_category"][cat]["value_end"]),
        ]
        for cat, label in labels.items()
    ]
    rows.append(
        [
            "Total",
            money(c["totals"]["value_start"]),
            money(c["totals"]["acquisitions"]),
            money(c["totals"]["diminutions"]),
            money(c["totals"]["value_end"]),
        ]
    )
    pdf.simple_table(
        ["Nature", "Début", "Augmentations", "Diminutions", "Fin"],
        rows,
        [60, 30, 30, 30, 30],
        bold_rows={len(rows) - 1},
    )
    pdf.subheading("II — Amortissements")
    rows = [
        [
            label,
            money(c["by_cerfa_category"][cat]["amort_start"]),
            money(c["by_cerfa_category"][cat]["dotation"]),
            money(c["by_cerfa_category"][cat]["diminutions"]),
            money(c["by_cerfa_category"][cat]["amort_end"]),
        ]
        for cat, label in labels.items()
    ]
    rows.append(
        [
            "Total (572 dotations / 576 fin)",
            money(c["totals"]["amort_start"]),
            money(c["totals"]["dotation"]),
            money(c["totals"]["diminutions"]),
            money(c["totals"]["amort_end"]),
        ]
    )
    pdf.simple_table(
        ["Nature", "Début", "Dotations", "Diminutions", "Fin"],
        rows,
        [60, 30, 30, 30, 30],
        bold_rows={len(rows) - 1},
    )


def _page_suiv39c(pdf: LmnpPdf) -> None:
    acc = pdf.payload["accounting"]
    pdf.add_page()
    pdf.heading("SUIV39C — Amortissements différés (art. 39 C) et déficits reportables")
    pdf.note(
        "L'amortissement n'est déductible qu'à hauteur des loyers diminués des autres charges "
        "afférentes au bien ; la fraction non déduite est reportée sans limite de durée. "
        "Un déficit LMNP est imputable sur les bénéfices LMNP des dix années suivantes "
        "(art. 156 I 1° ter CGI)."
    )
    pdf.subheading("Suivi des amortissements différés")
    rows = [
        [
            str(r["year"]),
            money(r["deferred_start"]),
            money(r["dotation"]),
            money(r["deducted"]),
            money(r["reintegrated_318"]),
            money(r["used_350"]),
            money(r["deferred_end"]),
        ]
        for r in acc["form_suiv39c"]["rows"]
    ]
    pdf.simple_table(
        [
            "Exercice",
            "Stock début",
            "Dotation",
            "Déduite",
            "Différée (318)",
            "Imputée (350)",
            "Stock fin",
        ],
        rows or [["—", "", "", "", "", "", ""]],
        [20, 27, 27, 27, 27, 27, 25],
    )
    pdf.subheading("Déficits reportables par année d'origine")
    history = acc["form_2042c"]["deficit_history"] or {}
    rows = [
        [str(origin), str(int(origin) + 10), money(amount)]
        for origin, amount in sorted(history.items())
    ]
    rows.append(["Total", "", money(acc["form_2042c"]["deficit_carryforward"])])
    pdf.simple_table(
        ["Année d'origine", "Imputable jusqu'en", "Déficit restant"],
        rows,
        [60, 60, 60],
        bold_rows={len(rows) - 1},
    )


def _page_2042c(pdf: LmnpPdf) -> None:
    c = pdf.payload["accounting"]["form_2042c"]
    f = pdf.payload["accounting"]["form_2031"]
    pdf.add_page()
    pdf.heading("2031 / 2042-C PRO — Cases à reporter")
    pdf.subheading("2031 — Récapitulation des éléments d'imposition")
    pdf.simple_table(
        ["", "Montant"],
        [
            [
                "Résultat fiscal avant imputation des déficits antérieurs (2033-B 352)",
                money(f["resultat_fiscal_352"]),
            ],
            [
                "Bénéfice imposable ou déficit déductible (2033-B 370)",
                money(f["resultat_fiscal_370"]),
            ],
        ],
        [130, 50],
        bold_rows={1},
    )
    pdf.subheading("2042-C PRO — Locations meublées non professionnelles, régime réel")
    rows = [
        ["5CD", "Durée de l'exercice en mois", str(c["case_5cd"])],
        ["5NA", "Revenus imposables — cas général", money(c["case_5na"])],
        ["5NY", "Déficit de l'année — cas général", money(c["case_5ny"])],
    ]
    rows += [
        [
            entry["label"],
            f"Déficit non encore déduit — année {entry['origin_year']}",
            money(entry["amount"]),
        ]
        for entry in c["deficit_cases_list"]
    ]
    pdf.simple_table(
        ["Case", "Libellé", "Montant"],
        rows,
        [20, 120, 40],
        bold_rows={1, 2},
        text_columns=2,
    )


def _page_amortization(pdf: LmnpPdf) -> None:
    tables = pdf.payload.get("amortization") or {}
    names = {str(p["id"]): p["name"] for p in pdf.payload["properties"]}
    pdf.add_page()
    pdf.heading("Tableau des amortissements par bien")
    for prop_id, rows in tables.items():
        pdf.subheading(names.get(str(prop_id), str(prop_id)))
        table_rows = [
            [
                row["label"],
                (row.get("beginning_date") or "")[:10],
                money(row["value_total"]),
                str(row["duration_years"]) if row.get("duration_years") else "—",
                money(row["annual_dotation"]),
                money(row["cumulative"]),
            ]
            for row in rows
        ]
        total_dotation = (
            sum(Decimal(str(r["annual_dotation"])) for r in rows)
            if rows
            else Decimal(0)
        )
        total_value = (
            sum(Decimal(str(r["value_total"])) for r in rows) if rows else Decimal(0)
        )
        total_cumul = (
            sum(Decimal(str(r["cumulative"])) for r in rows) if rows else Decimal(0)
        )
        table_rows.append(
            [
                "Total",
                "",
                money(total_value),
                "",
                money(total_dotation),
                money(total_cumul),
            ]
        )
        pdf.simple_table(
            ["Composant", "Début", "Valeur", "Durée", "Dotation N", "Cumul fin N"],
            table_rows,
            [55, 25, 30, 15, 27, 28],
            bold_rows={len(table_rows) - 1},
            text_columns=2,
        )


def render_lmnp_pdf(payload: dict) -> bytes:
    """Render the frozen liasse payload (see ``build_snapshot_payload``) as PDF bytes."""
    pdf = LmnpPdf(payload)
    for page in (
        _page_summary,
        _page_2033a,
        _page_2033b,
        _page_2033c,
        _page_suiv39c,
        _page_2042c,
        _page_amortization,
    ):
        page(pdf)
    return bytes(pdf.output())
