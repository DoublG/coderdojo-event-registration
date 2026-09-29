from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core import signing
from django.http import Http404
from django.shortcuts import redirect, render
from django.utils.translation import gettext as _
from django.views.decorators.csrf import csrf_exempt

from accounts.consent import set_consent
from accounts.models import User
from dojos.models import Dojo

from .categories import CAN_OPT_OUT, MailCategory, categories_for
from .forms import MailPreferencesForm
from .models import ConsentEvent
from .preferences import set_dojo_mute, set_preference
from .services import read_unsubscribe_token


@login_required
def mail_preferences(request):
    """The account's Mail preferences page: a switch per kind of mail it can
    turn off, a switch per dojo whose news reaches the family (muting one
    dojo, DATA_MODEL.md §25), a switch per child for using their details to choose mails
    (accounts.consent) and the mail language. Above them, the approved
    explanation of what we use to pick relevant mails. (The postcode is on
    the account page's details, accounts.views.edit_account.)"""
    user = request.user
    form = MailPreferencesForm(request.POST or None, user=user)
    if request.method == "POST" and form.is_valid():
        for category, subscribed in form.chosen().items():
            set_preference(user, category, subscribed, ConsentEvent.PREFERENCES)
        for dojo, wanted in form.dojo_choices():
            set_dojo_mute(user, dojo, not wanted, ConsentEvent.PREFERENCES)
        for guardianship, given in form.child_consents():
            set_consent(guardianship, given)
        user.preferred_language = form.cleaned_data["preferred_language"]
        user.save(update_fields=["preferred_language"])
        messages.success(request, _("Your mail preferences are saved."))
        return redirect("mail_preferences")
    return render(request, "mailing/mail_preferences.html", {"form": form})


@csrf_exempt
def mail_unsubscribe(request, token):
    """The link in every mail people can opt out of, no login needed.
    GET shows a confirmation; POST unsubscribes. A POST is also what mail
    clients send for one-click unsubscribe (RFC 8058, the
    List-Unsubscribe-Post header), which carries no CSRF token: hence
    csrf_exempt. The signed token is the only thing it trusts.

    A dojo's news carries the dojo in its token: the page then offers to
    stop only that dojo's mail (DATA_MODEL.md §25), which is also what a
    one-click POST (no `scope`) does. `scope` is "dojo", "category" or
    "all"."""
    try:
        user_id, category, dojo_id = read_unsubscribe_token(token)
    except signing.BadSignature:
        raise Http404 from None
    user = User.objects.filter(pk=user_id).first()
    if user is None or category not in MailCategory.values or not CAN_OPT_OUT[category]:
        raise Http404
    category = MailCategory(category)
    dojo = Dojo.objects.filter(pk=dojo_id).first() if dojo_id and category == MailCategory.DOJO_NEWS else None

    if request.method == "POST":
        scope = request.POST.get("scope") or ("dojo" if dojo else "category")
        if scope == "dojo" and dojo:
            set_dojo_mute(user, dojo, True, ConsentEvent.UNSUBSCRIBE_LINK)
            return render(request, "mailing/unsubscribed.html", {"category": category, "dojo": dojo})
        everything = scope == "all"
        targets = [c for c in categories_for(user) if CAN_OPT_OUT[c]] if everything else [category]
        for target in targets:
            set_preference(user, target, False, ConsentEvent.UNSUBSCRIBE_LINK)
        return render(request, "mailing/unsubscribed.html", {"category": category, "everything": everything})
    return render(request, "mailing/unsubscribe.html", {"category": category, "dojo": dojo, "token": token})
