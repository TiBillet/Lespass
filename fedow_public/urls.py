from rest_framework import routers

import fedow_public.views as fviews

router = routers.DefaultRouter()

router.register(r'asset', fviews.AssetViewset, basename='asset')

urlpatterns = [
    # path('', base_view.home, name="index"),
]

urlpatterns += router.urls
