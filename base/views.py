# Create your views here.
from django.contrib.auth.decorators import login_not_required
from django.http import HttpResponse

from django.template import loader
from finance.models import Account
from property.models import Property


@login_not_required
def index(request):
    if not request.user.is_authenticated:
        return HttpResponse("Welcome, please login.")
    if not request.user.userprofile.household:
        return HttpResponse("You must create or join a household.")

    accounts = Account.objects.filter(
        household_id=request.user.userprofile.household.id,
        is_active=True,
    )
    properties = Property.objects.filter(
        household_id=request.user.userprofile.household.id,
        is_active=True,
    )
    template = loader.get_template("index.html")
    context = {"accounts": accounts, "properties": properties}
    return HttpResponse(template.render(context, request))
