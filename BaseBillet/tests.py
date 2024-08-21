import json

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.serializers.json import DjangoJSONEncoder
from django.test import TestCase, tag

from AuthBillet.utils import get_or_create_user


class BaseBilletTest(TestCase):

    def setUp(self):
        settings.DEBUG = True
        # User = get_user_model()
        # self.rootuser = User.objects.create_superuser('rootuser', 'root@root.root', 'ROOTUSERPASSWORD')

        adminuser = get_or_create_user(
            email="admin@admin.admin",
            password="TESTADMINPASSWORD",
            set_active=True,
            send_mail=False,
        )
        adminuser.is_staff=True
        adminuser.is_active=True
        adminuser.save()
        self.adminuser = adminuser

        # log_admin = self.client.login(username='testadmin', password='TESTADMINPASSWORD')

    def admin_get(self, path):
        log_admin = self.client.login(username='admin@admin.admin', password='TESTADMINPASSWORD')
        response = self.client.get(f'{path}', follow=True)
        return response

    def admin_post(self, path, data):
        log_admin = self.client.login(username='testadmin', password='TESTADMINPASSWORD')

        response = self.client.post(f'{path}',
                                    data=json.dumps(data, cls=DjangoJSONEncoder),
                                    content_type="application/json",
                                    HTTP_X_REQUESTED_WITH='XMLHttpRequest')
        return response

    # def x_test_admin_get(self):
    #     pass

    @tag('adminpost')
    def x_test_admin_post(self):
        hello_lespass = self.admin_post(f'/api/get_user_pub_pem/',
                                      data={
                                          "email": f"admin@admin.admin",
                                      })


# test = BaseBilletTest()
# test.setUp()
# test.test_admin_post()