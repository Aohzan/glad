"""API views for the finance app — JSON endpoints for the dashboard."""

from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.urls import reverse
from django.utils.decorators import method_decorator
from django.views import View

from finance.models.investment_account import InvestmentAccount
from finance.models.saving_account import SavingAccount


@method_decorator(login_required, name="dispatch")
class AccountsSummaryApiView(View):
    """Return accounts breakdown, progress bars, and alerts for the dashboard."""

    def get(self, request):
        days = 30
        saving_accounts = SavingAccount.objects.filter(is_active=True).order_by(
            "-is_favorite", "name"
        )
        investment_accounts = InvestmentAccount.objects.filter(is_active=True).order_by(
            "-is_favorite", "name"
        )

        # Breakdown (donut chart)
        total_savings = sum((float(a.get_value().amount) for a in saving_accounts), 0.0)
        total_investments = sum(
            (float(a.current_value.amount) for a in investment_accounts), 0.0
        )
        breakdown_labels = ["Investments", "Savings"]
        breakdown_values = [total_investments, total_savings]

        # Per-account progress bars
        accounts = []
        for account in saving_accounts:
            prog = account.get_progression(days)
            accounts.append(
                {
                    "pk": account.pk,
                    "detail_url": reverse(
                        "finance:saving_detail", kwargs={"pk": account.pk}
                    ),
                    "name": str(account),
                    "value": float(account.get_value().amount),
                    "progression": float(prog.gross_progression),
                    "progression_percent": min(
                        max(float(prog.gross_progression), 0), 100
                    ),
                    "progression_css": (
                        "success"
                        if prog.gross_progression > 0
                        else "danger"
                        if prog.gross_progression < 0
                        else "secondary"
                    ),
                    "icon": "bi-piggy-bank",
                    "type": "savings",
                    "owner": account.owner or "",
                    "is_favorite": account.is_favorite,
                }
            )

        for account in investment_accounts:
            prog = account.get_progression(days)
            accounts.append(
                {
                    "pk": account.pk,
                    "detail_url": reverse(
                        "finance:investment_detail", kwargs={"pk": account.pk}
                    ),
                    "name": str(account),
                    "value": float(account.current_value.amount),
                    "progression": float(prog.gross_progression),
                    "progression_percent": min(
                        max(float(prog.gross_progression), 0), 100
                    ),
                    "progression_css": (
                        "success"
                        if prog.gross_progression > 0
                        else "danger"
                        if prog.gross_progression < 0
                        else "secondary"
                    ),
                    "icon": "bi-bar-chart-line",
                    "type": "investment",
                    "owner": account.owner or "",
                    "is_favorite": account.is_favorite,
                }
            )

        # Alerts
        alerts = []
        for account in saving_accounts:
            prog = account.get_progression(days)
            if prog.gross_progression < -5:
                alerts.append(
                    {
                        "account": str(account),
                        "message": f"Decreased by {abs(prog.gross_progression):.2f}%",
                        "type_css": "danger",
                    }
                )
        for account in investment_accounts:
            prog = account.get_progression(days)
            if prog.gross_progression < -5:
                alerts.append(
                    {
                        "account": str(account),
                        "message": f"Decreased by {abs(prog.gross_progression):.2f}%",
                        "type_css": "danger",
                    }
                )

        return JsonResponse(
            {
                "breakdown_labels": breakdown_labels,
                "breakdown_values": breakdown_values,
                "accounts": accounts,
                "alerts": alerts,
            }
        )
