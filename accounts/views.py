"""Views for the accounts app."""

from django.contrib.auth.forms import UserCreationForm
from django.urls import reverse_lazy
from django.views.generic import CreateView, TemplateView


class SignUpView(CreateView):
    """View for user registration."""

    form_class = UserCreationForm
    success_url = reverse_lazy("login")
    template_name = "registration/signup.html"


class LogoutConfirmView(TemplateView):
    """View to confirm user logout."""

    template_name = "logout.html"
