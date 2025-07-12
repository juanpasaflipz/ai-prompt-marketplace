-- AI Prompt Marketplace Initial Schema
-- PostgreSQL 15+

-- Enable required extensions
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS "pg_trgm"; -- For better text search

-- Create custom types
CREATE TYPE user_role AS ENUM ('buyer', 'seller', 'admin');
CREATE TYPE subscription_status AS ENUM ('trial', 'active', 'cancelled', 'expired');
CREATE TYPE prompt_category AS ENUM ('marketing', 'sales', 'support', 'content', 'development', 'analytics', 'other');
CREATE TYPE prompt_status AS ENUM ('active', 'inactive', 'pending', 'rejected');
CREATE TYPE model_type AS ENUM ('gpt-4o', 'gpt-4', 'gpt-3.5-turbo', 'claude-3', 'custom');
CREATE TYPE transaction_status AS ENUM ('pending', 'processing', 'completed', 'failed', 'refunded', 'cancelled');
CREATE TYPE transaction_type AS ENUM ('prompt_purchase', 'subscription', 'usage_fee', 'refund');

-- Users table
CREATE TABLE users (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    email VARCHAR(255) UNIQUE NOT NULL,
    company_name VARCHAR(255) NOT NULL,
    password_hash VARCHAR(255) NOT NULL,
    role user_role DEFAULT 'buyer' NOT NULL,
    stripe_customer_id VARCHAR(255) UNIQUE,
    subscription_status subscription_status DEFAULT 'trial' NOT NULL,
    is_active VARCHAR(10) DEFAULT 'true',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP NOT NULL,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP NOT NULL
);

-- Prompts table
CREATE TABLE prompts (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    seller_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    title VARCHAR(255) NOT NULL,
    description TEXT,
    category prompt_category NOT NULL,
    model_type model_type DEFAULT 'gpt-4o' NOT NULL,
    prompt_template TEXT NOT NULL,
    variables JSONB DEFAULT '{}',
    example_input TEXT,
    example_output TEXT,
    price_per_use DECIMAL(10,2) NOT NULL CHECK (price_per_use >= 0),
    total_uses INTEGER DEFAULT 0 CHECK (total_uses >= 0),
    total_revenue DECIMAL(12,2) DEFAULT 0 CHECK (total_revenue >= 0),
    average_rating DECIMAL(3,2) CHECK (average_rating >= 0 AND average_rating <= 5),
    rating_count INTEGER DEFAULT 0 CHECK (rating_count >= 0),
    status prompt_status DEFAULT 'pending' NOT NULL,
    version INTEGER DEFAULT 1 CHECK (version >= 1),
    tags JSONB DEFAULT '[]',
    metadata JSONB DEFAULT '{}',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP NOT NULL,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP NOT NULL
);

-- Transactions table
CREATE TABLE transactions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    buyer_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    prompt_id UUID REFERENCES prompts(id) ON DELETE SET NULL,
    stripe_payment_id VARCHAR(255) UNIQUE,
    stripe_payment_intent_id VARCHAR(255) UNIQUE,
    amount DECIMAL(10,2) NOT NULL CHECK (amount >= 0),
    currency VARCHAR(3) DEFAULT 'USD' NOT NULL,
    status transaction_status DEFAULT 'pending' NOT NULL,
    transaction_type transaction_type DEFAULT 'prompt_purchase' NOT NULL,
    metadata JSONB DEFAULT '{}',
    failure_reason TEXT,
    processed_at TIMESTAMP,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP NOT NULL,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP NOT NULL
);

-- Analytics events table
CREATE TABLE analytics_events (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID REFERENCES users(id) ON DELETE CASCADE,
    session_id VARCHAR(255),
    event_type VARCHAR(100) NOT NULL,
    entity_type VARCHAR(50) NOT NULL,
    entity_id VARCHAR(255),
    metadata JSONB DEFAULT '{}',
    ip_address VARCHAR(45),
    user_agent VARCHAR(500),
    referrer VARCHAR(500),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP NOT NULL
);

-- Create indexes for performance
CREATE INDEX idx_users_email ON users(email);
CREATE INDEX idx_users_stripe_customer ON users(stripe_customer_id);

CREATE INDEX idx_prompts_category ON prompts(category);
CREATE INDEX idx_prompts_seller ON prompts(seller_id);
CREATE INDEX idx_prompts_status ON prompts(status);
CREATE INDEX idx_prompts_title ON prompts USING gin(title gin_trgm_ops); -- Full text search
CREATE INDEX idx_prompts_tags ON prompts USING gin(tags);

CREATE INDEX idx_transactions_buyer ON transactions(buyer_id);
CREATE INDEX idx_transactions_prompt ON transactions(prompt_id);
CREATE INDEX idx_transactions_status ON transactions(status);
CREATE INDEX idx_transactions_created ON transactions(created_at);

CREATE INDEX idx_analytics_user_event ON analytics_events(user_id, event_type);
CREATE INDEX idx_analytics_entity ON analytics_events(entity_type, entity_id);
CREATE INDEX idx_analytics_created ON analytics_events(created_at);
CREATE INDEX idx_analytics_session ON analytics_events(session_id);

-- Create update trigger for updated_at columns
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = CURRENT_TIMESTAMP;
    RETURN NEW;
END;
$$ language 'plpgsql';

CREATE TRIGGER update_users_updated_at BEFORE UPDATE ON users
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER update_prompts_updated_at BEFORE UPDATE ON prompts
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER update_transactions_updated_at BEFORE UPDATE ON transactions
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

-- Create function to update prompt statistics
CREATE OR REPLACE FUNCTION update_prompt_stats()
RETURNS TRIGGER AS $$
BEGIN
    IF NEW.status = 'completed' AND OLD.status != 'completed' THEN
        UPDATE prompts 
        SET 
            total_uses = total_uses + 1,
            total_revenue = total_revenue + NEW.amount
        WHERE id = NEW.prompt_id;
    END IF;
    RETURN NEW;
END;
$$ language 'plpgsql';

CREATE TRIGGER update_prompt_stats_on_transaction
    AFTER UPDATE ON transactions
    FOR EACH ROW 
    WHEN (NEW.prompt_id IS NOT NULL)
    EXECUTE FUNCTION update_prompt_stats();