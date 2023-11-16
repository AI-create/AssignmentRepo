from rest_framework import viewsets, status, permissions
from rest_framework.response import Response
from django.contrib.auth import get_user_model
from .models import FriendRequest
from .serializers import UserSerializer, FriendRequestSerializer
from rest_framework.decorators import action
from django.contrib.auth import authenticate
from rest_framework.authtoken.models import Token
from django.db.models import Q
from rest_framework.pagination import LimitOffsetPagination
from django.db.models import Q
from rest_framework.pagination import PageNumberPagination
from rest_framework.authtoken.models import Token
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.permissions import AllowAny
from rest_framework.exceptions import ValidationError
from rest_framework.throttling import UserRateThrottle
from rest_framework.decorators import api_view, authentication_classes, permission_classes
from rest_framework.authentication import TokenAuthentication
from django.contrib.auth import authenticate, login, logout
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt

class SendRequestRateThrottle(UserRateThrottle):
    scope = 'user'


User = get_user_model()


class UserSearchPagination(LimitOffsetPagination):
    default_limit = 10

class UserViewSet(viewsets.ModelViewSet):
    queryset = User.objects.all()
    serializer_class = UserSerializer
    # Set permission_classes for the whole ViewSet
    permission_classes = [IsAuthenticated]

    # Override get_permissions if you want to set different permissions for different actions
    def get_permissions(self):
        if self.action in ['signup', 'signin', 'search']:
            return [permission() for permission in [AllowAny]]
        return super(UserViewSet, self).get_permissions()
    
    # @csrf_exempt
    # @api_view(['POST'])
    # @authentication_classes([])
    # @permission_classes([AllowAny])
    # @action(detail=False, methods=['post'])
    # def signup(request):
    #     username = request.data.get('username')
    #     email = request.data.get('email')
    #     password = request.data.get('password')
        
    #     if User.objects.filter(username=username).exists():
    #         return JsonResponse({'error': 'Username already exists'}, status=400)
        
    #     user, created = User.objects.get_or_create(username=username, email=email)
    #     user.set_password(password)
    #     user.save()

    #     # Retrieve the user instance again to ensure it's up-to-date
    #     user = User.objects.get(username=username)

    #     token, created = Token.objects.get_or_create(user=user)

    #     return JsonResponse({'message': 'Signup successful', 'token': token.key})

    @action(detail=False, methods=['post'], permission_classes=[AllowAny])
    def signup(self, request):
        serializer = UserSerializer(data=request.data)
        if serializer.is_valid():
            user = serializer.save()
            token, created = Token.objects.get_or_create(user=user)
            data = {
                'id': user.id,
                'username': user.username,
                'email': user.email,
                'token': token.key
            }
            return Response(data, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


    # @csrf_exempt
    # @api_view(['POST'])
    # @authentication_classes([TokenAuthentication])
    # @permission_classes([AllowAny])
    @action(detail=False, methods=['post'])
    def signin(request):
        username = request.data.get('username')
        password = request.data.get('password')
        
        user = authenticate(request, username=username, password=password)
        if user is not None:
            login(request, user)

            # Generate or retrieve the token for the user
            token, created = Token.objects.get_or_create(user=user)

            serializer = UserSerializer(user)
            return JsonResponse({'token': token.key, 'user': serializer.data})
        else:
            return JsonResponse({'error': 'Invalid credentials'}, status=400)


    # @csrf_exempt
    # @api_view(['POST'])
    # @authentication_classes([TokenAuthentication])
    # @permission_classes([IsAuthenticated])
    @action(detail=False, methods=['post'])
    def signout(request):
        logout(request)
        return JsonResponse({'message': 'Signout successful'})
    
    @action(detail=False, methods=['get'])
    def search(self, request):
        username_query = request.query_params.get('username', '').lower()
        email_query = request.query_params.get('email', '').lower()

        users = User.objects.all()

        if username_query:
            users = users.filter(username__icontains=username_query)
        if email_query:
            users = users.filter(email__iexact=email_query)

        paginator = PageNumberPagination()
        paginator.page_size = 10
        result_page = paginator.paginate_queryset(users, request)
        serializer = UserSerializer(result_page, many=True, context={'request': request})
        return paginator.get_paginated_response(serializer.data)


class FriendRequestViewSet(viewsets.ModelViewSet):
    queryset = FriendRequest.objects.all()
    serializer_class = FriendRequestSerializer
    permission_classes = [permissions.IsAuthenticated]

    # Define methods for sending, accepting, and rejecting friend requests
    @action(detail=True, methods=['post'])
    def accept(self, request, pk=None):
        friend_request = self.get_object()
        if friend_request.receiver != request.user:
            return Response({"error": "You can't accept this friend request"}, status=status.HTTP_403_FORBIDDEN)
        friend_request.status = 'accepted'
        friend_request.save()
        return Response({"status": "accepted"}, status=status.HTTP_200_OK)

    @action(detail=True, methods=['post'])
    def reject(self, request, pk=None):
        friend_request = self.get_object()
        if friend_request.receiver != request.user:
            return Response({"error": "You can't reject this friend request"}, status=status.HTTP_403_FORBIDDEN)
        friend_request.status = 'rejected'
        friend_request.save()
        return Response({"status": "rejected"}, status=status.HTTP_200_OK)
    
    
    @action(detail=False, methods=['post'], throttle_classes=[SendRequestRateThrottle])
    def send_request(self, request):
        sender = request.user
        receiver_email = request.data.get('email')

        try:
            receiver = User.objects.get(email=receiver_email)
        except User.DoesNotExist:
            return Response({"error": "Receiver not found"}, status=status.HTTP_404_NOT_FOUND)

        if sender == receiver:
            return Response({"error": "Cannot send request to self"}, status=status.HTTP_400_BAD_REQUEST)

        if FriendRequest.objects.filter(sender=sender, receiver=receiver, status='sent').exists():
            return Response({"error": "Friend request already sent"}, status=status.HTTP_400_BAD_REQUEST)

        FriendRequest.objects.create(sender=sender, receiver=receiver, status='sent')
        return Response({"message": "Friend request sent"}, status=status.HTTP_200_OK)
    
    @action(detail=False, methods=['get'])
    def list_friends(self, request):
        user = request.user
        friends = User.objects.filter(
            Q(sent_requests__receiver=user, sent_requests__status='accepted') |
            Q(received_requests__sender=user, received_requests__status='accepted')
        )
        serializer = UserSerializer(friends, many=True)
        return Response(serializer.data, status=status.HTTP_200_OK)
    
    @action(detail=False, methods=['get'])
    def pending_requests(self, request):
        pending_requests = FriendRequest.objects.filter(receiver=request.user, status='sent')
        serializer = FriendRequestSerializer(pending_requests, many=True)
        return Response(serializer.data, status=status.HTTP_200_OK)



