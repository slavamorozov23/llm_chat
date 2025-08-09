import asyncio
import logging
import threading
from .openrouter_service import OpenRouterService
from .staged_generation_service import StagedGenerationService
from .message_manager import MessageManager

logger = logging.getLogger(__name__)


class ResponseGenerator:
    """
    Генератор ответов - координация процесса генерации ответов ассистента.
    
    НАЗНАЧЕНИЕ И АРХИТЕКТУРА:
    =========================
    
    Этот модуль выделен из ChatService для управления генерацией ответов.
    Является координатором между различными сервисами генерации:
    - StagedGenerationService - для поэтапной генерации
    - OpenRouterService - для стандартной генерации
    - MessageManager - для управления сообщениями
    
    ТИПЫ ГЕНЕРАЦИИ:
    ===============
    
    1. STAGED GENERATION (Поэтапная генерация):
       - Используется когда есть активная конфигурация staged generation
       - Генерация происходит в несколько этапов согласно конфигурации
       - Каждый этап может содержать несколько параллельных промптов
       - Результаты этапов объединяются для финального ответа
       - Поддерживает saveLastAsContext для сохранения контекста
    
    2. STANDARD GENERATION (Стандартная генерация):
       - Используется когда нет активной staged конфигурации
       - Прямое обращение к OpenRouterService
       - Один запрос - один ответ
       - Быстрее, но менее гибко
    
    АСИНХРОННАЯ АРХИТЕКТУРА:
    ========================
    
    generate_response_async() запускается в отдельном потоке:
    - Не блокирует основной поток Django
    - Позволяет пользователю видеть статус генерации в реальном времени
    - Обеспечивает отзывчивость интерфейса
    - Обрабатывает ошибки gracefully
    
    ЖИЗНЕННЫЙ ЦИКЛ ГЕНЕРАЦИИ:
    =========================
    
    1. ИНИЦИАЦИЯ:
       - generate_response() вызывается из ChatService
       - Создается поток для generate_response_async()
       - Возвращается управление немедленно
    
    2. АСИНХРОННАЯ ОБРАБОТКА:
       - Определяется тип генерации (staged/standard)
       - Вызывается соответствующий сервис
       - Обновляется статус сообщения через MessageManager
    
    3. ФИНАЛИЗАЦИЯ:
       - При успехе: finalize_message() с результатом
       - При ошибке: handle_generation_error() с описанием
       - Логирование результата
    
    ИНТЕГРАЦИЯ С STAGED GENERATION:
    ===============================
    
    При наличии активной конфигурации:
    - Получает конфигурацию через get_active_config()
    - Передает управление StagedGenerationService
    - StagedGenerationService координирует:
      * ContextManager - для подготовки контекста
      * GenerationExecutor - для выполнения промптов
      * ConfigManager - для управления конфигурациями
    
    ОБРАБОТКА ОШИБОК:
    =================
    
    Многоуровневая система обработки ошибок:
    1. Ошибки сервисов генерации (OpenRouter, Staged)
    2. Ошибки сети и таймауты
    3. Ошибки конфигурации
    4. Неожиданные исключения
    
    Все ошибки:
    - Логируются с полной информацией
    - Преобразуются в понятные пользователю сообщения
    - Не приводят к потере данных или зависанию
    
    ПРИНЦИПЫ РАБОТЫ:
    ================
    
    1. РАЗДЕЛЕНИЕ ОТВЕТСТВЕННОСТИ:
       - ResponseGenerator - только координация
       - Конкретная генерация делегируется специализированным сервисам
       - MessageManager управляет состоянием сообщений
    
    2. ОТКАЗОУСТОЙЧИВОСТЬ:
       - Graceful degradation при ошибках
       - Всегда финализирует сообщение (успех или ошибка)
       - Не оставляет "висящих" сообщений в состоянии генерации
    
    3. РАСШИРЯЕМОСТЬ:
       - Легко добавить новые типы генерации
       - Модульная архитектура позволяет заменять компоненты
       - Четкие интерфейсы между модулями
    
    ИСПОЛЬЗОВАНИЕ:
    ==============
    
    Вызывается из ChatService.process_user_message():
    ```python
    self.response_generator.generate_response(
        chat=chat,
        user_message=user_message,
        assistant_message=assistant_message
    )
    ```
    
    НЕ УДАЛЯТЬ ЭТИ КОММЕНТАРИИ! Они описывают сложную архитектуру
     координации различных типов генерации ответов.
     """
    
    def __init__(self):
        self.openrouter = OpenRouterService()
        self.staged_generation = StagedGenerationService()
        self.message_manager = MessageManager()
    
    def generate_response_stages(self, message_id):
        
        try:
            from ..models import Message
            message = Message.objects.get(id=message_id)
            chat = message.chat
            
            # Получаем историю чата с ограничением контекста (исключая текущее генерируемое сообщение)
            chat_history = self.message_manager.get_context_limited_history(chat, message.id)
            
            # Получаем последнее сообщение пользователя
            user_message = chat_history.filter(role='user').last()
            if not user_message:
                self.message_manager.handle_generation_error(
                    message, 
                    "Ошибка: не найдено сообщение пользователя"
                )
                return
            
            # Проверяем, есть ли активная конфигурация поэтапной генерации
            config = self.staged_generation.get_active_config(chat.user)
            
            if config:
                # Используем поэтапную генерацию по конфигурации
                self.message_manager.update_message_status(
                    message, 
                    "Запускаю поэтапную генерацию...", 
                    1
                )
                
                # Создаем callback функцию для обновления статуса
                def status_callback(status_text, stage_number):
                    self.message_manager.update_message_status(message, status_text, stage_number)
                
                # Запускаем асинхронную генерацию
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                try:
                    final_response = loop.run_until_complete(
                        self.staged_generation.generate_staged_response(
                            user_message.content, 
                            chat.user,
                            status_callback
                        )
                    )
                    self.message_manager.finalize_message(message, final_response)
                finally:
                    loop.close()
            else:
                # Используем стандартную поэтапную генерацию
                self._generate_standard_stages(message, user_message, chat_history)
                
        except Exception as e:
            print(f"Error generating response: {e}")
            error_message = f"Ошибка генерации: {str(e)}"
            try:
                from ..models import Message
                message = Message.objects.get(id=message_id)
                self.message_manager.handle_generation_error(message, error_message)
            except Exception as inner_e:
                print(f"Failed to handle error: {inner_e}")
    
    def _generate_standard_stages(self, message, user_message, chat_history):
        
        # Этап 1: Первичная генерация
        self.message_manager.update_message_status(
            message, 
            "Генерирую первичный ответ...", 
            1
        )
        
        primary_response = self.openrouter.generate_primary_response(
            user_message.content, 
            chat_history.exclude(id=message.id)
        )
        message.raw_response = primary_response
        message.save()
        
        # Этап 2: Убираем лишнюю информацию
        self.message_manager.update_message_status(
            message, 
            "Убираю лишнюю информацию...", 
            2
        )
        
        edited_response = self.openrouter.remove_fluff(
            primary_response, 
            user_message.content
        )
        
        # Этап 3: Проверяем соответствие
        self.message_manager.update_message_status(
            message, 
            "Проверяю соответствие ответа...", 
            3
        )
        
        final_response = self.openrouter.verify_relevance(
            edited_response, 
            user_message.content
        )
        
        # Финальный результат
        self.message_manager.finalize_message(message, final_response)