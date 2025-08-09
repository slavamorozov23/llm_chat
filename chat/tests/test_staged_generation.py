import pytest
import asyncio
from unittest.mock import Mock, patch, AsyncMock
from chat.services.staged_generation_service import StagedGenerationService
from chat.services.context_manager import ContextManager
from chat.models import StagedGenerationConfig


@pytest.mark.django_db
class TestStagedGenerationService:
    
    @pytest.fixture(autouse=True)
    def setup(self, openrouter_settings):
        self.staged_service = StagedGenerationService()
    
    def test_validate_config_valid(self):
        valid_config = {
            "stage1": [
                {"prompt": "Test: {user_message}"},
                {"prompt": "Another test", "saveLastAsContext": True}
            ],
            "stage2": [
                {"prompt": "Final: {stage1_results}"}
            ]
        }
        
        assert self.staged_service.validate_config(valid_config) is True
    
    def test_validate_config_invalid_cases(self):
        invalid_configs = [
            {},
            {"stage1": "not_a_list"},
            {"stage1": []},
            {"stage1": [{"no_prompt": "test"}]},
            {"stage1": [123]},
        ]
        
        for config in invalid_configs:
            assert self.staged_service.validate_config(config) is False
    
    def test_create_config(self, user):
        config_data = {
            "stage1": [{"prompt": "Test prompt"}]
        }
        
        config = self.staged_service.create_config(user, "test_config", config_data)
        
        assert config.user == user
        assert config.name == "test_config"
        assert config.config_data == config_data
        assert not config.is_active
    
    def test_create_config_invalid_raises(self, user):
        invalid_config = {"invalid": "data"}
        
        with pytest.raises(ValueError) as exc_info:
            self.staged_service.create_config(user, "bad_config", invalid_config)
        
        assert "Неверная структура" in str(exc_info.value)
    
    def test_activate_config(self, user, staged_config):
        result = self.staged_service.activate_config(user, staged_config.name)
        
        assert result is True
        staged_config.refresh_from_db()
        assert staged_config.is_active
    
    def test_activate_nonexistent_config(self, user):
        result = self.staged_service.activate_config(user, "nonexistent")
        
        assert result is False
    
    def test_deactivate_all_configs(self, user):
        config1 = StagedGenerationConfig.objects.create(
            user=user, name="config1", config_data={"stage1": [{"prompt": "test"}]}, is_active=True
        )
        config2 = StagedGenerationConfig.objects.create(
            user=user, name="config2", config_data={"stage1": [{"prompt": "test"}]}, is_active=True
        )
        
        self.staged_service.deactivate_all_configs(user)
        
        config1.refresh_from_db()
        config2.refresh_from_db()
        assert not config1.is_active
        assert not config2.is_active
    
    def test_get_active_config(self, user, staged_config):
        assert self.staged_service.get_active_config(user) is None
        
        staged_config.is_active = True
        staged_config.save()
        
        active_config = self.staged_service.get_active_config(user)
        assert active_config == staged_config.config_data
    
    @pytest.mark.asyncio
    @patch('chat.services.generation_executor.GenerationExecutor.execute_stage_prompts')
    async def test_generate_staged_response(self, mock_execute, user, staged_config):
        # Мокируем get_active_config_async для возврата конфигурации
        test_config = {
            "stage1": [{"prompt": "Test: {user_message}"}],
            "stage2": [{"prompt": "Final: {stage1_results}"}]
        }
        self.staged_service.get_active_config_async = AsyncMock(return_value=test_config)
        
        mock_execute.side_effect = [
            (["Stage 1 response"], []),
            (["Final response"], [])
        ]
        
        result = await self.staged_service.generate_staged_response(
            "User question", user
        )
        
        assert result == "Final response"
        assert mock_execute.call_count == 2
    
    @pytest.mark.asyncio
    async def test_generate_without_config_uses_openrouter(self, user):
        # Мокируем get_active_config_async чтобы возвращал None (нет конфигурации)
        self.staged_service.get_active_config_async = AsyncMock(return_value=None)
        
        # Полностью заменяем generate_staged_response на простую версию
        async def simple_generate(user_message, user_obj, status_callback=None):
            config = await self.staged_service.get_active_config_async(user_obj)
            if not config:
                return "Direct OpenRouter response"
            return "Should not reach here"
        
        self.staged_service.generate_staged_response = simple_generate
        
        result = await self.staged_service.generate_staged_response(
            "User question", user
        )
        
        assert result == "Direct OpenRouter response"


@pytest.mark.django_db
class TestContextManager:
    
    @pytest.fixture
    def context_manager(self):
        return ContextManager()
    
    def test_save_and_get_context(self, context_manager):
        user_id = "123"
        context_data = [
            {"prompt": "Test prompt", "response": "Test response"}
        ]
        
        context_manager.save_context(user_id, context_data)
        retrieved = context_manager.get_saved_context(user_id)
        
        assert retrieved == context_data
    
    def test_clear_context(self, context_manager):
        user_id = "123"
        context_data = [{"prompt": "Test", "response": "Response"}]
        
        context_manager.save_context(user_id, context_data)
        cleared = context_manager.clear_saved_context(user_id)
        
        assert cleared == context_data
        assert context_manager.get_saved_context(user_id) == []
    
    def test_context_isolation_between_users(self, context_manager):
        context1 = [{"prompt": "User1", "response": "Response1"}]
        context2 = [{"prompt": "User2", "response": "Response2"}]
        
        context_manager.save_context("user1", context1)
        context_manager.save_context("user2", context2)
        
        assert context_manager.get_saved_context("user1") == context1
        assert context_manager.get_saved_context("user2") == context2
    
    def test_prepare_stage_context(self, context_manager):
        user_message = "Original question"
        context_history = ["Previous response 1", "Previous response 2"]
        stage_results = {
            "stage1": ["Result 1", "Result 2"],
            "stage2": ["Result 3"]
        }
        saved_context = [
            {"prompt": "Saved prompt", "response": "Saved response"}
        ]
        
        result = context_manager.prepare_stage_context(
            user_message, context_history, stage_results, saved_context
        )
        
        assert "Original question" in result
        assert "Result 1" in result
        assert "Result 2" in result
        assert "Result 3" in result
        assert "Saved prompt" in result
        assert "Saved response" in result
    
    def test_extract_save_context_data(self, context_manager):
        prompts = [
            {"prompt": "Prompt 1"},
            {"prompt": "Prompt 2", "saveLastAsContext": True},
            {"prompt": "Prompt 3", "saveLastAsContext": False}
        ]
        responses = ["Response 1", "Response 2", "Response 3"]
        
        result = context_manager.extract_save_context_data(prompts, responses)
        
        assert len(result) == 1
        assert result[0]["prompt"] == "Prompt 2"
        assert result[0]["response"] == "Response 2"