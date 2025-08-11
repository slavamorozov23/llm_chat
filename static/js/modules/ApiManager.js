/**
 * Модуль для управления API запросами
 */
class ApiManager {
    constructor() {
        this.pollInterval = null;
    }

    async sendMessage(message) {
        try {
            const response = await fetch('/chat/api/send-message/', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'X-CSRFToken': this.getCsrfToken()
                },
                body: JSON.stringify({ message })
            });

            return await response.json();
        } catch (error) {
            console.error('Ошибка отправки сообщения:', error);
            throw error;
        }
    }

    async getMessageStatus(messageId) {
        try {
            const response = await fetch(`/chat/api/message-status/${messageId}/`);
            return await response.json();
        } catch (error) {
            console.error('Ошибка получения статуса:', error);
            throw error;
        }
    }

    async loadMessages() {
        try {
            const response = await fetch('/chat/api/chat-messages/');
            return await response.json();
        } catch (error) {
            console.error('Ошибка загрузки сообщений:', error);
            throw error;
        }
    }

    async stopGeneration() {
        const response = await fetch('/chat/api/stop-generation/', {
            method: 'POST',
            headers: {
                'X-CSRFToken': this.getCsrfToken()
            }
        });

        return await response.json();
    }

    async archiveChat() {
        const response = await fetch('/chat/api/archive-chat/', {
            method: 'POST',
            headers: {
                'X-CSRFToken': this.getCsrfToken()
            }
        });

        return await response.json();
    }

    startPolling(messageId, callback) {
        this.pollInterval = setInterval(async () => {
            try {
                const response = await fetch(`/chat/api/message-status/${messageId}/`);
                const data = await response.json();

                callback(data);
            } catch (error) {
                console.error('Ошибка получения статуса:', error);
                this.stopPolling();
            }
        }, 3000);
    }

    stopPolling() {
        if (this.pollInterval) {
            clearInterval(this.pollInterval);
            this.pollInterval = null;
        }
    }

    getCsrfToken() {
        const token = document.querySelector('[name=csrfmiddlewaretoken]');
        if (!token) {
            console.error('CSRF token not found');
            return '';
        }
        return token.value;
    }
}