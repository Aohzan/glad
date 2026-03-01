"""Shared test helpers for finance tests (non-fixture utilities)."""


def setup_csv_import_session(
    user_client,
    account,
    csv_data=None,
    csv_type="saving_value",
    csv_header=None,
):
    """Set up session data for CSV import confirm tests."""
    if csv_data is None:
        csv_data = [[account.name, "1000", "2024-01-01 10:00:00"]]
    if csv_header is None:
        csv_header = ["account", "value", "date"]
    session = user_client.session
    session["csv_type"] = csv_type
    session["csv_header"] = csv_header
    session["csv_data"] = csv_data
    session["app_account_choices"] = [(account.id, str(account))]
    session.save()


def csv_confirm_post_data(account_name, app_account_id):
    """Return formset POST data for the CSV import confirm step (single mapping)."""
    return {
        "accounts-TOTAL_FORMS": "1",
        "accounts-INITIAL_FORMS": "1",
        "accounts-MIN_NUM_FORMS": "0",
        "accounts-MAX_NUM_FORMS": "1000",
        "accounts-0-csv_account_name": account_name,
        "accounts-0-app_account_id": str(app_account_id),
    }
