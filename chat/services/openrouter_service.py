import requests
import json
import logging
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
    
    def _make_request(self, messages, temperature=0.7):
        
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
            
            response = requests.post(self.base_url, headers=headers, json=data, timeout=30)
            response.raise_for_status()
            
            result = response.json()
            if 'choices' not in result or not result['choices']:
                raise Exception("Пустой ответ от API")
            
            # Логируем информацию о токенах
            if 'usage' in result:
                usage = result['usage']
                prompt_tokens = usage.get('prompt_tokens', 0)
                completion_tokens = usage.get('completion_tokens', 0)
                total_tokens = usage.get('total_tokens', 0)
                
                logger.info(f"OpenRouter API запрос завершен:")
                logger.info(f"  - Токены на входе: {prompt_tokens}")
                logger.info(f"  - Токены на выходе: {completion_tokens}")
                logger.info(f"  - Всего токенов: {total_tokens}")
                logger.info(f"  - Модель: {self.model}")
            else:
                logger.warning("Информация о токенах не получена от API")
                
            return result
            
        except requests.exceptions.Timeout:
            raise Exception("Превышено время ожидания ответа от API")
        except requests.exceptions.RequestException as e:
            raise Exception(f"Ошибка сети: {str(e)}")
        except json.JSONDecodeError:
            raise Exception("Неверный формат ответа от API")
        except Exception as e:
            raise Exception(f"Ошибка API: {str(e)}")
    
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
        
        response = self._make_request(messages)
        return response['choices'][0]['message']['content']
    
    def generate_response(self, user_message, chat_history=None):
        
        if chat_history is None:
            chat_history = []
        return self.generate_primary_response(user_message, chat_history)
    
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
        
        response = self._make_request(messages, temperature=0.3)
        return response['choices'][0]['message']['content']
    
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
            response = self._make_request(messages, temperature=0.2)
            return response['choices'][0]['message']['content']
        except Exception:
            # Если проверка не удалась, возвращаем отредактированный ответ
            return edited_response