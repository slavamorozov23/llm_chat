/**
 * Модуль для управления сообщениями
 */
class MessageManager {
    constructor(chatMessages) {
        this.chatMessages = chatMessages;
    }

    addUserMessage(content) {
        const now = new Date();
        const timeStr = now.getHours().toString().padStart(2, '0') + ':' +
            now.getMinutes().toString().padStart(2, '0');

        const messageDiv = document.createElement('div');
        messageDiv.className = 'message user';
        messageDiv.innerHTML = `
            <strong>Вы:</strong>
            <div class="message-content">${this.escapeHtml(content)}</div>
            <div class="message-time">${timeStr}</div>
        `;

        this.chatMessages.appendChild(messageDiv);
        this.scrollToBottom();
    }

    addAssistantMessage(messageId, content, isGenerating = false) {
        const now = new Date();
        const timeStr = now.getHours().toString().padStart(2, '0') + ':' +
            now.getMinutes().toString().padStart(2, '0');

        let messageDiv = document.querySelector(`[data-message-id="${messageId}"]`);

        if (!messageDiv) {
            messageDiv = document.createElement('div');
            messageDiv.className = 'message assistant';
            messageDiv.setAttribute('data-message-id', messageId);
            this.chatMessages.appendChild(messageDiv);
        }

        const generationStatus = isGenerating ?
            '<div class="generation-status">Генерация...</div>' : '';

        messageDiv.innerHTML = `
            <strong>LLM:</strong>
            <div class="message-content">${this.escapeHtml(content)}</div>
            ${generationStatus}
            <div class="message-time">${timeStr}</div>
        `;

        this.scrollToBottom();
    }

    updateMessageStatus(messageId, content, isGenerating, stage, statusText = '') {
        const messageDiv = document.querySelector(`[data-message-id="${messageId}"]`);
        if (!messageDiv) return;

        const contentDiv = messageDiv.querySelector('.message-content');
        const statusDiv = messageDiv.querySelector('.generation-status');

        if (contentDiv) {
            contentDiv.textContent = content;
        }

        // Обработка статуса
        if (isGenerating) {
            // Генерация идет - показываем статус
            const displayStatus = statusText || (stage === 1 ? 'Генерация...' :
                stage === 2 ? 'Уточнение...' :
                    stage === 3 ? 'Проверка...' : 'Обработка...');

            if (!statusDiv) {
                const statusElement = document.createElement('div');
                statusElement.className = 'generation-status';
                statusElement.textContent = displayStatus;
                contentDiv.after(statusElement);
            } else {
                statusDiv.textContent = displayStatus;
                statusDiv.className = 'generation-status'; // Убираем stopped если был
            }
        } else if (stage === -1) {
            // Генерация остановлена - показываем статус остановки
            if (!statusDiv) {
                const statusElement = document.createElement('div');
                statusElement.className = 'generation-status stopped';
                statusElement.textContent = 'Генерация остановлена';
                contentDiv.after(statusElement);
            } else {
                statusDiv.className = 'generation-status stopped';
                statusDiv.textContent = 'Генерация остановлена';
            }
        } else {
            // Генерация завершена нормально - убираем статус
            if (statusDiv) {
                statusDiv.remove();
            }
        }

        this.scrollToBottom();
    }

    addUserMessageFromData(message) {
        // Добавляем границу контекста если нужно
        if (message.is_context_boundary) {
            this.addContextBoundary();
        }

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
        // Добавляем границу контекста если нужно
        if (message.is_context_boundary) {
            this.addContextBoundary();
        }

        const date = new Date(message.created_at);
        const timeStr = date.getHours().toString().padStart(2, '0') + ':' +
            date.getMinutes().toString().padStart(2, '0');

        const messageDiv = document.createElement('div');
        messageDiv.className = 'message assistant';
        messageDiv.setAttribute('data-message-id', message.id);

        // Формируем блок статуса
        let statusHtml = '';
        if (message.is_generating) {
            const statusText = message.generation_status_text ||
                (message.generation_stage === 1 ? 'Генерация...' :
                    message.generation_stage === 2 ? 'Уточнение...' :
                        message.generation_stage === 3 ? 'Проверка...' : 'Обработка...');
            statusHtml = `<div class="generation-status">${statusText}</div>`;
        } else if (message.generation_stage === -1) {
            statusHtml = '<div class="generation-status stopped">Генерация остановлена</div>';
        }

        messageDiv.innerHTML = `
            <strong>LLM:</strong>
            <div class="message-content">${this.escapeHtml(message.content)}</div>
            ${statusHtml}
            <div class="message-time">${timeStr}</div>
        `;

        this.chatMessages.appendChild(messageDiv);
    }

    clearMessages() {
        this.chatMessages.innerHTML = '';
    }

    scrollToBottom() {
        this.chatMessages.scrollTop = this.chatMessages.scrollHeight;
    }

    escapeHtml(text) {
        const div = document.createElement('div');
        div.textContent = text;
        return div.innerHTML;
    }

    addContextBoundary() {
        const boundaryDiv = document.createElement('div');
        boundaryDiv.className = 'context-boundary';
        boundaryDiv.innerHTML = `
            <div class="context-boundary-line"></div>
            <div class="context-boundary-text">Граница контекста (64000 символов)</div>
            <div class="context-boundary-line"></div>
        `;
        this.chatMessages.appendChild(boundaryDiv);
    }
}