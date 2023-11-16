from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import UserViewSet, FriendRequestViewSet

router = DefaultRouter()
router.register(r'users', UserViewSet)
router.register(r'friend-requests', FriendRequestViewSet)

urlpatterns = [
    path('', include(router.urls)),
]
