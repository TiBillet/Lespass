from django.contrib.auth.tokens import default_token_generator
from rest_framework import serializers
from templated_mail.mail import BaseEmailMessage
from django.utils.translation import ugettext_lazy as _

from djoser import utils
from djoser.conf import settings



class ActivationEmail(BaseEmailMessage):
    template_name = "email/activation.html"

    def get_context_data(self):
        # ActivationEmail can be deleted
        print("activation !")
        context = super().get_context_data()
        # print(f"context : {context}")
        # import ipdb; ipdb.set_trace()

        user = context.get("user")
        context["site_name"] = self.request.tenant.name
        context["domain"] = self.request.tenant.domain_url
        context["uid"] = utils.encode_uid(user.pk)
        context["token"] = default_token_generator.make_token(user)
        context["url"] = settings.ACTIVATION_URL.format(**context)
        print(f"context : {context}")
        return context

    def send(self, to, *args, **kwargs):

        from_email = kwargs.get('from_email', 'contact@tibillet.re')

        self.render()

        self.to = to
        self.cc = kwargs.pop('cc', [])
        self.bcc = kwargs.pop('bcc', [])
        self.reply_to = kwargs.pop('reply_to', [])
        self.from_email = kwargs.pop(
            'from_email', from_email
        )

        # import ipdb; ipdb.set_trace()
        mail_send = super(BaseEmailMessage, self).send(*args, **kwargs)

        print(f'mail_send to {self.to} from {self.from_email} : {mail_send}')


class ConfirmationEmail(BaseEmailMessage):
    template_name = "email/confirmation.html"


class PasswordResetEmail(BaseEmailMessage):
    template_name = "email/password_reset.html"

    def get_context_data(self):
        # PasswordResetEmail can be deleted
        context = super().get_context_data()

        user = context.get("user")
        context["site_name"] = self.request.tenant.name
        context["domain"] = self.request.tenant.domain_url
        context["uid"] = utils.encode_uid(user.pk)
        context["token"] = default_token_generator.make_token(user)
        context["url"] = settings.PASSWORD_RESET_CONFIRM_URL.format(**context)
        return context


class PasswordChangedConfirmationEmail(BaseEmailMessage):
    template_name = "email/password_changed_confirmation.html"


class UsernameChangedConfirmationEmail(BaseEmailMessage):
    template_name = "email/username_changed_confirmation.html"


class UsernameResetEmail(BaseEmailMessage):
    template_name = "email/username_reset.html"

    def get_context_data(self):
        context = super().get_context_data()

        user = context.get("user")
        context["site_name"] = self.request.tenant.name
        context["domain"] = self.request.tenant.domain_url
        context["uid"] = utils.encode_uid(user.pk)
        context["token"] = default_token_generator.make_token(user)
        context["url"] = settings.USERNAME_RESET_CONFIRM_URL.format(**context)
        return context
