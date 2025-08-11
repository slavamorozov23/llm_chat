import json
import asyncio
import logging
from typing import Dict, List, Any
from concurrent.futures import ThreadPoolExecutor
from .openrouter_service import OpenRouterService

logger = logging.getLogger(__name__)


class StructuredPromptHandler:
    """
    Обработчик структурированных промптов с стандартизированной разметкой.
    
    СТАНДАРТЫ РАЗМЕТКИ:
    ==================
    
    Следуем стандартам OpenAI/OpenRouter для структурирования данных:
    - system: правила, инструкции, схема ответа
    - user: JSON-пейлоад с данными пользователя, контекстом, файлами
    - assistant: предыдущие ответы (опционально)
    - response_format: JSON Schema для строгого форматирования ответа
    
    ПРИМЕР СТАНДАРТНОЙ РАЗМЕТКИ:
    ============================
    
    {
        "messages": [
            {
                "role": "system",
                "content": "Rules: output JSON matching schema; do not invent facts; label file refs as <<file:name>>."
            },
            {
                "role": "user", 
                "content": {
                    "user_query": "Сделай TL;DR и список задач",
                    "context": "Результаты предыдущих этапов...",
                    "files": [
                        {
                            "name": "report.txt",
                            "summary": "20-стр. отчет — ключевые метрики на стр.2-4",
                            "ref": "<<file:report.txt>>"
                        }
                    ],
                    "max_tokens": 800
                }
            }
        ],
        "json_schema": {
            "type": "object",
            "properties": {
                "summary": {"type": "string"},
                "tasks": {"type": "array", "items": {"type": "string"}}
            },
            "required": ["summary"]
        }
    }
    """
    
    def __init__(self):
        self.openrouter = OpenRouterService()
        self.executor = ThreadPoolExecutor(max_workers=3)
    
    def _compose_standard_messages(self, prompt_item: Dict, context: str) -> List[Dict]:
        """
        Создает стандартизированные сообщения согласно OpenAI/OpenRouter формату.
        
        Args:
            prompt_item: Конфигурация промпта с messages и опциональной json_schema
            context: Контекст для подстановки
            
        Returns:
            List[Dict]: Стандартизированные сообщения для API
        """
        messages = []
        
        for message in prompt_item["messages"]:
            content = message["content"]
            
            if isinstance(content, str):
                # Простая строка - подставляем контекст напрямую
                content = content.replace("{context}", context)
                messages.append({
                    "role": message["role"],
                    "content": content
                })
            
            elif isinstance(content, dict):
                # JSON объект - подставляем контекст в соответствующие поля
                processed_content = self._inject_context_into_payload(content.copy(), context)
                
                # Если контекст был внедрен как массив messages и это роль user
                # Сериализуем в JSON, только если это не поле messages
                if "messages" in processed_content and isinstance(processed_content["messages"], list):
                    # Для полей messages оставляем их как список (не сериализуем в JSON)
                    messages.append({
                        "role": message["role"],
                        "content": processed_content
                    })
                else:
                    # Обычная сериализация для остальных случаев
                    messages.append({
                        "role": message["role"],
                        "content": json.dumps(processed_content, ensure_ascii=False)
                    })
            
            else:
                # Неожиданный тип - логируем и передаем как есть
                logger.warning(f"Unexpected content type: {type(content)} in message role {message['role']}")
                messages.append({
                    "role": message["role"],
                    "content": str(content)
                })
        
        return messages
    
    def _inject_context_into_payload(self, payload: Dict, context) -> Dict:
        """
        Внедряет контекст в JSON-пейлоад пользователя.
        
        Ищет поля 'context', 'previous_results', 'stage_context', 'messages'
        и заменяет их значения или добавляет контекст.
        
        Args:
            context: Может быть строкой (старый формат) или List[Dict] (новый формат messages)
        """
        # Если контекст это массив сообщений - используем новый формат
        if isinstance(context, list) and len(context) > 0 and isinstance(context[0], dict):
            # Если есть поле messages - заменяем его
            if "messages" in payload:
                payload["messages"] = context
            # Если есть поле context - заменяем
            elif "context" in payload:
                payload["context"] = context
            # Если есть поле stage_context - заменяем
            elif "stage_context" in payload:
                payload["stage_context"] = context
            # Если нет специальных полей - добавляем messages
            else:
                payload["messages"] = context
                
        # Старая логика для строкового контекста (обратная совместимость)
        else:
            context_str = str(context) if context else ""
            # Если есть поле context - заменяем его
            if "context" in payload:
                payload["context"] = context_str
            
            # Если есть поле previous_results - дополняем его
            elif "previous_results" in payload:
                if payload["previous_results"]:
                    payload["previous_results"] += f"\n\n{context_str}"
                else:
                    payload["previous_results"] = context_str
            
            # Если есть поле stage_context - заменяем
            elif "stage_context" in payload:
                payload["stage_context"] = context_str
            
            # Если нет специальных полей - добавляем context
            else:
                payload["context"] = context_str
        
        return payload
    
    async def execute_structured_prompt(self, prompt_item: Dict, context: str, stage_info: str = None, prompt_info: str = None) -> str:
        """
        Выполняет структурированный промпт с стандартной разметкой.
        
        Args:
            prompt_item: Конфигурация промпта с messages и опциональной json_schema
            context: Контекст для подстановки
            stage_info: Информация об этапе для логирования
            prompt_info: Информация о промпте для логирования
            
        Returns:
            str: Текст ответа от LLM
            
        Raises:
            Exception: При ошибках генерации
        """
        # Формируем стандартизированные сообщения
        messages = self._compose_standard_messages(prompt_item, context)
        
        # Извлекаем параметры запроса
        temperature = prompt_item.get("temperature", 0.7)
        response_format = None
        
        if "json_schema" in prompt_item:
            response_format = {
                "type": "json_schema",
                "json_schema": prompt_item["json_schema"]
            }
        
        # Выполняем асинхронный запрос
        loop = asyncio.get_event_loop()
        
        detailed_response = await loop.run_in_executor(
            self.executor,
            lambda: self.openrouter._make_request(
                messages=messages,
                temperature=temperature,
                response_format=response_format,
                stage_info=stage_info or "Structured generation",
                prompt_info=prompt_info or "Standardized message format"
            )
        )
        
        # Извлекаем результат
        if detailed_response.get("success") and detailed_response.get("response"):
            return detailed_response["response"]["response_content"]
        else:
            error_msg = detailed_response.get("error", "Неизвестная ошибка")
            raise Exception(f"Ошибка структурированной генерации: {error_msg}")
    
    async def execute_structured_prompt_detailed(self, prompt_item: Dict, context: str, stage_info: str = None, prompt_info: str = None) -> Dict:
        """
        Выполняет структурированный промпт с полной детальной информацией.
        
        Returns:
            Dict: Полная детальная информация от OpenRouterService
        """
        # Формируем стандартизированные сообщения
        messages = self._compose_standard_messages(prompt_item, context)
        
        # Извлекаем параметры запроса
        temperature = prompt_item.get("temperature", 0.7)
        response_format = None
        
        if "json_schema" in prompt_item:
            response_format = {
                "type": "json_schema", 
                "json_schema": prompt_item["json_schema"]
            }
        
        # Выполняем асинхронный запрос
        loop = asyncio.get_event_loop()
        
        detailed_response = await loop.run_in_executor(
            self.executor,
            lambda: self.openrouter._make_request(
                messages=messages,
                temperature=temperature,
                response_format=response_format,
                stage_info=stage_info or "Structured generation (detailed)",
                prompt_info=prompt_info or "Standardized message format (detailed)"
            )
        )
        
        return detailed_response
    
    def cleanup(self):
        """Освобождает ресурсы executor-а."""
        if hasattr(self, 'executor'):
            self.executor.shutdown(wait=True)