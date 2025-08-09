from django.urls import path
from django.contrib.auth import views as auth_views
from . import views

urlpatterns = [
    # Аутентификация
    path('register/', views.register_view, name='register'),
    path('login/', views.login_view, name='login'),
    path('logout/', auth_views.LogoutView.as_view(next_page='login'), name='logout'),
    
    # Основные страницы
    path('', views.chat_view, name='chat'),
    path('archive/', views.archive_view, name='archive'),
    path('archive/<int:archive_id>/', views.archived_chat_detail, name='archived_chat_detail'),
    
    # API endpoints
    path('api/send-message/', views.send_message, name='send_message'),
    path('api/message-status/<int:message_id>/', views.get_message_status, name='message_status'),
    path('api/chat-messages/', views.get_chat_messages, name='chat_messages'),
    path('api/archive-chat/', views.archive_chat_manually, name='archive_chat_manually'),
    

]