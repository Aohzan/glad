# Generated manually on 2026-05-10

from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("property", "0033_alter_amortizationasset_duration_years"),
    ]

    operations = [
        migrations.AlterField(
            model_name="propertyledgerentry",
            name="management_category",
            field=models.CharField(
                choices=[
                    ("rent_collected", "Rent collected"),
                    ("charges_collected", "Charges collected"),
                    ("other_income", "Other income"),
                    ("deposit_in", "Deposit received"),
                    ("manager_reversal", "Manager reversal"),
                    ("management_fees", "Management fees"),
                    ("letting_fees", "Letting fees"),
                    ("other_general_fees", "Other general fees"),
                    ("coownership", "Co-ownership fees"),
                    ("maintenance", "Routine maintenance"),
                    ("works", "Works"),
                    ("furnitures", "Furnitures"),
                    ("insurance", "Insurance"),
                    ("property_tax", "Property tax"),
                    ("cfe", "CFE"),
                    ("misc_deductible", "Miscellaneous deductible"),
                    ("loan_interest", "Loan interest"),
                    ("loan_insurance", "Loan insurance"),
                    ("rental_guarantee", "Rental guarantee"),
                    ("loan_repayment", "Loan capital repayment"),
                    ("deposit_out", "Deposit returned"),
                    ("non_deductible", "Other non-deductible"),
                    ("alur_works_fund", "ALUR works fund"),
                ],
                max_length=30,
                verbose_name="Category",
            ),
        ),
    ]
