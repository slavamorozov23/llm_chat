from django.shortcuts import render, get_object_or_404
from django.contrib.auth.decorators import login_required

from ..models import ArchivedChat
from ..services import ChatService


@login_required
def chat_view(request):
    
    chat_service = ChatService()
    chat = chat_service.get_or_create_chat(request.user)
    messages = chat.messages.all()
    
    return render(request, 'chat/chat.html', {
        'chat': chat,
        'messages': messages
    })


@login_required
def archive_view(request):
    
    archived_chats = ArchivedChat.objects.filter(user=request.user)
    return render(request, 'chat/archive.html', {
        'archived_chats': archived_chats
    })


@login_required
def archived_chat_detail(request, archive_id):
    
    archived_chat = get_object_or_404(
        ArchivedChat, 
        id=archive_id, 
        user=request.user
    )
    
    # Получаем сообщения из JSON данных
    messages = archived_chat.messages_data
    user_messages_count = len([m for m in messages if m['role'] == 'user'])
    
    return render(request, 'chat/archived_chat_detail.html', {
        'archived_chat': archived_chat,
        'messages': messages,
        'user_messages_count': user_messages_count
    })