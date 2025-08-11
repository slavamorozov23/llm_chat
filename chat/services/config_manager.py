import json
import logging
from typing import Dict, Any
from ..models import StagedGenerationConfig

# Настройка логгера
logger = logging.getLogger(__name__)


class ConfigManager:
    """
    Менеджер конфигураций поэтапной генерации.
    
    НАЗНАЧЕНИЕ И АРХИТЕКТУРА:
    =========================
    
    Этот модуль выделен из StagedGenerationService для управления конфигурациями
    поэтапной генерации. Отвечает за:
    - Создание новых конфигураций
    - Валидацию структуры конфигураций
    - Активацию/деактивацию конфигураций
    - Получение активной конфигурации для пользователя
    
    СТРУКТУРА КОНФИГУРАЦИИ:
    =======================
    
    Конфигурация представляет собой JSON со следующей структурой:
    {
        "stage_name1": [
            {
                "prompt": "Текст промпта с переменными {user_message}, {stage_name_results}",
                "saveLastAsContext": true/false  // опционально
            },
            // ... другие промпты этого этапа (выполняются параллельно)
        ],
        "stage_name2": [
            // ... промпты следующего этапа
        ]
    }
    
    ПРИНЦИПЫ РАБОТЫ:
    ================
    
    1. Каждый пользователь может иметь только одну активную конфигурацию
    2. При активации новой конфигурации все предыдущие деактивируются
    3. Валидация проверяет структуру JSON и наличие обязательных полей
    4. saveLastAsContext работает только в рамках одной генерации
    
    НЕ УДАЛЯТЬ ЭТИ КОММЕНТАРИИ! Они содержат критически важную информацию
    об архитектуре системы поэтапной генерации.
    """
    
    def get_active_config(self, user) -> Dict[str, Any] | None:
        
        try:
            config = StagedGenerationConfig.objects.filter(
                user=user, 
                is_active=True
            ).first()
            
            if config:
                logger.info(f"Найдена активная конфигурация: {config.name}")
                
                # Если данные пришли как строка, парсим JSON
                if isinstance(config.config_data, str):
                    try:
                        return json.loads(config.config_data)
                    except json.JSONDecodeError as e:
                        logger.error(f"Ошибка парсинга JSON: {e}")
                        return None
                else:
                    return config.config_data
            else:
                return None
                
        except Exception as e:
            logger.error(f"Ошибка при получении активной конфигурации: {e}")
            return None
    
    def validate_config(self, config: Dict[str, Any]) -> bool:
        """
        Валидирует структуру конфигурации.
        
        Поддерживаемые форматы:
        1. Классический формат с простыми промптами
        2. Структурированный формат с ролями и JSON Schema
        
        Returns:
            bool: True если конфигурация корректная
        """
        if not isinstance(config, dict):
            logger.error("Config must be a dictionary")
            return False
            
        if len(config) == 0:
            logger.error("Config cannot be empty")
            return False
        
        for stage_name, stage_prompts in config.items():
            if not isinstance(stage_name, str):
                logger.error(f"Stage name must be string, got: {type(stage_name)}")
                return False
                
            if not isinstance(stage_prompts, list):
                logger.error(f"Stage {stage_name} must be a list")
                return False
                
            if len(stage_prompts) == 0:
                logger.error(f"Stage {stage_name} cannot be empty")
                return False
            
            for i, prompt_item in enumerate(stage_prompts):
                if not isinstance(prompt_item, dict):
                    logger.error(f"Prompt item in stage {stage_name}[{i}] must be a dictionary")
                    return False
                
                # Проверяем, какой формат используется
                if "messages" in prompt_item:
                    # Структурированный формат
                    if not self._validate_structured_prompt(prompt_item, stage_name, i):
                        return False
                else:
                    # Классический формат
                    if not self._validate_classic_prompt(prompt_item, stage_name, i):
                        return False
        
        logger.info("Config validation passed")
        return True
    
    def _validate_classic_prompt(self, prompt_item: Dict, stage_name: str, index: int) -> bool:
        """Валидация классического формата промпта."""
        if "prompt" not in prompt_item:
            logger.error(f"Stage {stage_name}[{index}] missing required 'prompt' field")
            return False
            
        if not isinstance(prompt_item["prompt"], str):
            logger.error(f"Stage {stage_name}[{index}] 'prompt' must be string")
            return False
        
        # Проверяем опциональные поля
        optional_fields = {
            "saveLastAsContext": bool,
            "blockOutsideInterstageContext": bool,
            "step-by-stepRequest": bool
        }
        
        for field, expected_type in optional_fields.items():
            if field in prompt_item and not isinstance(prompt_item[field], expected_type):
                logger.error(f"Stage {stage_name}[{index}] '{field}' must be {expected_type.__name__}")
                return False
        
        return True
    
    def _validate_structured_prompt(self, prompt_item: Dict, stage_name: str, index: int) -> bool:
        """Валидация структурированного формата промпта."""
        required_fields = ["messages"]
        for field in required_fields:
            if field not in prompt_item:
                logger.error(f"Stage {stage_name}[{index}] missing required field '{field}' for structured format")
                return False
        
        # Валидация messages
        messages = prompt_item["messages"]
        if not isinstance(messages, list) or len(messages) == 0:
            logger.error(f"Stage {stage_name}[{index}] 'messages' must be non-empty list")
            return False
        
        valid_roles = {"system", "user", "assistant"}
        for msg_idx, message in enumerate(messages):
            if not isinstance(message, dict):
                logger.error(f"Stage {stage_name}[{index}] message {msg_idx} must be dictionary")
                return False
            
            if "role" not in message or "content" not in message:
                logger.error(f"Stage {stage_name}[{index}] message {msg_idx} must have 'role' and 'content'")
                return False
            
            if message["role"] not in valid_roles:
                logger.error(f"Stage {stage_name}[{index}] message {msg_idx} role must be one of {valid_roles}")
                return False
            
            if not isinstance(message["content"], str):
                logger.error(f"Stage {stage_name}[{index}] message {msg_idx} content must be string")
                return False
        
        # Валидация опциональной JSON схемы
        if "json_schema" in prompt_item:
            schema = prompt_item["json_schema"]
            if not isinstance(schema, dict):
                logger.error(f"Stage {stage_name}[{index}] 'json_schema' must be dictionary")
                return False
            
            # Базовая проверка структуры JSON Schema
            if "type" not in schema:
                logger.error(f"Stage {stage_name}[{index}] JSON schema must have 'type' field")
                return False
        
        # Валидация опциональных параметров
        optional_fields = {
            "temperature": (int, float),
            "saveLastAsContext": bool,
            "blockOutsideInterstageContext": bool,
            "step-by-stepRequest": bool
        }
        
        for field, expected_types in optional_fields.items():
            if field in prompt_item:
                if isinstance(expected_types, tuple):
                    if not isinstance(prompt_item[field], expected_types):
                        logger.error(f"Stage {stage_name}[{index}] '{field}' must be one of {expected_types}")
                        return False
                else:
                    if not isinstance(prompt_item[field], expected_types):
                        logger.error(f"Stage {stage_name}[{index}] '{field}' must be {expected_types.__name__}")
                        return False
        
        return True

    def create_config(self, user, name: str, config_data: Dict[str, Any]) -> StagedGenerationConfig:
        
        if not self.validate_config(config_data):
            raise ValueError("Неверная структура конфигурации")
        
        config = StagedGenerationConfig.objects.create(
            user=user,
            name=name,
            config_data=config_data,
            is_active=False
        )
        
        return config
    
    def activate_config(self, user, config_name: str) -> bool:
        
        try:
            config = StagedGenerationConfig.objects.get(
                user=user,
                name=config_name
            )
            config.is_active = True
            config.save()
            return True
        except StagedGenerationConfig.DoesNotExist:
            return False
    
    def deactivate_all_configs(self, user) -> None:
        
        StagedGenerationConfig.objects.filter(
            user=user,
            is_active=True
        ).update(is_active=False)