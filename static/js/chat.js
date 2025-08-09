/**
 * Минималистичный чат с LLM
 * Следует принципам проекта: максимум Django, минимум JavaScript
 * Модульная архитектура
 */

// Импорт модулей (в реальном проекте используйте ES6 modules или bundler)
// Пока используем глобальные классы

class ChatManager {
    constructor() {
        this.isGenerating = false;
        this.currentMessageId = null;

        this.initElements();
        this.initManagers();
        this.bindEvents();
        this.loadMessages();
    }

    initElements() {
        this.chatMessages = document.getElementById('chatMessages');
        this.messageForm = document.getElementById('messageForm');
        this.messageInput = document.getElementById('messageInput');
        this.sendBtn = document.getElementById('sendBtn');
        this.archiveBtn = document.getElementById('archiveBtn');
    }

    initManagers() {
        this.messageManager = new MessageManager(this.chatMessages);
        this.apiManager = new ApiManager();
        this.uiManager = new UIManager();
        this.uiManager.initElements(this.messageInput, this.sendBtn);
    }

    bindEvents() {
        this.messageForm.addEventListener('submit', (e) => this.handleSubmit(e));
        this.archiveBtn.addEventListener('click', () => this.archiveChat());

        // Делегируем управление input событиями UI менеджеру
        this.uiManager.bindInputEvents(() => {
            this.messageForm.dispatchEvent(new Event('submit'));
        });
    }

    async handleSubmit(e) {
        e.preventDefault();

        if (this.isGenerating) {
            this.uiManager.showMessage('Дождитесь завершения генерации текущего ответа');
            return;
        }

        const message = this.messageInput.value.trim();
        if (!message) return;

        try {
            const data = await this.apiManager.sendMessage(message);

            if (data.success) {
                this.messageManager.addUserMessage(message);
                this.messageManager.addAssistantMessage(data.message_id, 'Генерирую ответ...', true);
                this.uiManager.clearInput();
                this.startPolling(data.message_id);
            } else {
                this.uiManager.showMessage('Ошибка: ' + data.error);
            }
        } catch (error) {
            this.uiManager.showMessage('Произошла ошибка при отправке сообщения');
        }
    }

    // Методы для работы с сообщениями перенесены в MessageManager

    async startPolling(messageId) {
        this.isGenerating = true;
        this.currentMessageId = messageId;
        this.uiManager.toggleSendButton(false);

        this.apiManager.startPolling(messageId, (data) => {
            this.messageManager.updateMessageStatus(messageId, data.content, data.is_generating, data.generation_stage, data.generation_status_text);

            if (!data.is_generating) {
                this.stopPolling();
            }
        });
    }

    stopPolling() {
        this.apiManager.stopPolling();
        this.isGenerating = false;
        this.currentMessageId = null;
        this.uiManager.toggleSendButton(true);
    }

    async loadMessages() {
        try {
            const response = await fetch('/chat/api/chat-messages/');
            const data = await response.json();

            if (data.messages) {
                this.chatMessages.innerHTML = '';

                data.messages.forEach(message => {
                    if (message.role === 'user') {
                        this.addUserMessageFromData(message);
                    } else {
                        this.addAssistantMessageFromData(message);
                    }
                });

                // Проверяем, есть ли генерирующиеся сообщения
                const generatingMessage = data.messages.find(m => m.is_generating);
                if (generatingMessage) {
                    this.startPolling(generatingMessage.id);
                }
            }
        } catch (error) {
            console.error('Ошибка загрузки сообщений:', error);
        }
    }

    addUserMessageFromData(message) {
        const date = new Date(message.created_at);
        const timeStr = date.getHours().toString().padStart(2, '0') + ':' +
            date.getMinutes().toString().padStart(2, '0');

        const messageDiv = document.createElement('div');
        messageDiv.className = 'message user';
        messageDiv.innerHTML = `
            <strong>Вы:</strong>
            <div class="message-content">${this.escapeHtml(message.content)}</div>
            <div class="message-time">${timeStr}</div>
        `;

        this.chatMessages.appendChild(messageDiv);
    }

    addAssistantMessageFromData(message) {
        const date = new Date(message.created_at);
        const timeStr = date.getHours().toString().padStart(2, '0') + ':' +
            date.getMinutes().toString().padStart(2, '0');

        const messageDiv = document.createElement('div');
        messageDiv.className = 'message assistant';
        messageDiv.setAttribute('data-message-id', message.id);

        let statusText = '';
        if (message.is_generating) {
            switch (message.generation_stage) {
                case 1: statusText = 'Генерация...'; break;
                case 2: statusText = 'Уточнение...'; break;
                case 3: statusText = 'Проверка...'; break;
                default: statusText = 'Обработка...';
            }
        }

        const generationStatus = message.is_generating ?
            `<div class="generation-status">${statusText}</div>` : '';

        messageDiv.innerHTML = `
            <strong>LLM:</strong>
            <div class="message-content">${this.escapeHtml(message.content)}</div>
            ${generationStatus}
            <div class="message-time">${timeStr}</div>
        `;

        this.chatMessages.appendChild(messageDiv);
    }

    async archiveChat() {
        if (this.isGenerating) {
            this.uiManager.showMessage('Дождитесь завершения генерации ответа');
            return;
        }

        this.uiManager.showConfirmModal(
            'Вы уверены, что хотите архивировать этот чат?',
            async () => {
                await this.performArchive();
            }
        );
    }

    async performArchive() {
        try {
            const data = await this.apiManager.archiveChat();

            if (data.success) {
                this.uiManager.showMessage('Чат успешно архивирован!');
                setTimeout(() => location.reload(), 1500);
            } else {
                this.uiManager.showMessage('Ошибка: ' + data.error);
            }
        } catch (error) {
            console.error('Ошибка архивации:', error);
            this.uiManager.showMessage('Произошла ошибка при архивации чата');
        }
    }

    // Вспомогательные методы перенесены в соответствующие модули

    escapeHtml(text) {
        const div = document.createElement('div');
        div.textContent = text;
        return div.innerHTML;
    }

    getCSRFToken() {
        return document.querySelector('[name=csrfmiddlewaretoken]').value;
    }
}

// Инициализация при загрузке страницы
document.addEventListener('DOMContentLoaded', function () {
    window.chatManager = new ChatManager();
});