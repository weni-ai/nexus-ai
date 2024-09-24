from django.urls import path
from nexus.zeroshot.api.views import ZeroShotFastPredictAPIView


urlpatterns = [
    path(
        'nlp/zeroshot/zeroshot-fast-predict',
        ZeroShotFastPredictAPIView.as_view(),
        name="zeroshot-fast-prediction"
    ),
]
