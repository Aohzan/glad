"""Forms managing the members of the household."""

import copy

from django import forms
from django.contrib.auth import get_user_model, password_validation
from django.contrib.auth.validators import UnicodeUsernameValidator
from django.utils.text import slugify
from django.utils.translation import gettext_lazy as _

from .models import Child, UserProfile, is_child

User = get_user_model()


def member_username(first_name: str, prefix: str = "member") -> str:
    """Unique username built from the first name, for a member who cannot log in."""
    base = f"{prefix}-{slugify(first_name) or 'member'}"[:140]
    taken = set(
        User.objects.filter(username__startswith=base).values_list(
            "username", flat=True
        )
    )
    username, number = base, 1
    while username in taken:
        number += 1
        username = f"{base}-{number}"
    return username


def child_username(first_name: str) -> str:
    """Unique username for a child, built from the first name (never used to log in)."""
    return member_username(first_name, prefix="child")


def can_edit_member(acting_user, member) -> bool:
    """True when *acting_user* may edit *member* on the household page.

    A member who logs in is edited by themselves or by a superuser; the
    members who do not log in (children, adults without account) by anyone.
    """
    return (
        bool(getattr(acting_user, "is_superuser", False))
        or acting_user.pk == member.pk
        or not member.has_usable_password()
    )


class ChildForm(forms.ModelForm):
    """A child only needs a first name: the other fields are optional."""

    birth_date = forms.DateField(
        label=_("Birth date"),
        required=False,
        widget=forms.DateInput(attrs={"type": "date"}, format="%Y-%m-%d"),
    )

    class Meta:
        model = Child
        fields = ("first_name", "last_name", "email")

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["first_name"].required = True
        profile = getattr(self.instance, "profile", None)
        if profile is not None:
            self.fields["birth_date"].initial = profile.birth_date


class HouseholdMemberForm(forms.ModelForm):
    """Add or edit a member of the household.

    Anyone sets the names and the birth date. A new member is a child or an
    adult; neither can log in, unless a superuser gives an adult a username
    and a password. A superuser can also give them to an existing adult who
    cannot log in yet; the members who log in manage their password in their
    settings.
    """

    KIND_ADULT = "adult"
    KIND_CHILD = "child"

    birth_date = forms.DateField(
        label=_("Birth date"),
        required=False,
        help_text=_("Used to value a life usufruct (article 669 CGI)."),
        widget=forms.DateInput(
            attrs={"type": "date", "class": "form-control"}, format="%Y-%m-%d"
        ),
    )
    kind = forms.ChoiceField(
        label=_("Member"),
        choices=[(KIND_ADULT, _("Adult")), (KIND_CHILD, _("Child"))],
        initial=KIND_ADULT,
        widget=forms.Select(attrs={"class": "form-select"}),
        help_text=_("A child owns assets but never logs in."),
    )
    can_log_in = forms.BooleanField(
        label=_("Can log in"),
        required=False,
        widget=forms.CheckboxInput(attrs={"class": "form-check-input"}),
    )
    login = forms.CharField(
        label=_("Username"),
        required=False,
        max_length=150,
        validators=[UnicodeUsernameValidator()],
        widget=forms.TextInput(attrs={"class": "form-control", "autocomplete": "off"}),
    )
    password1 = forms.CharField(
        label=_("Password"),
        required=False,
        strip=False,
        widget=forms.PasswordInput(
            attrs={"class": "form-control", "autocomplete": "new-password"}
        ),
    )
    password2 = forms.CharField(
        label=_("Password confirmation"),
        required=False,
        strip=False,
        widget=forms.PasswordInput(
            attrs={"class": "form-control", "autocomplete": "new-password"}
        ),
    )

    LOGIN_FIELDS = ("can_log_in", "login", "password1", "password2")

    class Meta:
        model = User
        fields = ("first_name", "last_name")
        widgets = {
            "first_name": forms.TextInput(attrs={"class": "form-control"}),
            "last_name": forms.TextInput(attrs={"class": "form-control"}),
        }

    def __init__(self, *args, acting_user, **kwargs):
        """*acting_user* is the logged-in user filling the form."""
        super().__init__(*args, **kwargs)
        self.fields["first_name"].required = True
        member = self.instance
        if member.pk:
            del self.fields["kind"]
            profile = getattr(member, "profile", None)
            self.fields["birth_date"].initial = getattr(profile, "birth_date", None)
        self.with_login = bool(getattr(acting_user, "is_superuser", False)) and (
            member.pk is None
            or (not member.has_usable_password() and not is_child(member))
        )
        if not self.with_login:
            for name in self.LOGIN_FIELDS:
                del self.fields[name]

    @property
    def is_new_child(self) -> bool:
        return self.cleaned_data.get("kind") == self.KIND_CHILD

    def clean_login(self) -> str:
        login = self.cleaned_data.get("login", "").strip()
        if (
            login
            and User.objects.filter(username__iexact=login)
            .exclude(pk=self.instance.pk)
            .exists()
        ):
            raise forms.ValidationError(_("A user with that username already exists."))
        return login

    def clean(self):
        cleaned = super().clean() or {}
        if not cleaned.get("can_log_in"):
            return cleaned
        if self.is_new_child:
            self.add_error("can_log_in", _("A child cannot log in."))
            return cleaned
        if not cleaned.get("login") and "login" not in self.errors:
            self.add_error("login", _("Enter the username to log in with."))
        password1, password2 = cleaned.get("password1"), cleaned.get("password2")
        if not password1:
            self.add_error("password1", _("Enter the password to log in with."))
        elif password1 != password2:
            self.add_error("password2", _("The two passwords do not match."))
        else:
            # Checked against a copy: the member is only changed once saved.
            candidate = copy.copy(self.instance)
            candidate.username = cleaned.get("login") or candidate.username
            try:
                password_validation.validate_password(password1, candidate)
            except forms.ValidationError as error:
                self.add_error("password1", error)
        return cleaned

    def save(self, commit: bool = True):
        """Save the member, then its profile (with the other relations).

        With *commit* False, nothing is written: call ``save_m2m()`` after
        saving the returned member, as with any model form.
        """
        member = super().save(commit=False)
        self._created = member.pk is None
        child = self._created and self.is_new_child
        if self.with_login and self.cleaned_data.get("can_log_in"):
            member.username = self.cleaned_data["login"]
            member.set_password(self.cleaned_data["password1"])
        elif self._created:
            member.username = member_username(
                member.first_name, prefix="child" if child else "member"
            )
            member.set_unusable_password()
        if self._created:
            member.is_staff = member.is_superuser = False
        if commit:
            member.save()
            self._save_m2m()
        return member

    def _save_m2m(self):
        super()._save_m2m()  # ty: ignore[unresolved-attribute]
        profile, _created = UserProfile.objects.get_or_create(user=self.instance)
        if self._created:
            profile.is_child = self.is_new_child
        profile.birth_date = self.cleaned_data.get("birth_date")
        profile.save()
        self.instance.profile = profile
