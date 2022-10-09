from django.urls import path
from . import views

urlpatterns = [
    path('api/get_link_token', views.LinkTokenAPIView.as_view(), name='get-link-token'),
    path('api/get_public_token', views.PublicTokenAPIView.as_view(), name='get-public-token'),
    path('api/get_access_token', views.AccessTokenAPIView.as_view(), name='get-access-token'),
    path('api/get_transactions', views.GetTransactionsAPI.as_view(), name='get-transaction'), 
    path('api/accounts', views.AccountInfoAPIView.as_view(), name='get-balance'),
    path('api/webhook', views.webhook, name='webhook'),
]
