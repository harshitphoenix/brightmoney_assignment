from django.urls import path
from .views import UserDetailAPI,RegisterUserAPIView, LogoutUserAPIView
urlpatterns = [
  path("get-details",UserDetailAPI.as_view()),
  path('register',RegisterUserAPIView.as_view()),
  path('logout',LogoutUserAPIView.as_view())
]