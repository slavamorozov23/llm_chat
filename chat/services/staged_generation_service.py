import asyncio
import logging
from typing import Dict, List, Any, Tuple
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
                
                if status_callback:
                    status_text = f"Этап {i}: {stage_name}"
                    await sync_to_async(status_callback)(status_text, i)
                
                stage_context = self.context_manager.prepare_stage_context(
                    user_message, 
                    context_history, 
                    stage_results,
                    saved_context_data
                )
                
                # stage_responses_data - это список словарей
                stage_responses_data, stage_saved_context = await self.generation_executor.execute_stage_prompts(
                    stage_prompts, 
                    stage_context
                )
                
                # Фильтруем ответы, которые не должны идти в межэтапный контекст
                responses_for_next_stage = [
                    item['response_text'] for item in stage_responses_data 
                    if not item.get('block_outside_context', False)
                ]
                
                # Все ответы этапа (только текст) сохраняем для возможного финального вывода
                all_stage_response_texts = [item['response_text'] for item in stage_responses_data]
                
                stage_results[stage_name] = all_stage_response_texts
                context_history.extend(responses_for_next_stage) # В историю добавляем только разрешенные
                
                new_saved_context.extend(stage_saved_context)
            
            self.context_manager.save_context(user_id, new_saved_context)
            
            final_stage = stage_names[-1]
            final_responses = stage_results[final_stage]
            
            if len(final_responses) == 1:
                return final_responses[0]
            else:
                return "\n\n".join(final_responses)
                
        except Exception as e:
            logger.error(f"Ошибка поэтапной генерации: {e}")
            # В случае ошибки возвращаем обычную генерацию
            return await sync_to_async(self.openrouter.generate_response)(user_message)
    

    
    async def generate_staged_response_detailed(self, user_message: str, user, status_callback=None) -> Tuple[str, List[Dict[str, Any]]]:
        """
        Выполняет поэтапную генерацию с детальным логированием каждого запроса к LLM.
        Возвращает финальный ответ и список данных по этапам с полными детальными ответами.
        """
        config = await self.get_active_config_async(user)
        
        # Если нет конфигурации, выполняем один детальный запрос, чтобы в raw_response были полные данные
        if not config or not self.validate_config(config):
            try:
                detailed = await sync_to_async(self.openrouter.generate_response_detailed)(
                    user_message,
                    None,
                    "Standard generation",
                    "Primary response generation"
                )
                if detailed.get('success') and detailed.get('response'):
                    final_text = detailed['response']['response_content']
                else:
                    final_text = await sync_to_async(self.openrouter.generate_response)(user_message)
                staged_data = [{
                    "stage_name": "Standard generation",
                    "detailed_responses": [detailed]
                }]
                return final_text, staged_data
            except Exception as e:
                logger.error(f"Fallback detailed generation error: {e}")
                final_text = await sync_to_async(self.openrouter.generate_response)(user_message)
                return final_text, []
        
        try:
            stage_names = list(config.keys())
            context_history: List[str] = []
            stage_results: Dict[str, List[str]] = {}
            user_id = str(user.id)
            saved_context_data = self.context_manager.clear_saved_context(user_id)
            new_saved_context: List[Dict] = []
            staged_detailed_data: List[Dict[str, Any]] = []
            
            for i, stage_name in enumerate(stage_names, 1):
                stage_prompts = config[stage_name]
                if status_callback:
                    status_text = f"Этап {i}: {stage_name}"
                    await sync_to_async(status_callback)(status_text, i)
                
                stage_context = self.context_manager.prepare_stage_context(
                    user_message,
                    context_history,
                    stage_results,
                    saved_context_data
                )
                
                responses_data, stage_saved_context, detailed_responses = await self.generation_executor.execute_stage_prompts_detailed(
                    stage_prompts,
                    stage_context,
                    stage_name
                )
                
                responses_for_next_stage = [
                    item['response_text'] for item in responses_data
                    if not item.get('block_outside_context', False)
                ]
                all_stage_response_texts = [item['response_text'] for item in responses_data]
                stage_results[stage_name] = all_stage_response_texts
                context_history.extend(responses_for_next_stage)
                new_saved_context.extend(stage_saved_context)
                
                staged_detailed_data.append({
                    "stage_name": stage_name,
                    "detailed_responses": detailed_responses
                })
            
            self.context_manager.save_context(user_id, new_saved_context)
            final_stage = stage_names[-1]
            final_responses = stage_results[final_stage]
            if len(final_responses) == 1:
                final_response = final_responses[0]
            else:
                final_response = "\n\n".join(final_responses)
            return final_response, staged_detailed_data
        except Exception as e:
            logger.error(f"Ошибка поэтапной генерации (детально): {e}")
            # Пытаемся вернуть детальный лог хотя бы одного стандартного запроса
            try:
                detailed = await sync_to_async(self.openrouter.generate_response_detailed)(
                    user_message,
                    None,
                    "Fallback standard generation",
                    "Direct user request"
                )
                if detailed.get('success') and detailed.get('response'):
                    final_text = detailed['response']['response_content']
                else:
                    final_text = await sync_to_async(self.openrouter.generate_response)(user_message)
                staged_data = [{
                    "stage_name": "Fallback standard generation",
                    "detailed_responses": [detailed]
                }]
                return final_text, staged_data
            except Exception as inner_e:
                logger.error(f"Fallback detailed generation failed: {inner_e}")
                final_text = await sync_to_async(self.openrouter.generate_response)(user_message)
                return final_text, []
    
    
    def create_config(self, user, name: str, config_data: Dict[str, Any]):
        
        return self.config_manager.create_config(user, name, config_data)
    
    def activate_config(self, user, config_name: str) -> bool:
        
        return self.config_manager.activate_config(user, config_name)
    
    def deactivate_all_configs(self, user) -> None:
        
        self.config_manager.deactivate_all_configs(user)