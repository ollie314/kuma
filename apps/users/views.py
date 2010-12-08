import os
import urlparse

from django.conf import settings
from django.contrib import auth
from django.contrib.auth.forms import PasswordResetForm, SetPasswordForm
from django.contrib.auth.models import User
from django.contrib.auth.tokens import default_token_generator
from django.contrib.sites.models import Site
from django.http import HttpResponseRedirect, Http404
from django.views.decorators.http import require_http_methods
from django.shortcuts import get_object_or_404
from django.utils.http import base36_to_int

import jingo

from access.decorators import logout_required, login_required
from sumo.decorators import ssl_required
from sumo.urlresolvers import reverse
from upload.tasks import _create_image_thumbnail
from users.backends import Sha256Backend  # Monkey patch User.set_password.
from users.forms import ProfileForm, AvatarForm
from users.models import Profile, RegistrationProfile
from users.utils import handle_login, handle_register


@ssl_required
def login(request):
    """Try to log the user in."""
    next_url = _clean_next_url(request) or reverse('home')
    form = handle_login(request)

    if request.user.is_authenticated():
        return HttpResponseRedirect(next_url)

    return jingo.render(request, 'users/login.html',
                        {'form': form, 'next_url': next_url})


@ssl_required
def logout(request):
    """Log the user out."""
    auth.logout(request)
    next_url = _clean_next_url(request) if 'next' in request.GET else ''

    return HttpResponseRedirect(next_url or reverse('home'))


@ssl_required
@logout_required
@require_http_methods(['GET', 'POST'])
def register(request):
    """Register a new user."""
    form = handle_register(request)
    if form.is_valid():
        return jingo.render(request, 'users/register_done.html')
    return jingo.render(request, 'users/register.html',
                        {'form': form})


def activate(request, activation_key):
    """Activate a User account."""
    activation_key = activation_key.lower()
    account = RegistrationProfile.objects.activate_user(activation_key)
    return jingo.render(request, 'users/activate.html',
                        {'account': account})


def profile(request, user_id):
    user_profile = get_object_or_404(Profile, user__id=user_id)
    return jingo.render(request, 'users/profile.html',
                        {'profile': user_profile})


@login_required
@require_http_methods(['GET', 'POST'])
def edit_profile(request):
    """Edit user profile."""
    try:
        user_profile = request.user.get_profile()
    except Profile.DoesNotExist:
        # TODO: Once we do user profile migrations, all users should have a
        # a profile. We can remove this fallback.
        user_profile = Profile.objects.create(user=request.user)

    if request.method == 'POST':
        form = ProfileForm(request.POST, request.FILES, instance=user_profile)
        if form.is_valid():
            user_profile = form.save()
            return HttpResponseRedirect(reverse('users.profile',
                                                args=[request.user.id]))
    else:  # request.method == 'GET'
        form = ProfileForm(instance=user_profile)

    # TODO: detect timezone automatically from client side, see
    # http://rocketscience.itteco.org/2010/03/13/automatic-users-timezone-determination-with-javascript-and-django-timezones/

    return jingo.render(request, 'users/edit_profile.html',
                        {'form': form, 'profile': user_profile})


@login_required
@require_http_methods(['GET', 'POST'])
def edit_avatar(request):
    """Edit user avatar."""
    try:
        user_profile = request.user.get_profile()
    except Profile.DoesNotExist:
        # TODO: Once we do user profile migrations, all users should have a
        # a profile. We can remove this fallback.
        user_profile = Profile.objects.create(user=request.user)

    if request.method == 'POST':
        # Upload new avatar and replace old one.
        old_avatar_path = None
        if user_profile.avatar:
            # Need to store the path, not the file here, or else django's
            # form.is_valid() messes with it.
            old_avatar_path = user_profile.avatar.path
        form = AvatarForm(request.POST, request.FILES, instance=user_profile)
        if form.is_valid():
            if old_avatar_path:
                os.unlink(old_avatar_path)
            user_profile = form.save()

            content = _create_image_thumbnail(user_profile.avatar.path,
                                              settings.AVATAR_SIZE)
            # Delete uploaded avatar and replace with thumbnail.
            name = user_profile.avatar.name
            user_profile.avatar.delete()
            user_profile.avatar.save(name, content, save=True)
            return HttpResponseRedirect(reverse('users.edit_profile'))

    else:  # request.method == 'GET'
        form = AvatarForm(instance=user_profile)

    return jingo.render(request, 'users/edit_avatar.html',
                        {'form': form, 'profile': user_profile})


@login_required
@require_http_methods(['GET', 'POST'])
def delete_avatar(request):
    """Delete user avatar."""
    try:
        user_profile = request.user.get_profile()
    except Profile.DoesNotExist:
        # TODO: Once we do user profile migrations, all users should have a
        # a profile. We can remove this fallback.
        user_profile = Profile.objects.create(user=request.user)

    if request.method == 'POST':
        # Delete avatar here
        if user_profile.avatar:
            user_profile.avatar.delete()
        return HttpResponseRedirect(reverse('users.edit_profile'))
    # else:  # request.method == 'GET'

    return jingo.render(request, 'users/confirm_avatar_delete.html',
                        {'profile': user_profile})


def password_reset(request):
    """Password reset form.

    Based on django.contrib.auth.views. This view sends the email.

    """
    if request.method == "POST":
        form = PasswordResetForm(request.POST)
        if form.is_valid():
            form.save(use_https=request.is_secure(),
                      token_generator=default_token_generator,
                      email_template_name='users/email/pw_reset.ltxt')
            return HttpResponseRedirect(reverse('users.pw_reset_sent'))
    else:
        form = PasswordResetForm()

    return jingo.render(request, 'users/pw_reset_form.html', {'form': form})


def password_reset_sent(request):
    """Password reset email sent.

    Based on django.contrib.auth.views. This view shows a success message after
    email is sent.

    """
    return jingo.render(request, 'users/pw_reset_sent.html')


@ssl_required
def password_reset_confirm(request, uidb36=None, token=None):
    """View that checks the hash in a password reset link and presents a
    form for entering a new password.

    Based on django.contrib.auth.views.

    """
    try:
        uid_int = base36_to_int(uidb36)
    except ValueError:
        raise Http404

    user = get_object_or_404(User, id=uid_int)
    context = {}

    if default_token_generator.check_token(user, token):
        context['validlink'] = True
        if request.method == 'POST':
            form = SetPasswordForm(user, request.POST)
            if form.is_valid():
                form.save()
                return HttpResponseRedirect(reverse('users.pw_reset_complete'))
        else:
            form = SetPasswordForm(None)
    else:
        context['validlink'] = False
        form = None
    context['form'] = form
    return jingo.render(request, 'users/pw_reset_confirm.html', context)


def password_reset_complete(request):
    """Password reset complete.

    Based on django.contrib.auth.views. Show a success message.

    """
    return jingo.render(request, 'users/pw_reset_complete.html')


def _clean_next_url(request):
    if 'next' in request.POST:
        url = request.POST.get('next')
    elif 'next' in request.GET:
        url = request.GET.get('next')
    else:
        url = request.META.get('HTTP_REFERER')

    if url:
        parsed_url = urlparse.urlparse(url)
        # Don't redirect outside of SUMO.
        # Don't include protocol+domain, so if we are https we stay that way.
        if parsed_url.scheme:
            site_domain = Site.objects.get_current().domain
            url_domain = parsed_url.netloc
            if site_domain != url_domain:
                url = None
            else:
                url = u'?'.join([getattr(parsed_url, x) for x in
                                ('path', 'query') if getattr(parsed_url, x)])

        # Don't redirect right back to login or logout page
        if parsed_url.path in [settings.LOGIN_URL, settings.LOGOUT_URL]:
            url = None

    return url
