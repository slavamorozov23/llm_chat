import asyncio
import json
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
        self.staged_generation = StagedGenerationService()
        self.message_manager = MessageManager()
    
    def _init_detailed_raw_response(self):
        
        return {
            "generation_type": "",  # "standard" или "staged" 
            "generation_stages": [],
            "total_requests": 0,
            "start_time": "",
            "end_time": "",
            "final_response": "",
            "errors": []
        }
    
    def _add_detailed_request_to_raw_response(self, raw_response_data, stage_info, detailed_response):
        
        stage_entry = {
            "stage": stage_info,
            "requests": []
        }
        
        if isinstance(detailed_response, list):
            # Множественные запросы (staged generation)
            for response in detailed_response:
                stage_entry["requests"].append(response)
                raw_response_data["total_requests"] += 1
        else:
            # Одиночный запрос (standard generation)
            stage_entry["requests"].append(detailed_response)
            raw_response_data["total_requests"] += 1
        
        raw_response_data["generation_stages"].append(stage_entry)
        return raw_response_data
    
    def generate_response_stages(self, message_id):
        
        try:
            from ..models import Message
            from datetime import datetime
            
            message = Message.objects.get(id=message_id)
            chat = message.chat
            
            # Инициализируем детальное логирование
            raw_response_data = self._init_detailed_raw_response()
            raw_response_data["start_time"] = datetime.now().isoformat()
            
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
                raw_response_data["generation_type"] = "staged"
                
                # Используем поэтапную генерацию по конфигурации
                self.message_manager.update_message_status(
                    message, 
                    "Запускаю поэтапную генерацию...", 
                    1
                )
                
                # Создаем callback функцию для обновления статуса
                def status_callback(status_text, stage_number):
                    self.message_manager.update_message_status(message, status_text, stage_number)
                
                # Запускаем асинхронную генерацию с детальным логированием
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                try:
                    final_response, staged_detailed_data = loop.run_until_complete(
                        self.staged_generation.generate_staged_response_detailed(
                            user_message.content, 
                            chat.user,
                            status_callback
                        )
                    )
                    
                    # Добавляем данные staged generation в raw_response
                    for stage_data in staged_detailed_data:
                        self._add_detailed_request_to_raw_response(
                            raw_response_data, 
                            stage_data["stage_name"], 
                            stage_data["detailed_responses"]
                        )
                    
                    raw_response_data["final_response"] = final_response
                    raw_response_data["end_time"] = datetime.now().isoformat()
                    
                    self.message_manager.finalize_message(message, final_response)
                finally:
                    loop.close()
            else:
                raw_response_data["generation_type"] = "standard"
                
                # Используем стандартную поэтапную генерацию
                final_response = self._generate_standard_stages_detailed(
                    message, user_message, chat_history, raw_response_data
                )
                
                raw_response_data["final_response"] = final_response
                raw_response_data["end_time"] = datetime.now().isoformat()
            
            # Сохраняем детальную информацию в raw_response
            message.raw_response = json.dumps(raw_response_data, ensure_ascii=False, indent=2)
            message.save(update_fields=['raw_response'])
                
        except Exception as e:
            logger.error(f"Error generating response: {e}")
            error_message = f"Ошибка генерации: {str(e)}"
            try:
                from ..models import Message
                from datetime import datetime
                
                message = Message.objects.get(id=message_id)
                
                # Записываем ошибку в детальный лог
                if 'raw_response_data' in locals():
                    raw_response_data["errors"].append({
                        "timestamp": datetime.now().isoformat(),
                        "error": str(e),
                        "stage": "generation_error"
                    })
                    raw_response_data["end_time"] = datetime.now().isoformat()
                    message.raw_response = json.dumps(raw_response_data, ensure_ascii=False, indent=2)
                    message.save(update_fields=['raw_response'])
                
                self.message_manager.handle_generation_error(message, error_message)
            except Exception as inner_e:
                logger.error(f"Failed to handle error: {inner_e}")
    
    def _generate_standard_stages_detailed(self, message, user_message, chat_history, raw_response_data):
        
        openrouter = OpenRouterService()
        
        # Этап 1: Первичная генерация
        self.message_manager.update_message_status(
            message, 
            "Генерирую первичный ответ...", 
            1
        )
        
        # Подготавливаем сообщения для API
        messages = []
        for msg in chat_history.exclude(id=message.id):
            messages.append({
                "role": msg.role,
                "content": msg.content
            })
        messages.append({
            "role": "user",
            "content": user_message.content
        })
        
        # Получаем детальную информацию о первичном запросе
        primary_detailed = openrouter._make_request(
            messages,
            stage_info="Этап 1: Первичная генерация ответа",
            prompt_info=f"Запрос пользователя: {user_message.content[:100]}..."
        )
        
        if not primary_detailed.get("success"):
            raise Exception(f"Ошибка первичной генерации: {primary_detailed.get('error')}")
        
        primary_response = primary_detailed["response"]["response_content"]
        
        # Добавляем в детальный лог
        self._add_detailed_request_to_raw_response(
            raw_response_data, 
            "Этап 1: Первичная генерация", 
            primary_detailed
        )
        
        # Этап 2: Убираем лишнюю информацию
        self.message_manager.update_message_status(
            message, 
            "Убираю лишнюю информацию...", 
            2
        )
        
        edit_messages = [
            {
                "role": "system",
                "content": "Ты редактор текста. Убери из ответа лишнюю воду, оставь только суть. Сохрани полезную информацию, но сделай текст более кратким и точным."
            },
            {
                "role": "user",
                "content": f"Исходный вопрос: {user_message.content}\n\nОтвет для редактирования: {primary_response}"
            }
        ]
        
        edit_detailed = openrouter._make_request(
            edit_messages,
            temperature=0.3,
            stage_info="Этап 2: Убираю лишнюю информацию",
            prompt_info="Редактирование ответа для убирания воды"
        )
        
        if not edit_detailed.get("success"):
            # Если редактирование не удалось, используем первичный ответ
            edited_response = primary_response
            raw_response_data["errors"].append({
                "timestamp": edit_detailed.get("request", {}).get("timestamp", ""),
                "error": edit_detailed.get("error", "Неизвестная ошибка"),
                "stage": "Этап 2: Редактирование"
            })
        else:
            edited_response = edit_detailed["response"]["response_content"]
        
        # Добавляем в детальный лог
        self._add_detailed_request_to_raw_response(
            raw_response_data, 
            "Этап 2: Убираю лишнюю информацию", 
            edit_detailed
        )
        
        # Этап 3: Проверяем соответствие
        self.message_manager.update_message_status(
            message, 
            "Проверяю соответствие ответа...", 
            3
        )
        
        verify_messages = [
            {
                "role": "system",
                "content": "Проверь, отвечает ли данный текст на вопрос пользователя. Если да, верни текст как есть. Если нет, исправь его так, чтобы он точно отвечал на вопрос."
            },
            {
                "role": "user",
                "content": f"Вопрос: {user_message.content}\n\nОтвет: {edited_response}"
            }
        ]
        
        verify_detailed = openrouter._make_request(
            verify_messages,
            temperature=0.2,
            stage_info="Этап 3: Проверяю соответствие ответа",
            prompt_info="Проверка соответствия ответа вопросу"
        )
        
        if not verify_detailed.get("success"):
            # Если проверка не удалась, используем отредактированный ответ
            final_response = edited_response
            raw_response_data["errors"].append({
                "timestamp": verify_detailed.get("request", {}).get("timestamp", ""),
                "error": verify_detailed.get("error", "Неизвестная ошибка"),
                "stage": "Этап 3: Проверка соответствия"
            })
        else:
            final_response = verify_detailed["response"]["response_content"]
        
        # Добавляем в детальный лог
        self._add_detailed_request_to_raw_response(
            raw_response_data, 
            "Этап 3: Проверяю соответствие", 
            verify_detailed
        )
        
        # Финальный результат
        self.message_manager.finalize_message(message, final_response)
        return final_response