from django.contrib import admin

from glad import settings

from .models import Account, AccountBalance, AccountTransaction, AccountType

# Register your models here.


if settings.ENVIRONMENT == "development":
    admin.site.register(Account)
    admin.site.register(AccountTransaction)
    admin.site.register(AccountBalance)

admin.site.register(AccountType)
