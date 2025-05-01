# Contributing

## Add default account type

Run `python manage.py makemigrations --empty finance -n add_account_types_xxxx` to create a new migration file in the `finance/migrations` directory.
Add the following code to the migration file:

```python
def add_account_types(apps, schema_editor):
    AccountType = apps.get_model('finance', 'AccountType')
    AccountType.objects.bulk_create([
        # France
        AccountType(
            name="Compte Courant",
            category=AccountType.CATEGORY.CHECKING,
            country="FR"
        )
    ])

class Migration(migrations.Migration):
    operations = [
        migrations.RunPython(add_account_types),
    ]
```
