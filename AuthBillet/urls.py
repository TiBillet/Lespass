from django.urls import include, path
from rest_framework import routers
from rest_framework_simplejwt.views import TokenObtainPairView, TokenVerifyView

from AuthBillet import views as auth_view
from AuthBillet.views import test_api_key
# TokenRefreshViewCustom, OAauthApi, OAauthCallback, SetPasswordIfEmpty

router = routers.DefaultRouter()
router.register(r'me', auth_view.MeViewset, basename='me')
# router.register(r'setpassword', auth_view.SetPassword, basename='setpassword')

urlpatterns = [
    path('', include(router.urls)),

    # path('token/', TokenObtainPairView.as_view(), name='token_obtain_pair'),
    # path('token/refresh/', TokenRefreshViewCustom.as_view(), name='token_refresh'),


    path('keytest/', test_api_key.as_view(), name='test_api_key'),
    # path('SetPasswordIfEmpty/', SetPasswordIfEmpty.as_view(), name='setpassword'),



    # path('token/verify/', TokenVerifyView.as_view(), name='token_verify'),
    # path('create/', create_user.as_view(), name='create_user'),
    # path('requestoauth/', OAauthApi.as_view(), name='requestoauth'),
    # path('oauth/', OAauthCallback.as_view(), name='oauth'),
    # uniquement pour tenant public :
    # path('terminal/', create_terminal_user.as_view(), name='create_terminal_user'),

    path('activate/<str:uid>/<str:token>', auth_view.activate, name='activate'),
]