import asyncio
import logging
from typing import Dict, List, Any
from asgiref.sync import sync_to_async

from .config_manager import ConfigManager
from .context_manager import ContextManager
from .generation_executor import GenerationExecutor
from .openrouter_service import OpenRouterService

# Настройка логгера
logger = logging.getLogger(__name__)


class StagedGenerationService:
    
    
    def __init__(self):
        self.openrouter = OpenRouterService()
        self.config_manager = ConfigManager()
        self.context_manager = ContextManager()
        self.generation_executor = GenerationExecutor()
    
    def get_active_config(self, user) -> Dict[str, Any] | None:
        
        return self.config_manager.get_active_config(user)
    
    async def get_active_config_async(self, user) -> Dict[str, Any] | None:
        
        return await sync_to_async(self.get_active_config)(user)
    
    def validate_config(self, config_data: Dict[str, Any]) -> bool:
        
        return self.config_manager.validate_config(config_data)
    
    async def generate_staged_response(self, user_message: str, user, status_callback=None) -> str:
        
        config = await self.get_active_config_async(user)
        
        if not config or not self.validate_config(config):
            # Если нет конфигурации, используем обычную генерацию
            logger.info("Нет активной конфигурации поэтапной генерации, используем обычную генерацию")
            return await sync_to_async(self.openrouter.generate_response)(user_message)
        
        try:
            # Получаем этапы в порядке их определения (Python 3.7+ сохраняет порядок dict)
            stage_names = list(config.keys())
            logger.info(f"Начинаем поэтапную генерацию: {len(stage_names)} этапов")
            
            # Контекст для накопления результатов между этапами
            context_history = []
            stage_results = {}
            
            # Получаем и очищаем сохраненный контекст для этого пользователя
            user_id = str(user.id)
            saved_context_data = self.context_manager.clear_saved_context(user_id)
            
            # Новый контекст для сохранения в этой генерации
            new_saved_context = []
            
            for i, stage_name in enumerate(stage_names, 1):
                stage_prompts = config[stage_name]
                
                # Обновляем статус через callback
                if status_callback:
                    status_text = f"Этап {i}: {stage_name}"
                    await sync_to_async(status_callback)(status_text, i)
                
                # Подготавливаем контекст с результатами предыдущих этапов и сохраненным контекстом
                stage_context = self.context_manager.prepare_stage_context(
                    user_message, 
                    context_history, 
                    stage_results,
                    saved_context_data
                )
                
                # Выполняем промпты этапа асинхронно и независимо друг от друга
                stage_responses, stage_saved_context = await self.generation_executor.execute_stage_prompts(
                    stage_prompts, 
                    stage_context
                )
                
                # Сохраняем результаты этапа для следующих этапов
                stage_results[stage_name] = stage_responses
                context_history.extend(stage_responses)
                
                # Добавляем контекст для сохранения на следующую генерацию
                new_saved_context.extend(stage_saved_context)
            
            # Сохраняем новый контекст для следующей генерации
            self.context_manager.save_context(user_id, new_saved_context)
            
            # Возвращаем результат последнего этапа
            final_stage = stage_names[-1]
            final_responses = stage_results[final_stage]
            
            # Если в финальном этапе несколько ответов, объединяем их
            if len(final_responses) == 1:
                return final_responses[0]
            else:
                return "\n\n".join(final_responses)
                
        except Exception as e:
            print(f"Ошибка поэтапной генерации: {e}")
            # В случае ошибки возвращаем обычную генерацию
            return await sync_to_async(self.openrouter.generate_response)(user_message)
    

    
    def create_config(self, user, name: str, config_data: Dict[str, Any]):
        
        return self.config_manager.create_config(user, name, config_data)
    
    def activate_config(self, user, config_name: str) -> bool:
        
        return self.config_manager.activate_config(user, config_name)
    
    def deactivate_all_configs(self, user) -> None:
        
        self.config_manager.deactivate_all_configs(user)