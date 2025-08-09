import pytest
from unittest.mock import Mock, patch
from chat.services.chat_service import ChatService
from chat.services.staged_generation_service import StagedGenerationService
from chat.services.chat_manager import ChatManager
from chat.services.message_manager import MessageManager
from chat.services.response_generator import ResponseGenerator
from chat.services.context_manager import ContextManager
from chat.services.config_manager import ConfigManager
from chat.services.generation_executor import GenerationExecutor
from chat.models import Chat, Message, StagedGenerationConfig


@pytest.mark.django_db
class TestModuleIntegration:
    
    @pytest.fixture(autouse=True)
    def setup(self, openrouter_settings):
        self.chat_service = ChatService()
        self.staged_service = StagedGenerationService()
    
    def test_chat_service_modules_initialized(self):
        assert isinstance(self.chat_service.chat_manager, ChatManager)
        assert isinstance(self.chat_service.message_manager, MessageManager)
        assert isinstance(self.chat_service.response_generator, ResponseGenerator)
    
    def test_staged_service_modules_initialized(self):
        assert isinstance(self.staged_service.config_manager, ConfigManager)
        assert isinstance(self.staged_service.context_manager, ContextManager)
        assert isinstance(self.staged_service.generation_executor, GenerationExecutor)
    
    def test_chat_creation_through_manager(self, user):
        chat = self.chat_service.get_or_create_chat(user)
        
        assert isinstance(chat, Chat)
        assert chat.user == user
        assert not chat.is_archived
        assert Chat.objects.filter(user=user).exists()
    
    def test_config_creation_through_staged_service(self, user):
        config_data = {
            "stage1": [{"prompt": "Integration test: {user_message}"}]
        }
        
        self.staged_service.create_config(user, "integration_test", config_data)
        
        config = StagedGenerationConfig.objects.get(user=user, name="integration_test")
        assert config.config_data == config_data
        assert not config.is_active
    
    @patch('chat.services.openrouter_service.OpenRouterService._make_request')
    @patch('chat.services.response_generator.ResponseGenerator.generate_response_stages')
    def test_cross_service_message_processing(self, mock_generate_stages, mock_request, user):
        mock_request.return_value = {
            'choices': [{'message': {'content': 'Test response'}}],
            'usage': {'prompt_tokens': 10, 'completion_tokens': 20, 'total_tokens': 30}
        }
        
        # Мокируем generate_response_stages для предотвращения зависания
        def mock_generate_response(message_id):
            from chat.models import Message
            message = Message.objects.get(id=message_id)
            message.content = 'Test response'
            message.status = 'completed'
            message.save()
        
        mock_generate_stages.side_effect = mock_generate_response
        
        config_data = {
            "stage1": [{"prompt": "Analyze: {user_message}", "saveLastAsContext": True}]
        }
        
        self.staged_service.create_config(user, "cross_test", config_data)
        self.staged_service.activate_config(user, "cross_test")
        
        chat = self.chat_service.get_or_create_chat(user)
        initial_message_count = chat.messages.count()
        
        result = self.chat_service.process_user_message(user, "Test message")
        
        assert 'chat_id' in result
        assert 'user_message_id' in result
        assert 'assistant_message_id' in result
        
        user_msg = Message.objects.get(id=result['user_message_id'])
        assert user_msg.content == "Test message"
        assert user_msg.role == 'user'
        
        chat.refresh_from_db()
        assert chat.messages.count() == initial_message_count + 2
    
    def test_context_manager_user_isolation(self, user):
        user2 = UserFactory()
        context_manager = ContextManager()
        
        context1 = [{"prompt": "Context 1", "response": "Response 1"}]
        context2 = [{"prompt": "Context 2", "response": "Response 2"}]
        
        context_manager.save_context(str(user.id), context1)
        context_manager.save_context(str(user2.id), context2)
        
        retrieved1 = context_manager.get_saved_context(str(user.id))
        retrieved2 = context_manager.get_saved_context(str(user2.id))
        
        assert retrieved1 == context1
        assert retrieved2 == context2
        assert retrieved1 != retrieved2
    
    def test_message_manager_status_lifecycle(self, chat):
        message_manager = MessageManager()
        
        assistant_msg = message_manager.create_assistant_message(chat)
        assert assistant_msg.is_generating
        assert assistant_msg.generation_stage == 1
        
        message_manager.update_message_status(assistant_msg, 'Processing...', 2)
        assistant_msg.refresh_from_db()
        assert assistant_msg.generation_stage == 2
        assert assistant_msg.generation_status_text == 'Processing...'
        
        message_manager.finalize_message(assistant_msg, 'Final content')
        assistant_msg.refresh_from_db()
        assert not assistant_msg.is_generating
        assert assistant_msg.generation_stage == 0
        assert assistant_msg.content == 'Final content'
    
    def test_message_error_handling(self, chat):
        message_manager = MessageManager()
        
        assistant_msg = message_manager.create_assistant_message(chat)
        message_manager.handle_generation_error(assistant_msg, 'Error occurred')
        
        assistant_msg.refresh_from_db()
        assert not assistant_msg.is_generating
        assert assistant_msg.generation_stage == -1
        assert assistant_msg.content == 'Error occurred'
    
    def test_config_manager_validation(self):
        config_manager = ConfigManager()
        
        valid_config = {"stage1": [{"prompt": "Valid prompt"}]}
        assert config_manager.validate_config(valid_config)
        
        invalid_configs = [
            {},
            {"stage1": "not_list"},
            {"stage1": []},
            {"stage1": [{"wrong_key": "value"}]}
        ]
        
        for config in invalid_configs:
            assert not config_manager.validate_config(config)
    
    def test_config_activation_deactivates_others(self, user):
        config1 = StagedGenerationConfig.objects.create(
            user=user,
            name="config1",
            config_data={"stage1": [{"prompt": "test"}]},
            is_active=True
        )
        
        config2 = StagedGenerationConfig.objects.create(
            user=user,
            name="config2",
            config_data={"stage1": [{"prompt": "test"}]},
            is_active=False
        )
        
        self.staged_service.activate_config(user, "config2")
        
        config1.refresh_from_db()
        config2.refresh_from_db()
        
        assert not config1.is_active
        assert config2.is_active
    
    def test_context_limited_history(self, chat):
        message_manager = MessageManager()
        
        for i in range(10):
            Message.objects.create(
                chat=chat,
                role='user' if i % 2 == 0 else 'assistant',
                content=f"Message {i}" * 100
            )
        
        current_msg = Message.objects.create(
            chat=chat,
            role='assistant',
            content='Current',
            is_generating=True
        )
        
        history = message_manager.get_context_limited_history(chat, current_msg.id)
        
        total_chars = sum(len(msg.content) for msg in history)
        assert total_chars <= 64000
        assert current_msg not in history


from chat.tests.conftest import UserFactory