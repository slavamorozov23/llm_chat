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
    
    def validate_config(self, config_data: Dict[str, Any]) -> bool:
        
        try:
            if not isinstance(config_data, dict):
                logger.error("Конфигурация не является словарем")
                return False
            
            if len(config_data) == 0:
                logger.error("Конфигурация пустая")
                return False
            
            # Проверяем структуру каждого этапа
            for stage_name, stage_data in config_data.items():
                if not isinstance(stage_data, list):
                    logger.error(f"Этап {stage_name} не является списком")
                    return False
                
                if len(stage_data) == 0:
                    logger.error(f"Этап {stage_name} не может быть пустым")
                    return False
                
                for i, prompt_item in enumerate(stage_data):
                    if not isinstance(prompt_item, dict) or 'prompt' not in prompt_item:
                        logger.error(f"Промпт {i} в этапе {stage_name} имеет неверную структуру")
                        return False
            
            return True
        except Exception as e:
            logger.error(f"Ошибка при валидации конфигурации: {e}")
            return False
    
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