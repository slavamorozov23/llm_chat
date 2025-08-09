/**
 * Модуль для управления UI элементами
 */
class UIManager {
    constructor() {
        this.messageInput = null;
        this.sendBtn = null;
    }

    initElements(messageInput, sendBtn) {
        this.messageInput = messageInput;
        this.sendBtn = sendBtn;
    }

    showConfirmModal(message, onConfirm) {
        const modal = document.getElementById('confirmModal');
        const confirmBtn = document.getElementById('confirmBtn');
        const cancelBtn = document.getElementById('cancelBtn');
        const messageElement = modal.querySelector('p');

        // Устанавливаем текст сообщения
        if (messageElement && message) {
            messageElement.textContent = message;
        }

        modal.style.display = 'block';

        // Очищаем предыдущие обработчики
        const newConfirmBtn = confirmBtn.cloneNode(true);
        const newCancelBtn = cancelBtn.cloneNode(true);
        confirmBtn.parentNode.replaceChild(newConfirmBtn, confirmBtn);
        cancelBtn.parentNode.replaceChild(newCancelBtn, cancelBtn);

        newConfirmBtn.onclick = () => {
            modal.style.display = 'none';
            if (onConfirm) {
                onConfirm();
            }
        };

        newCancelBtn.onclick = () => {
            modal.style.display = 'none';
        };

        // Закрытие по клику вне модального окна
        modal.onclick = (e) => {
            if (e.target === modal) {
                modal.style.display = 'none';
            }
        };
    }

    showMessage(text) {
        // Простое уведомление вместо alert
        const messageDiv = document.createElement('div');
        messageDiv.style.cssText = `
            position: fixed;
            top: 20px;
            right: 20px;
            background: #333;
            color: white;
            padding: 15px;
            border-radius: 4px;
            z-index: 1001;
            max-width: 300px;
        `;
        messageDiv.textContent = text;
        document.body.appendChild(messageDiv);

        setTimeout(() => {
            document.body.removeChild(messageDiv);
        }, 3000);
    }

    clearInput() {
        if (this.messageInput) {
            this.messageInput.value = '';
            this.autoResize();
        }
    }

    toggleSendButton(enabled) {
        if (this.sendBtn) {
            this.sendBtn.disabled = !enabled;
        }
    }

    autoResize() {
        if (this.messageInput) {
            this.messageInput.style.height = 'auto';
            this.messageInput.style.height = this.messageInput.scrollHeight + 'px';
        }
    }

    bindInputEvents(onSubmit) {
        if (this.messageInput) {
            // Автоматическое изменение размера textarea
            this.messageInput.addEventListener('input', () => this.autoResize());

            // Enter для отправки (Shift+Enter для новой строки)
            this.messageInput.addEventListener('keydown', (e) => {
                if (e.key === 'Enter' && !e.shiftKey) {
                    e.preventDefault();
                    onSubmit();
                }
            });
        }
    }
}