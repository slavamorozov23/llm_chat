import logging
from ..models import Message

# Настройка логгера
logger = logging.getLogger(__name__)


class MessageManager:
    """
    Менеджер сообщений - управление жизненным циклом сообщений в чате.
    
    НАЗНАЧЕНИЕ И АРХИТЕКТУРА:
    =========================
    
    Этот модуль выделен из ChatService для управления сообщениями.
    Отвечает за:
    - Создание пользовательских и ассистентских сообщений
    - Управление статусами генерации (is_generating, generation_stage)
    - Обновление содержимого сообщений в процессе генерации
    - Финализацию сообщений после завершения генерации
    - Обработку ошибок генерации
    - Получение истории сообщений с ограничениями по контексту
    
    ЖИЗНЕННЫЙ ЦИКЛ СООБЩЕНИЯ АССИСТЕНТА:
    ====================================
    
    1. СОЗДАНИЕ:
       - create_assistant_message() создает пустое сообщение
       - Устанавливается is_generating = True
       - content = "" (пустое)
       - generation_stage = 0
    
    2. ПРОЦЕСС ГЕНЕРАЦИИ:
       - update_message_status() обновляет статус и этап
       - Может вызываться многократно для отображения прогресса
       - generation_stage увеличивается с каждым этапом
    
    3. ФИНАЛИЗАЦИЯ:
       - finalize_message() устанавливает финальный контент
       - is_generating = False
       - updated_at обновляется
    
    4. ОБРАБОТКА ОШИБОК:
       - handle_generation_error() при ошибках генерации
       - Устанавливает сообщение об ошибке
       - is_generating = False
       - Логирует ошибку для отладки
    
    УПРАВЛЕНИЕ КОНТЕКСТОМ:
    ======================
    
    get_context_limited_history() реализует важную логику:
    - Ограничивает количество сообщений для контекста LLM
    - Предотвращает превышение лимитов токенов
    - Сохраняет хронологический порядок сообщений
    - Исключает сообщения в процессе генерации
    
    ПРИНЦИПЫ РАБОТЫ:
    ================
    
    1. АТОМАРНОСТЬ ОПЕРАЦИЙ:
       - Каждая операция с сообщением атомарна
       - Использует save() для немедленного сохранения в БД
       - Предотвращает потерю данных при сбоях
    
    2. СТАТУСНАЯ МОДЕЛЬ:
       - is_generating четко разделяет завершенные и генерируемые сообщения
       - generation_stage позволяет отслеживать прогресс
       - updated_at автоматически обновляется
    
    3. БЕЗОПАСНОСТЬ:
       - Все операции логируются
       - Ошибки обрабатываются gracefully
       - Нет возможности потерять сообщения пользователя
    
    ИНТЕГРАЦИЯ С ДРУГИМИ МОДУЛЯМИ:
    ==============================
    
    MessageManager используется:
    - ChatService - для создания сообщений при обработке запросов
    - ResponseGenerator - для обновления статуса генерации
    - ChatManager - для получения истории при архивировании
    
    НЕ УДАЛЯТЬ ЭТИ КОММЕНТАРИИ! Они описывают сложную логику управления
    состоянием сообщений и их жизненным циклом.
    """
    
    def create_user_message(self, chat, content):
        
        return Message.objects.create(
            chat=chat,
            role='user',
            content=content
        )
    
    def create_assistant_message(self, chat):
        
        return Message.objects.create(
            chat=chat,
            role='assistant',
            content='Генерирую ответ...',
            is_generating=True,
            generation_stage=1  # 1-первичная генерация
        )
    
    def update_message_status(self, message, status_text, stage):
        
        logger.debug(f"Обновляем статус сообщения: stage={stage}, status_text='{status_text}'")
        message.generation_stage = stage
        message.generation_status_text = status_text
        message.save(update_fields=['generation_stage', 'generation_status_text'])
        logger.debug(f"Статус сохранен в БД: generation_stage={message.generation_stage}, generation_status_text='{message.generation_status_text}'")
    
    def finalize_message(self, message, content):
        
        message.content = content
        message.is_generating = False
        message.generation_stage = 0
        message.save()
    
    def handle_generation_error(self, message, error_content):
        
        message.content = error_content
        message.is_generating = False
        message.generation_stage = -1
        message.save()
    
    def get_context_limited_history(self, chat, current_message_id):
        
        # Получаем все сообщения до текущего (исключая генерируемые)
        all_messages = chat.messages.filter(
            id__lt=current_message_id,
            is_generating=False
        ).order_by('-created_at')  # От новых к старым
        
        context_message_ids = []
        total_chars = 0
        context_limit = 64000
        
        # Сначала сбрасываем все границы контекста
        chat.messages.filter(is_context_boundary=True).update(is_context_boundary=False)
        
        # Идем от новых сообщений к старым и считаем символы
        for message in all_messages:
            message_length = len(message.content)
            
            # Если добавление этого сообщения превысит лимит
            if total_chars + message_length > context_limit:
                # Отмечаем это сообщение как границу контекста
                message.is_context_boundary = True
                message.save()
                break
            
            context_message_ids.append(message.id)
            total_chars += message_length
        
        # Возвращаем QuerySet с сообщениями в правильном порядке (от старых к новым)
        if context_message_ids:
            return chat.messages.filter(id__in=context_message_ids).order_by('created_at')
        else:
            return chat.messages.none()