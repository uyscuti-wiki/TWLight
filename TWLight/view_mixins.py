"""
Commonly needed custom view mixins.

Note that these do *not* use something like django-braces' UserPassesTestMixin,
because we may need to use multiple tests in one view (e.g. must be a
coordinator AND must have agreed to the terms of use). If we used that mixin,
test functions and login URLs would overwrite each other. Using the dispatch
function and super() means we can chain as many access tests as we'd like.
"""
import ast
import requests

from bs4 import BeautifulSoup

from urllib import urlencode
from urlparse import ParseResult

from django.contrib import messages
from django.contrib.auth import REDIRECT_FIELD_NAME
from django.contrib.auth.models import User
from django.core.exceptions import PermissionDenied
from django.core.urlresolvers import reverse_lazy
from django.http import HttpResponseRedirect, Http404

from TWLight.applications.models import Application
from TWLight.resources.models import Partner
from TWLight.users.models import Editor
from TWLight.users.groups import get_coordinators, get_restricted

import logging
logger = logging.getLogger(__name__)

coordinators = get_coordinators()

class CoordinatorOrSelf(object):
    """
    Restricts visibility to:
    * The designated Coordinator for partner related to the object; or
    * The Editor who owns (or is) the object in the view; or
    * Superusers.

    This mixin assumes that the decorated view has a get_object method, and that
    the object in question has a ForeignKey, 'user', to the User model, or else
    is an instance of User.
    """

    def test_func_coordinator_or_self(self, user):
        obj_owner_test = False # Set default.

        try:
            obj = self.get_object()
            if obj:
                if isinstance(obj, User):
                    obj_owner_test = (obj.pk == user.pk)
                else:
                    obj_owner_test = (obj.user.pk == user.pk)
        except AttributeError:
            # Keep the default.
            pass

        obj_coordinator_test = False # Set default.

        # If the user is a coordinator run more tests
        if user in coordinators.user_set.all():
            try:
                obj = self.get_object()
                if obj:
                        # Return true if the object is an editor and has
                        # at least one application to a partner for whom
                        # the user is a designated coordinator.
                        if isinstance(obj, Editor):
                            obj_coordinator_test = (Application.objects.filter(
                                editor__pk=obj.pk,
                                partner__coordinator__pk=user.pk
                            ).exists())
                        # Return true if the object is an application to a
                        # partner for whom the user is a designated coordinator
                        elif isinstance(obj, Application):
                            obj_coordinator_test = (
                                obj.partner.coordinator.pk == user.pk
                            )
                        elif isinstance(obj, Partner):
                            obj_coordinator_test = (
                                obj.coordinator.pk == user.pk
                            )
            except AttributeError:
                # Keep the default.
                pass

        return (user.is_superuser or
                obj_coordinator_test or
                obj_owner_test)


    def dispatch(self, request, *args, **kwargs):
        if not self.test_func_coordinator_or_self(request.user):
            messages.add_message(request, messages.WARNING, 'You must be the '
                    'designated coordinator or the owner to do that.')
            raise PermissionDenied

        return super(CoordinatorOrSelf, self).dispatch(
            request, *args, **kwargs)



class CoordinatorsOnly(object):
    """
    Restricts visibility to:
    * Coordinators; or
    * Superusers.
    """


    def test_func_coordinators_only(self, user):
        return (user.is_superuser or
                user in coordinators.user_set.all())


    def dispatch(self, request, *args, **kwargs):
        if not self.test_func_coordinators_only(request.user):
            messages.add_message(request, messages.WARNING, 'You must be a '
                    'coordinator to do that.')
            raise PermissionDenied

        return super(CoordinatorsOnly, self).dispatch(
            request, *args, **kwargs)



class PartnerCoordinatorOnly(object):
    """
    Restricts visibility to:
    * The designated Coordinator for partner related to the object; or
    * Superusers.

    This mixin assumes that the decorated view has a get_object method, and that
    the object in question has a ForeignKey, 'user', to the User model, or else
    is an instance of User.
    """

    def test_func_coordinator_or_self(self, user):

        obj_coordinator_test = False # Set default.

        # If the user is a coordinator run more tests
        if user in coordinators.user_set.all():
            try:
                obj = self.get_object()
                if obj:
                        # Return true if the object is an editor and has
                        # at least one application to a partner for whom
                        # the user is a designated coordinator.
                        if isinstance(obj, Editor):
                            obj_coordinator_test = (Application.objects.filter(
                                editor__pk=obj.pk,
                                partner__coordinator__pk=user.pk
                            ).exists())
                        # Return true if the object is an application to a
                        # partner for whom the user is a designated coordinator
                        elif isinstance(obj, Application):
                            obj_coordinator_test = (
                                obj.partner.coordinator.pk == user.pk
                            )
                        elif isinstance(obj, Partner):
                            obj_coordinator_test = (
                                obj.coordinator.pk == user.pk
                            )
            except AttributeError:
                # Keep the default.
                pass

        return (user.is_superuser or
                obj_coordinator_test)


    def dispatch(self, request, *args, **kwargs):
        if not self.test_func_coordinator_or_self(request.user):
            messages.add_message(request, messages.WARNING, 'You must be the '
                    'designated coordinator or the owner to do that.')
            raise PermissionDenied

        return super(PartnerCoordinatorOnly, self).dispatch(
            request, *args, **kwargs)



class EditorsOnly(object):
    """
    Restricts visibility to:
    * Editors.

    Unlike other views this does _not_ automatically permit superusers, because
    some views need user.editor to exist, which it may not if the user was
    created via django's createsuperuser command-line function rather than via
    OAuth.
    """

    def test_func_editors_only(self, user):
        return hasattr(user, 'editor')


    def dispatch(self, request, *args, **kwargs):
        if not self.test_func_editors_only(request.user):
            messages.add_message(request, messages.WARNING, 'You must be a '
                    'coordinator or an editor to do that.')
            raise PermissionDenied

        return super(EditorsOnly, self).dispatch(
            request, *args, **kwargs)



class SelfOnly(object):
    """
    Restricts visibility to:
    * The user who owns (or is) the object in question.

    This mixin assumes that the decorated view has a get_object method, and that
    the object in question has a ForeignKey, 'user', to the User model, or else
    is an instance of User.
    """

    def test_func_self_only(self, user):
        obj_owner_test = False # set default

        obj = self.get_object()

        try:
            if isinstance(obj, User):
                obj_owner_test = (obj.pk == user.pk)
            else:
                obj_owner_test = (self.get_object().user.pk == user.pk)
        except AttributeError:
            pass

        return obj_owner_test


    def dispatch(self, request, *args, **kwargs):
        if not self.test_func_self_only(request.user):
            messages.add_message(request, messages.WARNING, 'You must be the '
                    'owner to do that.')
            raise PermissionDenied

        return super(SelfOnly, self).dispatch(
            request, *args, **kwargs)



class ToURequired(object):
    """
    Restricts visibility to:
    * Users who have agreed with the site's terms of use.
    * Superusers.
    """

    def test_func_tou_required(self, user):
        try:
            return user.is_superuser or user.userprofile.terms_of_use
        except AttributeError:
            # AnonymousUser won't have a userprofile...but AnonymousUser hasn't
            # agreed to the Terms, either, so we can safely deny them.
            return False


    def dispatch(self, request, *args, **kwargs):
        if not self.test_func_tou_required(request.user):
            messages.add_message(request, messages.INFO,
                'You need to agree to the terms of use before you can do that.')

            # Remember where they were trying to go, so we can redirect them
            # back after they agree. There's logic in TermsView to pick up on
            # this parameter.
            next_path = request.path
            next_param = urlencode({REDIRECT_FIELD_NAME: next_path})
            path = reverse_lazy('terms')
            new_url = ParseResult(scheme='', netloc='', path=path, params='',
                query=next_param, fragment='').geturl()            
            return HttpResponseRedirect(new_url)

        return super(ToURequired, self).dispatch(
            request, *args, **kwargs)



class EmailRequired(object):
    """
    Restricts visibility to:
    * Users who have an email on file.
    * Superusers.
    """

    def test_func_email_required(self, user):
        return bool(user.email) or user.is_superuser


    def dispatch(self, request, *args, **kwargs):
        if not self.test_func_email_required(request.user):
            messages.add_message(request, messages.INFO,
                'You need to have an email address on file before you can do that.')

            # Remember where they were trying to go, so we can redirect them
            # back after they agree. There's logic in TermsView to pick up on
            # this parameter.
            next_path = request.path
            next_param = urlencode({REDIRECT_FIELD_NAME: next_path})
            path = reverse_lazy('users:email_change')
            new_url = ParseResult(scheme='', netloc='', path=path, params='',
                query=next_param, fragment='').geturl()            
            return HttpResponseRedirect(new_url)

        return super(EmailRequired, self).dispatch(
            request, *args, **kwargs)



class DataProcessingRequired(object):
    """
    Used to restrict views from users with data processing restricted.
    """

    def test_func_data_processing_required(self, user):
        restricted = get_restricted()
        return user in restricted.user_set.all()


    def dispatch(self, request, *args, **kwargs):
        if self.test_func_data_processing_required(request.user):
            # No need to give the user a message because they will already
            # have the generic data processing notice.
            raise PermissionDenied

        return super(DataProcessingRequired, self).dispatch(
            request, *args, **kwargs)



class NotDeleted(object):
    """
    Used to check that the submitting user hasn't deleted their account.
    Without this, users hit a Server Error if trying to navigate directly
    to an app from a deleted user.
    """

    def test_func_not_deleted(self, object):
        obj = self.get_object()
        return obj.editor is None

    def dispatch(self, request, *args, **kwargs):
        if self.test_func_not_deleted(object):
            raise Http404

        return super(NotDeleted, self).dispatch(
            request, *args, **kwargs)



class APIPartnerDescriptions(object):
    """
    Make MediaWiki API calls to get partner short, long, and collection descriptions,
    and process the data before being consumed by views
    """

    def get_partner_short_description_api(self, user_language, **kwargs):
        response = requests.get('https://meta.wikimedia.org/w/api.php?action=parse&format=json&page=Library_Card_platform%2FTranslation%2FPartners%2FShort_description%2F{partner_pk}/{language_code}&prop=wikitext|revid'.format(partner_pk=kwargs['pk'], language_code=user_language))
        short_desc_json = response.json()
        requested_language = True
        
        if 'error' in short_desc_json and user_language == 'en':
            short_description = False
        elif 'error' in short_desc_json:
            response = requests.get('https://meta.wikimedia.org/w/api.php?action=parse&format=json&page=Library_Card_platform%2FTranslation%2FPartners%2FShort_description%2F{partner_pk}/en&prop=wikitext|revid'.format(partner_pk=kwargs['pk']))
            short_desc_json = response.json()
            requested_language = False
        if 'error' not in short_desc_json:
            revision_id = int(short_desc_json.get('parse').get('revid'))
            return self.parse_json_to_wikitext(short_desc_json), requested_language, revision_id
        else:
            revision_id = None
            short_description = None
            return short_description, requested_language, revision_id

    def parse_json_to_wikitext(self, short_desc_json):
        short_desc_html = short_desc_json.get('parse').get('wikitext').get('*')
        unicode_short_desc = BeautifulSoup(short_desc_html, 'lxml')
        short_description = unicode_short_desc.find('div').get_text()
        return short_description