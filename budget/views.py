"""Views of the yearly household budget."""

import datetime

from django.conf import settings
from django.contrib import messages
from django.db.models import ProtectedError
from django.http import HttpRequest, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils.translation import gettext as _
from django.utils.translation import ngettext
from django.views.decorators.http import require_POST

from base.csv_utils import decode_upload
from budget.forms import (
    BudgetCategoryForm,
    BudgetCopyForm,
    BudgetImportForm,
    BudgetLineForm,
    BudgetYearForm,
    PersonFilterForm,
)
from budget.models import BudgetCategory, BudgetKind, BudgetLine, BudgetYear
from budget.services.categories import category_tree, create_default_categories
from budget.services.comparison import (
    comparison_chart,
    last_12_months_inflation,
    with_previous,
)
from budget.services.copy import copy_year
from budget.services.csv_io import (
    COLUMNS,
    ai_prompt,
    export_lines,
    import_lines,
    parse_lines,
)
from budget.services.perspective import Perspective
from budget.services.sankey import sankey_payload
from budget.services.summary import DEBT_RATIO_LIMIT, build_budget

_SESSION_IMPORT_KEY = "budget_import"


def _year_or_404(year: int) -> BudgetYear:
    return get_object_or_404(BudgetYear, year=year)


# ─── Years ────────────────────────────────────────────────────────────────────


def index(request: HttpRequest) -> HttpResponse:
    """Budget years with their totals, or the first steps when there is none."""
    years = list(BudgetYear.objects.all())
    perspective = Perspective.build()
    rows = [(year, build_budget(year, perspective).indicators) for year in years]
    chronological = sorted(rows, key=lambda row: row[0].year)
    return render(
        request,
        "budget/index.html",
        {
            "rows": rows,
            # Income, expenses and savings over the years, from two years on.
            "evolution": {
                "years": [str(year.year) for year, _indicators in chronological],
                **{
                    name: [
                        round(float(getattr(indicators, name)), 2)
                        for _year, indicators in chronological
                    ]
                    for name in ("income", "expenses", "savings")
                },
            }
            if len(rows) > 1
            else None,
            "has_categories": BudgetCategory.objects.exists(),
            "currency": settings.DEFAULT_CURRENCY,
            "current_year": datetime.date.today().year,
        },
    )


def year_detail(request: HttpRequest, year: int) -> HttpResponse:
    """Budget of a year: indicators, sankey diagram and lines, for the household or a member."""
    budget_year = _year_or_404(year)
    person_form = PersonFilterForm(request.GET or None)
    person = person_form.selected()
    summary = build_budget(budget_year, Perspective.build(person))
    previous_indicators, inflation = with_previous(summary)
    sections = [
        (BudgetKind.INCOME, _("Resources"), summary.resources, summary.resources_total),
        (BudgetKind.EXPENSE, _("Expenses"), summary.expenses, summary.expenses_total),
        (
            BudgetKind.SAVING,
            BudgetKind.SAVING.label,
            summary.savings,
            summary.savings_total,
        ),
    ]
    return render(
        request,
        "budget/year_detail.html",
        {
            "budget_year": budget_year,
            "years": BudgetYear.objects.values_list("year", flat=True),
            "person_form": person_form,
            "person": person,
            "summary": summary,
            "indicators": summary.indicators,
            "previous": previous_indicators,
            "deltas": {
                "income": summary.indicators.income - previous_indicators.income,
                "expenses": summary.indicators.expenses - previous_indicators.expenses,
            }
            if previous_indicators
            else None,
            "inflation": inflation,
            "sections": sections,
            "currency": summary.currency,
            "debt_limit": DEBT_RATIO_LIMIT,
            "sankey": sankey_payload(summary),
            "comparison_chart": comparison_chart(summary)
            if summary.has_previous
            else None,
        },
    )


def _save_year_form(
    request: HttpRequest, budget_year: BudgetYear | None
) -> HttpResponse:
    if request.method == "POST":
        form = BudgetYearForm(request.POST, instance=budget_year)
        if form.is_valid():
            saved = form.save()
            messages.success(request, _("Budget saved."))
            return redirect("budget:year", year=saved.year)
        messages.error(request, _("Please correct the errors below."))
    else:
        form = BudgetYearForm(
            instance=budget_year,
            initial=None
            if budget_year
            else {"year": _next_free_year(datetime.date.today().year)},
        )
    return render(
        request,
        "budget/edit_year.html",
        {"form": form, "budget_year": budget_year},
    )


def _next_free_year(year: int) -> int:
    taken = set(BudgetYear.objects.values_list("year", flat=True))
    while year in taken:
        year += 1
    return year


def year_create(request: HttpRequest) -> HttpResponse:
    """Create the budget of a year."""
    return _save_year_form(request, None)


def year_edit(request: HttpRequest, year: int) -> HttpResponse:
    """Edit the settings of a budget."""
    return _save_year_form(request, _year_or_404(year))


@require_POST  # type: ignore
def year_delete(request: HttpRequest, year: int) -> HttpResponse:
    """Delete a budget and its lines."""
    _year_or_404(year).delete()
    messages.success(request, _("Budget deleted."))
    return redirect("budget:index")


def year_copy(request: HttpRequest, year: int) -> HttpResponse:
    """Create the budget of another year from this one, with a revaluation."""
    source = _year_or_404(year)
    if request.method == "POST":
        form = BudgetCopyForm(request.POST)
        if form.is_valid():
            target = copy_year(
                source, form.cleaned_data["year"], form.cleaned_data["revaluation"]
            )
            messages.success(
                request,
                _("Budget %(year)d created from %(source)d.")
                % {"year": target.year, "source": source.year},
            )
            return redirect("budget:year", year=target.year)
    else:
        form = BudgetCopyForm(
            initial={
                "year": _next_free_year(source.year + 1),
                "revaluation": last_12_months_inflation() or 0,
            }
        )
    return render(
        request, "budget/copy_year.html", {"form": form, "budget_year": source}
    )


# ─── Lines ────────────────────────────────────────────────────────────────────


def _save_line_form(
    request: HttpRequest, budget_year: BudgetYear, line: BudgetLine | None
) -> HttpResponse:
    if not BudgetCategory.objects.exists():
        messages.warning(request, _("Create the categories before adding lines."))
        return redirect("budget:categories")
    if request.method == "POST":
        form = BudgetLineForm(request.POST, instance=line)
        if form.is_valid():
            saved = form.save(commit=False)
            saved.budget_year = budget_year
            saved.save()
            messages.success(request, _("Line saved."))
            if "save_add" in request.POST:
                url = reverse("budget:line_new", kwargs={"year": budget_year.year})
                return redirect(f"{url}?category={saved.category_id}")
            return redirect("budget:year", year=budget_year.year)
        messages.error(request, _("Please correct the errors below."))
    else:
        initial = {}
        category = request.GET.get("category", "")
        if line is None and category.isdigit():
            initial["category"] = int(category)
        form = BudgetLineForm(instance=line, initial=initial)
    return render(
        request,
        "budget/edit_line.html",
        {"form": form, "line": line, "budget_year": budget_year},
    )


def line_create(request: HttpRequest, year: int) -> HttpResponse:
    """Add a line to a budget."""
    return _save_line_form(request, _year_or_404(year), None)


def line_edit(request: HttpRequest, pk: int) -> HttpResponse:
    """Edit a line of a budget."""
    line = get_object_or_404(BudgetLine.objects.select_related("budget_year"), pk=pk)
    return _save_line_form(request, line.budget_year, line)


@require_POST  # type: ignore
def line_delete(request: HttpRequest, pk: int) -> HttpResponse:
    """Delete a line of a budget."""
    line = get_object_or_404(BudgetLine.objects.select_related("budget_year"), pk=pk)
    year = line.budget_year.year
    line.delete()
    messages.success(request, _("Line deleted."))
    return redirect("budget:year", year=year)


# ─── Categories ───────────────────────────────────────────────────────────────


def category_list(request: HttpRequest) -> HttpResponse:
    """The category tree shared by every budget."""
    nodes = category_tree()
    groups = [
        (kind, label, [n for n in nodes if n.category.kind == kind])
        for kind, label in BudgetKind.choices
    ]
    return render(request, "budget/categories.html", {"groups": groups})


def _save_category_form(
    request: HttpRequest, category: BudgetCategory | None
) -> HttpResponse:
    if request.method == "POST":
        form = BudgetCategoryForm(request.POST, instance=category)
        if form.is_valid():
            form.save()
            messages.success(request, _("Category saved."))
            return redirect("budget:categories")
        messages.error(request, _("Please correct the errors below."))
    else:
        initial = {}
        parent = request.GET.get("parent", "")
        if category is None and parent.isdigit():
            initial["parent"] = int(parent)
        form = BudgetCategoryForm(instance=category, initial=initial)
    return render(
        request,
        "budget/edit_category.html",
        {"form": form, "category": category},
    )


def category_create(request: HttpRequest) -> HttpResponse:
    """Add a category."""
    return _save_category_form(request, None)


def category_edit(request: HttpRequest, pk: int) -> HttpResponse:
    """Edit a category."""
    return _save_category_form(request, get_object_or_404(BudgetCategory, pk=pk))


@require_POST  # type: ignore
def category_delete(request: HttpRequest, pk: int) -> HttpResponse:
    """Delete a category without lines nor sub-categories."""
    category = get_object_or_404(BudgetCategory, pk=pk)
    try:
        category.delete()
    except ProtectedError:
        messages.error(
            request,
            _(
                "This category still holds sub-categories or budget lines: "
                "move or delete them first."
            ),
        )
    else:
        messages.success(request, _("Category deleted."))
    return redirect("budget:categories")


@require_POST  # type: ignore
def category_defaults(request: HttpRequest) -> HttpResponse:
    """Create the default categories."""
    created = create_default_categories()
    messages.success(
        request,
        ngettext(
            "%(count)d category created.", "%(count)d categories created.", created
        )
        % {"count": created},
    )
    if request.POST.get("next") == "index":
        return redirect("budget:index")
    return redirect("budget:categories")


# ─── CSV and AI prompt ────────────────────────────────────────────────────────


def csv_export(request: HttpRequest, year: int) -> HttpResponse:
    """Download the lines of a budget as CSV."""
    budget_year = _year_or_404(year)
    response = HttpResponse(
        "﻿" + export_lines(budget_year), content_type="text/csv; charset=utf-8"
    )
    response["Content-Disposition"] = (
        f'attachment; filename="budget-{budget_year.year}.csv"'
    )
    return response


def csv_import(request: HttpRequest, year: int) -> HttpResponse:
    """Upload a CSV file of lines and preview them before the import."""
    budget_year = _year_or_404(year)
    if request.method == "POST":
        form = BudgetImportForm(request.POST, request.FILES)
        if form.is_valid():
            text = decode_upload(form.cleaned_data["csv_file"].read())
            create_missing = form.cleaned_data["create_missing"]
            preview = parse_lines(text, create_missing=create_missing)
            if preview.errors:
                for error in preview.errors:
                    messages.error(request, error)
            else:
                request.session[_SESSION_IMPORT_KEY] = {
                    "year": budget_year.year,
                    "text": text,
                    "create_missing": create_missing,
                }
                return render(
                    request,
                    "budget/import_preview.html",
                    {"budget_year": budget_year, "preview": preview},
                )
    else:
        form = BudgetImportForm()
    return render(
        request,
        "budget/import.html",
        {"form": form, "budget_year": budget_year, "columns": COLUMNS},
    )


@require_POST  # type: ignore
def csv_import_confirm(request: HttpRequest, year: int) -> HttpResponse:
    """Import the valid lines of the previewed file."""
    budget_year = _year_or_404(year)
    data = request.session.pop(_SESSION_IMPORT_KEY, None)
    if not data or data.get("year") != budget_year.year:
        messages.error(
            request, _("The import session expired, please upload the file again.")
        )
        return redirect("budget:import", year=budget_year.year)
    preview = parse_lines(data["text"], create_missing=data["create_missing"])
    count = import_lines(budget_year, preview, settings.DEFAULT_CURRENCY)
    messages.success(
        request,
        ngettext("%(count)d line imported.", "%(count)d lines imported.", count)
        % {"count": count},
    )
    skipped = len(preview.invalid_rows)
    if skipped:
        messages.warning(
            request,
            ngettext(
                "%(count)d line with errors was skipped.",
                "%(count)d lines with errors were skipped.",
                skipped,
            )
            % {"count": skipped},
        )
    return redirect("budget:year", year=budget_year.year)


def prompt(request: HttpRequest, year: int) -> HttpResponse:
    """Prompt asking an AI to turn a bank export into an importable file."""
    budget_year = _year_or_404(year)
    return render(
        request,
        "budget/ai_prompt.html",
        {"budget_year": budget_year, "prompt": ai_prompt(budget_year)},
    )
