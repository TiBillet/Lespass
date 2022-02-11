from django.urls import include, path, re_path

from AuthBillet import views as auth_view
from rest_framework_simplejwt.views import TokenObtainPairView, TokenRefreshView, TokenVerifyView

from AuthBillet.views import create_user

urlpatterns = [
    path('token/', TokenObtainPairView.as_view(), name='token_obtain_pair'),
    path('token/refresh/', TokenRefreshView.as_view(), name='token_refresh'),
    path('token/verify/', TokenVerifyView.as_view(), name='token_verify'),
    path('create/', create_user.as_view(), name='create_user'),
    path('activate/<str:uid>/<str:token>', auth_view.activate.as_view()),
]