-- Миграция для создания таблиц в PostgreSQL / Supabase
-- Выполните этот скрипт в Supabase SQL Editor или через psql

-- Таблица пользователей (владельцев аккаунтов)
CREATE TABLE IF NOT EXISTS users (
    id SERIAL PRIMARY KEY,
    email VARCHAR(255) UNIQUE NOT NULL,
    hashed_password VARCHAR(255) NOT NULL,
    company_name VARCHAR(255) NOT NULL,
    is_active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_users_email ON users(email);

-- Таблица клиентов бота (конечные пользователи)
CREATE TABLE IF NOT EXISTS bot_users (
    id SERIAL PRIMARY KEY,
    owner_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    user_id VARCHAR(255) NOT NULL,
    name VARCHAR(255),
    phone VARCHAR(50),
    language VARCHAR(10) DEFAULT 'ru',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_bot_users_user_id ON bot_users(user_id);
CREATE INDEX idx_bot_users_owner_id ON bot_users(owner_id);

-- Таблица сообщений (история диалогов)
CREATE TABLE IF NOT EXISTS messages (
    id SERIAL PRIMARY KEY,
    bot_user_id INTEGER NOT NULL REFERENCES bot_users(id) ON DELETE CASCADE,
    role VARCHAR(20) NOT NULL,
    content TEXT NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_messages_bot_user_id ON messages(bot_user_id);

-- Таблица лидов (заявок)
CREATE TABLE IF NOT EXISTS leads (
    id SERIAL PRIMARY KEY,
    owner_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    bot_user_id INTEGER NOT NULL REFERENCES bot_users(id) ON DELETE CASCADE,
    name VARCHAR(255) NOT NULL,
    phone VARCHAR(50) NOT NULL,
    city VARCHAR(255),
    object_type VARCHAR(255),
    area VARCHAR(100),
    summary TEXT,
    language VARCHAR(10) DEFAULT 'ru',
    status VARCHAR(20) DEFAULT 'new',
    telegram_message_id INTEGER,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_leads_owner_id ON leads(owner_id);
CREATE INDEX idx_leads_bot_user_id ON leads(bot_user_id);
CREATE INDEX idx_leads_status ON leads(status);

-- Trigger для автоматического обновления updated_at
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = CURRENT_TIMESTAMP;
    RETURN NEW;
END;
$$ language 'plpgsql';

CREATE TRIGGER update_users_updated_at BEFORE UPDATE ON users
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER update_bot_users_updated_at BEFORE UPDATE ON bot_users
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER update_leads_updated_at BEFORE UPDATE ON leads
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

-- Комментарии для документации
COMMENT ON TABLE users IS 'Владельцы аккаунтов (компании, использующие SaaS)';
COMMENT ON TABLE bot_users IS 'Клиенты бота (конечные пользователи)';
COMMENT ON TABLE messages IS 'История диалогов';
COMMENT ON TABLE leads IS 'Заявки (лиды)';
