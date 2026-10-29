"""Tests for the shared PDF base."""

from base.services.pdf import BasePdf, money


def test_money():
    assert money(None) == ""
    assert money("") == ""
    assert money("1234.5") == "1 234,50 €"


def test_base_pdf_renders_the_helpers():
    pdf = BasePdf()
    pdf.add_page()
    pdf.heading("Quittance de loyer")
    pdf.subheading("Période")
    pdf.paragraph("Je soussigné, propriétaire du logement désigné ci-dessous…")
    pdf.note("Note")
    pdf.simple_table(
        ["Libellé", "Montant"],
        [["Loyer", money(750)], ["Total", money(830)]],
        [120, 50],
        bold_rows={1},
    )
    content = pdf.render()
    assert content.startswith(b"%PDF")
