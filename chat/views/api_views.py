import json
import threading

from django.shortcuts import get_object_or_404
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods

from ..models import Chat, Message
from ..services import ChatService


@login_required
@csrf_exempt
@require_http_methods(["POST"])
def send_message(request):
    
    try:
        data = json.loads(request.body)
        message_content = data.get('message', '').strip()
        
        if not message_content:
            return JsonResponse({
                'error': 'Сообщение не может быть пустым'
            }, status=400)
        
        chat_service = ChatService()
        assistant_message = chat_service.process_user_message(
            request.user, 
            message_content
        )
        
        # Запускаем генерацию ответа в отдельном потоке
        def generate_async():
            chat_service.generate_response_stages(assistant_message.id)
        
        thread = threading.Thread(target=generate_async)
        thread.daemon = True
        thread.start()
        
        return JsonResponse({
            'success': True,
            'message_id': assistant_message.id,
            'user_message': message_content
        })
        
    except json.JSONDecodeError:
        return JsonResponse({
            'error': 'Неверный формат JSON'
        }, status=400)
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)


@login_required
@require_http_methods(["GET"])
def get_message_status(request, message_id):
    
    try:
        message = get_object_or_404(
            Message, 
            id=message_id, 
            chat__user=request.user
        )
        
        return JsonResponse({
            'id': message.id,
            'content': message.content,
            'is_generating': message.is_generating,
            'generation_stage': message.generation_stage,
            'generation_status_text': message.generation_status_text,
            'created_at': message.created_at.isoformat()
        })
        
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)


@login_required
@require_http_methods(["GET"])
def get_chat_messages(request):
    
    try:
        chat_service = ChatService()
        chat = chat_service.get_or_create_chat(request.user)
        messages = chat.messages.all()
        
        messages_data = []
        for message in messages:
            messages_data.append({
                'id': message.id,
                'role': message.role,
                'content': message.content,
                'is_generating': message.is_generating,
                'generation_stage': message.generation_stage,
                'is_context_boundary': message.is_context_boundary,
                'created_at': message.created_at.isoformat()
            })
        
        return JsonResponse({
            'messages': messages_data,
            'chat_id': chat.id
        })
        
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)


@login_required
@csrf_exempt
@require_http_methods(["POST"])
def archive_chat_manually(request):
    
    try:
        chat_service = ChatService()
        chat = Chat.objects.filter(
            user=request.user, 
            is_archived=False
        ).first()
        
        if chat:
            chat_service.archive_chat(chat)
            # Создаем новый чат для пользователя
            new_chat = chat_service.get_or_create_chat(request.user)
            return JsonResponse({
                'success': True, 
                'message': 'Чат успешно архивирован',
                'new_chat_id': new_chat.id
            })
        else:
            return JsonResponse({
                'error': 'Активный чат не найден'
            }, status=404)
            
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)