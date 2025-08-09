import pytest
from django.contrib.auth.models import User
import factory
from factory.django import DjangoModelFactory
from chat.models import Chat, Message, StagedGenerationConfig, OpenRouterSettings


pytest_plugins = ['pytest_django']


class UserFactory(DjangoModelFactory):
    class Meta:
        model = User
    
    username = factory.Sequence(lambda n: f'testuser{n}')
    email = factory.LazyAttribute(lambda obj: f'{obj.username}@test.com')
    password = factory.PostGenerationMethodCall('set_password', 'testpass123')


class ChatFactory(DjangoModelFactory):
    class Meta:
        model = Chat
    
    user = factory.SubFactory(UserFactory)
    is_archived = False


class MessageFactory(DjangoModelFactory):
    class Meta:
        model = Message
    
    chat = factory.SubFactory(ChatFactory)
    role = 'user'
    content = factory.Faker('sentence', nb_words=10)
    is_generating = False
    generation_stage = 0


class StagedGenerationConfigFactory(DjangoModelFactory):
    class Meta:
        model = StagedGenerationConfig
    
    user = factory.SubFactory(UserFactory)
    name = factory.Sequence(lambda n: f'config_{n}')
    config_data = {
        "stage1": [
            {"prompt": "Test prompt: {user_message}"}
        ]
    }
    is_active = False


class OpenRouterSettingsFactory(DjangoModelFactory):
    class Meta:
        model = OpenRouterSettings
        django_get_or_create = ('id',)
    
    id = 1
    api_key = 'test_api_key'
    model = 'test/model'


@pytest.fixture
def user():
    return UserFactory()


@pytest.fixture
def chat(user):
    return ChatFactory(user=user)


@pytest.fixture
def message(chat):
    return MessageFactory(chat=chat)


@pytest.fixture
def staged_config(user):
    return StagedGenerationConfigFactory(user=user)


@pytest.fixture
def openrouter_settings(db):
    return OpenRouterSettingsFactory()


@pytest.fixture
def mock_openrouter_response(mocker):
    return mocker.patch(
        'chat.services.openrouter_service.OpenRouterService._make_request',
        return_value={
            'choices': [
                {'message': {'content': 'Mocked response'}}
            ],
            'usage': {
                'prompt_tokens': 10,
                'completion_tokens': 20,
                'total_tokens': 30
            }
        }
    )


@pytest.fixture
def mock_threading(mocker):
    mock_thread = mocker.patch('chat.services.chat_service.threading.Thread')
    mock_thread.return_value.start = mocker.Mock()
    mock_thread.return_value.daemon = True
    return mock_thread


@pytest.fixture(autouse=True)
def disable_threading_in_tests(mocker):
    def run_sync(*args, **kwargs):
        pass
    
    mocker.patch('chat.services.chat_service.threading.Thread', side_effect=lambda target, args: target(*args))
    return mocker