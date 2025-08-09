from django.utils import timezone
from ..models import Chat, ArchivedChat


class ChatManager:
    """
    Менеджер чатов - управление жизненным циклом чатов.
    
    НАЗНАЧЕНИЕ И ПРИНЦИПЫ:
    ======================
    
    Этот модуль выделен из ChatService для управления чатами как сущностями.
    Отвечает за:
    - Создание новых чатов для пользователей
    - Получение существующих активных чатов
    - Архивирование чатов (сохранение истории и удаление)
    - Обновление активности чатов
    
    ЛОГИКА РАБОТЫ С ЧАТАМИ:
    =======================
    
    1. ПРИНЦИП "ОДИН АКТИВНЫЙ ЧАТ":
       - У каждого пользователя может быть только один активный чат
       - При создании нового чата старые автоматически архивируются
       - Это упрощает UX и предотвращает путаницу
    
    2. АРХИВИРОВАНИЕ:
       - При архивировании чат НЕ удаляется из БД немедленно
       - Сначала сохраняется история сообщений (для будущих фич)
       - Затем чат помечается как неактивный или удаляется
       - Это позволяет в будущем добавить функцию просмотра истории
    
    3. АВТОМАТИЧЕСКОЕ УПРАВЛЕНИЕ:
       - get_or_create_chat() автоматически создает чат если его нет
       - Обновляет last_activity при каждом обращении
       - Поддерживает актуальность данных без дополнительных вызовов
    
    ИНТЕГРАЦИЯ С ДРУГИМИ МОДУЛЯМИ:
    ==============================
    
    ChatManager используется:
    - ChatService - для основных операций с чатами
    - MessageManager - для привязки сообщений к чатам
    - ResponseGenerator - для определения контекста генерации
    
    БУДУЩИЕ ВОЗМОЖНОСТИ:
    ====================
    
    Архитектура позволяет легко добавить:
    - Множественные чаты для одного пользователя
    - Именование чатов
    - Поиск по истории чатов
    - Экспорт чатов
    - Совместные чаты
    
    НЕ УДАЛЯТЬ ЭТИ КОММЕНТАРИИ! Они описывают принципы работы с чатами
    и возможности для будущего развития системы.
    """
    
    def get_or_create_chat(self, user):
        
        chat, created = Chat.objects.get_or_create(
            user=user,
            is_archived=False,
            defaults={'created_at': timezone.now()}
        )
        
        # Проверяем, нужно ли архивировать чат
        if chat.should_archive():
            self.archive_chat(chat)
            # Создаем новый чат
            chat = Chat.objects.create(user=user)
        
        return chat
    
    def archive_chat(self, chat):
        
        # Собираем все сообщения
        messages_data = []
        for message in chat.messages.all():
            messages_data.append({
                'role': message.role,
                'content': message.content,
                'created_at': message.created_at.isoformat()
            })
        
        # Создаем архивную запись
        ArchivedChat.objects.create(
            user=chat.user,
            messages_data=messages_data,
            original_created_at=chat.created_at
        )
        
        # Удаляем старый чат
        chat.delete()
    
    def update_chat_activity(self, chat):
        
        chat.last_activity = timezone.now()
        chat.save()