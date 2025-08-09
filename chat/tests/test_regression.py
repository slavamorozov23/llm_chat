import pytest
from unittest.mock import Mock, patch
from chat.services.chat_service import ChatService
from chat.services.staged_generation_service import StagedGenerationService
from chat.models import Chat, Message, StagedGenerationConfig


@pytest.mark.django_db
class TestRegression:
    
    @pytest.fixture(autouse=True)
    def setup(self, openrouter_settings):
        self.chat_service = ChatService()
        self.staged_service = StagedGenerationService()
    
    def test_backward_compat_chat_creation(self, user):
        chat1 = self.chat_service.get_or_create_chat(user)
        chat2 = self.chat_service.get_or_create_chat(user)
        
        assert chat1.id == chat2.id
        assert chat1.user == user
        assert not chat1.is_archived
        assert Chat.objects.filter(user=user).count() == 1
    
    @patch('chat.services.response_generator.ResponseGenerator.generate_response_stages')
    def test_backward_compat_message_creation(self, mock_generate, user):
        chat = self.chat_service.get_or_create_chat(user)
        user_message_content = "Test regression message"
        
        result = self.chat_service.process_user_message(user, user_message_content)
        
        user_message = Message.objects.get(id=result['user_message_id'])
        assert user_message.content == user_message_content
        assert user_message.role == 'user'
        assert user_message.chat == chat
        
        assistant_message = Message.objects.get(id=result['assistant_message_id'])
        assert assistant_message.role == 'assistant'
        assert assistant_message.is_generating
    
    def test_backward_compat_chat_archiving(self, user):
        chat = self.chat_service.get_or_create_chat(user)
        original_id = chat.id
        
        Message.objects.create(chat=chat, role='user', content='Test')
        Message.objects.create(chat=chat, role='assistant', content='Response')
        
        self.chat_service.archive_chat(chat)
        
        assert not Chat.objects.filter(id=original_id).exists()
        assert user.archived_chats.count() == 1
        
        new_chat = self.chat_service.get_or_create_chat(user)
        assert new_chat.id != original_id
        assert not new_chat.is_archived
    
    def test_backward_compat_staged_config_management(self, user):
        config_data = {
            "stage1": [
                {"prompt": "Analysis: {user_message}", "saveLastAsContext": True}
            ],
            "stage2": [
                {"prompt": "Response: {stage1_results}"}
            ]
        }
        
        self.staged_service.create_config(user, "regression_test", config_data)
        
        config = StagedGenerationConfig.objects.get(user=user, name="regression_test")
        assert config.config_data == config_data
        assert not config.is_active
        
        result = self.staged_service.activate_config(user, "regression_test")
        assert result
        
        active_config = self.staged_service.get_active_config(user)
        assert active_config == config_data
        
        config.refresh_from_db()
        assert config.is_active
        
        self.staged_service.deactivate_all_configs(user)
        
        inactive_config = self.staged_service.get_active_config(user)
        assert inactive_config is None
        
        config.refresh_from_db()
        assert not config.is_active
    
    def test_backward_compat_config_validation(self):
        valid_config = {
            "stage1": [{"prompt": "Valid: {user_message}"}]
        }
        assert self.staged_service.validate_config(valid_config)
        
        invalid_configs = [
            {},
            {"stage1": "not_list"},
            {"stage1": []},
            {"stage1": [{"no_prompt": "test"}]},
        ]
        
        for config in invalid_configs:
            assert not self.staged_service.validate_config(config)
    
    @patch('chat.services.openrouter_service.OpenRouterService._make_request')
    def test_backward_compat_response_generation(self, mock_request, user):
        mock_request.return_value = {
            'choices': [{'message': {'content': 'Mocked response'}}],
            'usage': {'prompt_tokens': 10, 'completion_tokens': 20, 'total_tokens': 30}
        }
        
        chat = self.chat_service.get_or_create_chat(user)
        result = self.chat_service.process_user_message(user, "Test message")
        
        user_message = Message.objects.get(id=result['user_message_id'])
        assert user_message.content == "Test message"
        
        assert hasattr(self.chat_service, 'response_generator')
        assert hasattr(self.chat_service.response_generator, 'generate_response_stages')
        
        assistant_message = self.chat_service.message_manager.create_assistant_message(chat)
        assert assistant_message.role == 'assistant'
        assert assistant_message.is_generating
    
    def test_backward_compat_context_mechanism(self, user):
        assert hasattr(self.staged_service, 'context_manager')
        context_manager = self.staged_service.context_manager
        
        user_id = str(user.id)
        test_context = [
            {"prompt": "Regression test prompt", "response": "Regression test response"}
        ]
        
        context_manager.save_context(user_id, test_context)
        saved_context = context_manager.get_saved_context(user_id)
        assert saved_context == test_context
        
        cleared_context = context_manager.clear_saved_context(user_id)
        assert cleared_context == test_context
        
        empty_context = context_manager.get_saved_context(user_id)
        assert empty_context == []
    
    def test_backward_compat_api_methods(self):
        chat_service_methods = [
            'get_or_create_chat',
            'process_user_message',
            'archive_chat'
        ]
        
        for method in chat_service_methods:
            assert hasattr(self.chat_service, method)
            assert callable(getattr(self.chat_service, method))
        
        staged_service_methods = [
            'get_active_config',
            'validate_config',
            'generate_staged_response',
            'create_config',
            'activate_config',
            'deactivate_all_configs'
        ]
        
        for method in staged_service_methods:
            assert hasattr(self.staged_service, method)
            assert callable(getattr(self.staged_service, method))
    
    def test_message_status_updates(self, chat):
        message_manager = self.chat_service.message_manager
        
        assistant_msg = message_manager.create_assistant_message(chat)
        initial_stage = assistant_msg.generation_stage
        
        message_manager.update_message_status(assistant_msg, "Test status", 2)
        assistant_msg.refresh_from_db()
        assert assistant_msg.generation_stage == 2
        assert assistant_msg.generation_status_text == "Test status"
        
        message_manager.finalize_message(assistant_msg, "Final content")
        assistant_msg.refresh_from_db()
        assert not assistant_msg.is_generating
        assert assistant_msg.content == "Final content"
        assert assistant_msg.generation_stage == 0
    
    def test_multiple_configs_single_active(self, user):
        config1 = self.staged_service.create_config(
            user, "config1", {"stage1": [{"prompt": "test1"}]}
        )
        config2 = self.staged_service.create_config(
            user, "config2", {"stage1": [{"prompt": "test2"}]}
        )
        
        self.staged_service.activate_config(user, "config1")
        config1.refresh_from_db()
        assert config1.is_active
        
        self.staged_service.activate_config(user, "config2")
        config1.refresh_from_db()
        config2.refresh_from_db()
        assert not config1.is_active
        assert config2.is_active
    
    @pytest.mark.asyncio
    @patch('chat.services.generation_executor.GenerationExecutor.execute_stage_prompts')
    async def test_async_generation_with_context(self, mock_execute, user):
        config = StagedGenerationConfig.objects.create(
            user=user,
            name="async_test",
            config_data={
                "stage1": [{"prompt": "Test: {user_message}", "saveLastAsContext": True}]
            },
            is_active=True
        )
        
        mock_execute.return_value = (
            ["Test response"],
            [{"prompt": "Test: {user_message}", "response": "Test response"}]
        )
        
        result = await self.staged_service.generate_staged_response(
            "User input", user
        )
        
        assert result == "Test response"
        
        saved_context = self.staged_service.context_manager.get_saved_context(str(user.id))
        assert len(saved_context) == 1
        assert saved_context[0]["prompt"] == "Test: {user_message}"
        assert saved_context[0]["response"] == "Test response"