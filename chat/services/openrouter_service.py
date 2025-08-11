import requests
import json
import logging
from datetime import datetime
from django.conf import settings

# Настройка логгера
logger = logging.getLogger(__name__)


class OpenRouterService:
    
    
    def __init__(self):
        # Импортируем модель здесь, чтобы избежать циклических импортов
        from ..models import OpenRouterSettings
        
        # Пытаемся получить настройки из базы данных
        try:
            db_settings = OpenRouterSettings.objects.first()
            if db_settings:
                self.api_key = db_settings.api_key or getattr(settings, 'OPENROUTER_API_KEY', None)
                self.model = db_settings.model
            else:
                # Если настроек в БД нет, используем настройки из settings.py
                self.api_key = getattr(settings, 'OPENROUTER_API_KEY', None)
                self.model = "openai/gpt-oss-20b:free"
        except Exception:
            # Если БД недоступна (например, при миграциях), используем настройки по умолчанию
            self.api_key = getattr(settings, 'OPENROUTER_API_KEY', None)
            self.model = "openai/gpt-oss-20b:free"
            
        if not self.api_key:
            raise Exception("API ключ OpenRouter не настроен ни в базе данных, ни в settings.py")
            
        self.base_url = "https://openrouter.ai/api/v1/chat/completions"
    
    def _make_request(self, messages, temperature=0.7, stage_info=None, prompt_info=None, response_format=None):
        """
        Выполняет запрос к LLM API и возвращает детальную информацию.
        
        Args:
            messages: Список сообщений для API
            temperature: Температура генерации
            stage_info: Информация о стадии (например, "Этап 1: Анализ")
            prompt_info: Информация о конкретном промпте
            response_format: Секция OpenRouter/OAI response_format. Пример:
                {"type": "json_schema", "json_schema": {...}}
            
        Returns:
            dict: Полная информация о запросе и ответе
        """
        try:
            headers = {
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json"
            }
            
            data = {
                "model": self.model,
                "messages": messages,
                "temperature": temperature
            }
            # Добавляем response_format, если задан
            if response_format:
                data["response_format"] = response_format
            
            # Создаем детальную запись о запросе
            request_info = {
                "timestamp": datetime.now().isoformat(),
                "stage_info": stage_info or "Standard generation",
                "prompt_info": prompt_info or "Direct user request",
                "model": self.model,
                "temperature": temperature,
                "request_messages_count": len(messages),
                "request_messages": [
                    {
                        "role": msg.get('role', 'unknown'),
                        "content": msg.get('content', ''),
                        "content_length": len(msg.get('content', ''))
                    } for msg in messages
                ],
                "response_format_meta": (
                    {
                        "type": response_format.get("type"),
                        "schema_keys": list(response_format.get("json_schema", {}).keys()) if isinstance(response_format, dict) else None
                    } if response_format else None
                )
            }
            
            # Детальное логирование запроса к LLM (trace-логи для дебага)
            logger.debug(f"LLM Request: Model={self.model}, Temperature={temperature}")
            logger.debug(f"Context messages count: {len(messages)}")
            for i, msg in enumerate(messages, 1):
                role = msg.get('role', 'unknown')
                content = msg.get('content', '')
                # Обрезаем очень длинный контент для читаемости
                display_content = content[:200] + "..." if len(content) > 200 else content
                logger.debug(f"Message {i} [{role.upper()}]: {display_content}")
            if response_format:
                logger.debug(f"Response format specified: {response_format.get('type')}")
            
            response = requests.post(self.base_url, headers=headers, json=data, timeout=30)
            response.raise_for_status()
            
            result = response.json()
            if 'choices' not in result or not result['choices']:
                raise Exception("Пустой ответ от API")
            
            # Получаем ответ
            response_content = result['choices'][0]['message']['content']
            
            # Детальное логирование ответа от LLM (trace-логи для дебага)
            display_response = response_content[:300] + "..." if len(response_content) > 300 else response_content
            logger.debug(f"LLM Response: {display_response}")
            
            # Создаем полную запись об ответе
            response_info = {
                "response_content": response_content,
                "response_length": len(response_content),
                "finish_reason": result['choices'][0].get('finish_reason', 'unknown'),
                "usage": result.get('usage', {}),
                "raw_api_response": result
            }
            
            # Попробуем распарсить JSON, если запрашивали json_schema
            if isinstance(response_format, dict) and response_format.get("type") == "json_schema":
                try:
                    response_info["parsed_json"] = json.loads(response_content)
                except Exception:
                    response_info["parsed_json_error"] = "Failed to parse JSON content"
            
            # Логируем информацию о токенах
            if 'usage' in result:
                usage = result['usage']
                prompt_tokens = usage.get('prompt_tokens', 0)
                completion_tokens = usage.get('completion_tokens', 0)
                total_tokens = usage.get('total_tokens', 0)
                
                logger.info(f"LLM API completed - Model: {self.model}, Tokens: {prompt_tokens}+{completion_tokens}={total_tokens}")
            else:
                logger.warning("Token usage information not received from API")
            
            # Возвращаем полную информацию
            return {
                "request": request_info,
                "response": response_info,
                "success": True,
                "error": None
            }
                
        except requests.exceptions.Timeout:
            error_msg = "Превышено время ожидания ответа от API"
            return {
                "request": request_info if 'request_info' in locals() else {},
                "response": None,
                "success": False,
                "error": error_msg
            }
        except requests.exceptions.RequestException as e:
            error_msg = f"Ошибка сети: {str(e)}"
            return {
                "request": request_info if 'request_info' in locals() else {},
                "response": None,
                "success": False,
                "error": error_msg
            }
        except json.JSONDecodeError:
            error_msg = "Неверный формат ответа от API"
            return {
                "request": request_info if 'request_info' in locals() else {},
                "response": None,
                "success": False,
                "error": error_msg
            }
        except Exception as e:
            error_msg = f"Ошибка API: {str(e)}"
            return {
                "request": request_info if 'request_info' in locals() else {},
                "response": None,
                "success": False,
                "error": error_msg
            }
    
    def _extract_content_from_detailed_response(self, detailed_response):
        
        if detailed_response.get("success") and detailed_response.get("response"):
            return detailed_response["response"]["response_content"]
        else:
            error_msg = detailed_response.get("error", "Неизвестная ошибка")
            raise Exception(error_msg)
    
    def generate_primary_response(self, user_message, chat_history):
        
        messages = []
        
        # Добавляем историю чата
        for msg in chat_history:
            messages.append({
                "role": msg.role,
                "content": msg.content
            })
        
        # Добавляем текущее сообщение пользователя
        messages.append({
            "role": "user",
            "content": user_message
        })
        
        detailed_response = self._make_request(
            messages, 
            stage_info="Standard generation",
            prompt_info="Primary response generation"
        )
        return self._extract_content_from_detailed_response(detailed_response)
    
    def generate_response(self, user_message, chat_history=None, stage_info=None, prompt_info=None):
        """
        Генерирует ответ с поддержкой детальной информации.
        
        Args:
            user_message: Сообщение пользователя
            chat_history: История чата (опционально)
            stage_info: Информация о стадии для детального логирования
            prompt_info: Информация о промпте для детального логирования
            
        Returns:
            str: Текст ответа (для обратной совместимости)
        """
        if chat_history is None:
            chat_history = []
        return self.generate_primary_response(user_message, chat_history)
    
    def generate_response_detailed(self, user_message, chat_history=None, stage_info=None, prompt_info=None):
        """
        Генерирует ответ с полной детальной информацией.
        
        Args:
            user_message: Сообщение пользователя
            chat_history: История чата (опционально)
            stage_info: Информация о стадии для детального логирования
            prompt_info: Информация о промпте для детального логирования
            
        Returns:
            dict: Полная информация о запросе и ответе
        """
        if chat_history is None:
            chat_history = []
            
        messages = [
            {
                "role": "user",
                "content": user_message
            }
        ]
        
        return self._make_request(
            messages, 
            stage_info=stage_info or "Standard generation",
            prompt_info=prompt_info or user_message[:100] + "..." if len(user_message) > 100 else user_message
        )
    
    def remove_fluff(self, original_response, user_question):
        
        messages = [
            {
                "role": "system",
                "content": "Ты редактор текста. Убери из ответа лишнюю воду, оставь только суть. Сохрани полезную информацию, но сделай текст более кратким и точным."
            },
            {
                "role": "user",
                "content": f"Исходный вопрос: {user_question}\n\nОтвет для редактирования: {original_response}"
            }
        ]
        
        detailed_response = self._make_request(
            messages, 
            temperature=0.3,
            stage_info="Этап 2: Убираю лишнюю информацию",
            prompt_info="Remove fluff from response"
        )
        return self._extract_content_from_detailed_response(detailed_response)
    
    def verify_relevance(self, edited_response, user_question):
        
        messages = [
            {
                "role": "system",
                "content": "Проверь, отвечает ли данный текст на вопрос пользователя. Если да, верни текст как есть. Если нет, исправь его так, чтобы он точно отвечал на вопрос."
            },
            {
                "role": "user",
                "content": f"Вопрос: {user_question}\n\nОтвет: {edited_response}"
            }
        ]
        
        try:
            detailed_response = self._make_request(
                messages, 
                temperature=0.2,
                stage_info="Этап 3: Проверяю соответствие ответа",
                prompt_info="Verify response relevance"
            )
            return self._extract_content_from_detailed_response(detailed_response)
        except Exception:
            # Если проверка не удалась, возвращаем отредактированный ответ
            return edited_response

    # === Новая функциональность: поддержка JSON Schema в запросах ===
    def generate_with_json_schema(self, *, system_rules: str, user_payload: dict, json_schema: dict, previous_assistant: str = "", temperature: float = 0.7, stage_info: str | None = None, prompt_info: str | None = None):
        """
        Выполняет запрос с жесткой структурой сообщений и требованием ответа по JSON Schema.

        Пример использования:
            detailed = self.generate_with_json_schema(
                system_rules="Rules: output JSON matching schema; do not invent facts; label file refs as <<file:name>>.",
                user_payload={"user_query": "Сделай TL;DR и список задач", "files": [{"name": "report.txt", "summary": "20-стр. отчет — ключевые метрики на стр.2-4", "ref": "<<file:report.txt>>"}], "max_tokens": 800},
                json_schema={"type": "object", "properties": {"summary": {"type": "string"}, "tasks": {"type": "array", "items": {"type": "string"}}}, "required": ["summary"]}
            )

        Возвращает детальную структуру так же, как _make_request().
        """
        messages = [
            {"role": "system", "content": system_rules.strip()},
            {"role": "user", "content": json.dumps(user_payload, ensure_ascii=False)}
        ]
        if previous_assistant:
            messages.append({"role": "assistant", "content": previous_assistant})

        response_format = {"type": "json_schema", "json_schema": json_schema}

        return self._make_request(
            messages,
            temperature=temperature,
            stage_info=stage_info or "JSON schema generation",
            prompt_info=prompt_info or "Structured JSON output",
            response_format=response_format,
        )