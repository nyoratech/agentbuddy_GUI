-- PostgreSQL initialization script for finbuddy with Role-Based Access Control
-- This runs automatically when the container starts for the first time

-- ============================================================
-- CORE RESOURCE TABLES (unchanged from before)
-- ============================================================

-- Agents table
CREATE TABLE IF NOT EXISTS agents (
    id VARCHAR PRIMARY KEY,
    name VARCHAR NOT NULL,
    display_name VARCHAR NOT NULL,
    agent_module VARCHAR NOT NULL,
    description TEXT,
    config_json TEXT NOT NULL,
    user_id VARCHAR NOT NULL,              -- Owner
    agent_dir VARCHAR,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Tools table
CREATE TABLE IF NOT EXISTS tools (
    id VARCHAR PRIMARY KEY,
    name VARCHAR NOT NULL,
    display_name VARCHAR,
    api_module VARCHAR NOT NULL,
    api_function VARCHAR NOT NULL,
    description TEXT,
    tool_dir VARCHAR NOT NULL,
    schema_json TEXT,
    user_id VARCHAR NOT NULL,              -- Owner
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(api_module, api_function)
);

-- Agent instances table
CREATE TABLE IF NOT EXISTS agent_instances (
    id VARCHAR PRIMARY KEY,
    agent_id VARCHAR NOT NULL,
    user_id VARCHAR NOT NULL,              -- Owner
    instance_type VARCHAR NOT NULL,        -- 'local_docker', 'gc_run', 'aws_ecs', 'k8s'
    status VARCHAR DEFAULT 'stopped',      -- 'running', 'stopped', 'error', 'provisioning'
    address VARCHAR,                       -- Endpoint URL or IP
    port INTEGER,
    container_id VARCHAR,                  -- Docker container ID or cloud instance ID
    platform VARCHAR,                      -- 'gcp', 'aws', 'local'
    region VARCHAR,                        -- Cloud region
    image_name VARCHAR,                    -- Container image
    config_json TEXT,                      -- Instance-specific config
    environment_vars JSONB,                -- Environment variables
    metadata JSONB,                        -- Platform-specific metadata (GC Run service URL, Docker network, etc.)
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    started_at TIMESTAMP,
    stopped_at TIMESTAMP,
    last_health_check TIMESTAMP,
    FOREIGN KEY (agent_id) REFERENCES agents(id) ON DELETE CASCADE
);

-- GUI modules table
CREATE TABLE IF NOT EXISTS gui_modules (
    module_id INTEGER PRIMARY KEY,
    module_type VARCHAR NOT NULL UNIQUE,
    display_name VARCHAR NOT NULL,
    icon VARCHAR DEFAULT '📦',
    category VARCHAR DEFAULT 'general',
    default_width INTEGER DEFAULT 200,
    default_height INTEGER DEFAULT 100,
    min_width INTEGER DEFAULT 100,
    min_height INTEGER DEFAULT 50,
    resizable BOOLEAN DEFAULT TRUE,
    default_config JSONB,
    config_schema JSONB,
    render_template TEXT,
    description TEXT,
    user_id VARCHAR,                       -- Owner (NULL for system modules)
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    is_active BOOLEAN DEFAULT TRUE
);

-- Page layouts table
CREATE TABLE IF NOT EXISTS page_layouts (
    layout_id INTEGER PRIMARY KEY,
    page_name VARCHAR NOT NULL UNIQUE,
    description TEXT,
    layout_json TEXT NOT NULL DEFAULT '{"modules": []}',
    route VARCHAR,
    is_published BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    created_by VARCHAR                     -- Owner
);

-- ============================================================
-- ACCESS CONTROL TABLES (NEW)
-- ============================================================

-- Users table (for authentication and user info)
CREATE TABLE IF NOT EXISTS users (
    user_id VARCHAR PRIMARY KEY,
    username VARCHAR UNIQUE NOT NULL,
    email VARCHAR UNIQUE,
    password_hash VARCHAR NOT NULL,
    company_id VARCHAR,                    -- For multi-tenant isolation
    is_active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Groups table (for organizing users)
CREATE TABLE IF NOT EXISTS groups (
    group_id VARCHAR PRIMARY KEY,
    group_name VARCHAR NOT NULL,
    company_id VARCHAR NOT NULL,           -- Groups belong to companies
    description TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(group_name, company_id)
);

-- User-Group membership table (many-to-many)
CREATE TABLE IF NOT EXISTS user_groups (
    user_id VARCHAR NOT NULL,
    group_id VARCHAR NOT NULL,
    added_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    added_by VARCHAR,
    PRIMARY KEY (user_id, group_id),
    FOREIGN KEY (user_id) REFERENCES users(user_id) ON DELETE CASCADE,
    FOREIGN KEY (group_id) REFERENCES groups(group_id) ON DELETE CASCADE
);

-- Unified resources table (tracks ALL resources for permissions)
CREATE TABLE IF NOT EXISTS resources (
    resource_id VARCHAR PRIMARY KEY,       -- Can be agent_id, tool_id, layout_id, etc.
    resource_type VARCHAR NOT NULL,        -- 'agent', 'tool', 'gui_module', 'page_layout', 'file', 'chat'
    owner_id VARCHAR NOT NULL,             -- User who created/owns it
    company_id VARCHAR,                    -- For multi-tenant isolation
    visibility VARCHAR DEFAULT 'private',  -- 'private', 'group', 'company', 'public'
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (owner_id) REFERENCES users(user_id) ON DELETE CASCADE
);

-- Resource permissions table (who can access what)
CREATE TABLE IF NOT EXISTS resource_permissions (
    permission_id VARCHAR PRIMARY KEY,
    resource_id VARCHAR NOT NULL,
    entity_type VARCHAR NOT NULL,          -- 'user' or 'group'
    entity_id VARCHAR NOT NULL,            -- user_id or group_id
    permission_level VARCHAR NOT NULL,     -- 'read', 'write', 'admin'
    granted_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    granted_by VARCHAR,                    -- User who granted permission
    expires_at TIMESTAMP,                  -- Optional: permission expiry
    FOREIGN KEY (resource_id) REFERENCES resources(resource_id) ON DELETE CASCADE,
    UNIQUE(resource_id, entity_type, entity_id)
);

-- Audit log table (track all permission changes and access)
CREATE TABLE IF NOT EXISTS audit_log (
    id SERIAL PRIMARY KEY,
    user_id VARCHAR,
    action VARCHAR NOT NULL,               -- 'create', 'read', 'update', 'delete', 'share', 'access'
    resource_type VARCHAR NOT NULL,
    resource_id VARCHAR,
    details JSONB,                         -- Additional context
    ip_address VARCHAR,
    user_agent TEXT,
    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- ============================================================
-- INDEXES FOR PERFORMANCE
-- ============================================================

-- Indexes for agents
CREATE INDEX IF NOT EXISTS idx_agents_user ON agents(user_id);
CREATE INDEX IF NOT EXISTS idx_agents_name ON agents(name);
CREATE INDEX IF NOT EXISTS idx_agents_display ON agents(display_name);

-- Indexes for tools
CREATE INDEX IF NOT EXISTS idx_tools_user ON tools(user_id);
CREATE INDEX IF NOT EXISTS idx_tools_name ON tools(name);
CREATE INDEX IF NOT EXISTS idx_tools_module ON tools(api_module);

-- Indexes for agent_instances
CREATE INDEX IF NOT EXISTS idx_instances_agent ON agent_instances(agent_id);
CREATE INDEX IF NOT EXISTS idx_instances_user ON agent_instances(user_id);
CREATE INDEX IF NOT EXISTS idx_instances_status ON agent_instances(status);

-- Indexes for gui_modules
CREATE INDEX IF NOT EXISTS idx_gui_modules_type ON gui_modules(module_type);
CREATE INDEX IF NOT EXISTS idx_gui_modules_category ON gui_modules(category);
CREATE INDEX IF NOT EXISTS idx_gui_modules_user ON gui_modules(user_id);

-- Indexes for page_layouts
CREATE INDEX IF NOT EXISTS idx_page_layouts_name ON page_layouts(page_name);
CREATE INDEX IF NOT EXISTS idx_page_layouts_published ON page_layouts(is_published);
CREATE INDEX IF NOT EXISTS idx_page_layouts_created_by ON page_layouts(created_by);

-- Indexes for users
CREATE INDEX IF NOT EXISTS idx_users_company ON users(company_id);
CREATE INDEX IF NOT EXISTS idx_users_username ON users(username);
CREATE INDEX IF NOT EXISTS idx_users_email ON users(email);

-- Indexes for groups
CREATE INDEX IF NOT EXISTS idx_groups_company ON groups(company_id);

-- Indexes for resources (CRITICAL for performance)
CREATE INDEX IF NOT EXISTS idx_resources_type ON resources(resource_type);
CREATE INDEX IF NOT EXISTS idx_resources_owner ON resources(owner_id);
CREATE INDEX IF NOT EXISTS idx_resources_company ON resources(company_id);
CREATE INDEX IF NOT EXISTS idx_resources_visibility ON resources(visibility);
CREATE INDEX IF NOT EXISTS idx_resources_type_owner ON resources(resource_type, owner_id);

-- Indexes for permissions (CRITICAL for permission checks)
CREATE INDEX IF NOT EXISTS idx_permissions_resource ON resource_permissions(resource_id);
CREATE INDEX IF NOT EXISTS idx_permissions_entity ON resource_permissions(entity_type, entity_id);
CREATE INDEX IF NOT EXISTS idx_permissions_level ON resource_permissions(permission_level);

-- Indexes for audit log
CREATE INDEX IF NOT EXISTS idx_audit_user ON audit_log(user_id);
CREATE INDEX IF NOT EXISTS idx_audit_resource ON audit_log(resource_type, resource_id);
CREATE INDEX IF NOT EXISTS idx_audit_timestamp ON audit_log(timestamp);

-- ============================================================
-- ROW LEVEL SECURITY (RLS) - Optional but recommended
-- ============================================================

-- Enable RLS on sensitive tables
ALTER TABLE agents ENABLE ROW LEVEL SECURITY;
ALTER TABLE tools ENABLE ROW LEVEL SECURITY;
ALTER TABLE page_layouts ENABLE ROW LEVEL SECURITY;

-- Policy: Users can see their own resources + resources shared with them
-- This will be enforced by setting session variable app.current_user_id
CREATE POLICY agents_access_policy ON agents
    FOR ALL
    USING (
        user_id = current_setting('app.current_user_id', true)
        OR id IN (
            SELECT r.resource_id FROM resources r
            LEFT JOIN resource_permissions rp ON r.resource_id = rp.resource_id
            WHERE r.resource_type = 'agent'
            AND (
                r.visibility = 'public'
                OR (rp.entity_type = 'user' AND rp.entity_id = current_setting('app.current_user_id', true))
            )
        )
    );

CREATE POLICY tools_access_policy ON tools
    FOR ALL
    USING (
        user_id = current_setting('app.current_user_id', true)
        OR user_id = 'system'  -- System tools are always accessible
    );

CREATE POLICY layouts_access_policy ON page_layouts
    FOR ALL
    USING (
        created_by = current_setting('app.current_user_id', true)
        OR is_published = true
    );

-- ============================================================
-- HELPER FUNCTIONS
-- ============================================================

-- Function to check if user has permission to access resource
CREATE OR REPLACE FUNCTION has_resource_permission(
    p_user_id VARCHAR,
    p_resource_id VARCHAR,
    p_required_permission VARCHAR  -- 'read', 'write', 'admin'
)
RETURNS BOOLEAN AS $$
DECLARE
    v_owner_id VARCHAR;
    v_visibility VARCHAR;
    v_company_id VARCHAR;
    v_user_company VARCHAR;
    v_user_groups VARCHAR[];
    v_has_permission BOOLEAN := FALSE;
BEGIN
    -- Get resource info
    SELECT owner_id, visibility, company_id INTO v_owner_id, v_visibility, v_company_id
    FROM resources WHERE resource_id = p_resource_id;

    -- Resource not found
    IF NOT FOUND THEN
        RETURN FALSE;
    END IF;

    -- Owner has all permissions
    IF v_owner_id = p_user_id THEN
        RETURN TRUE;
    END IF;

    -- Public resources (read-only)
    IF v_visibility = 'public' AND p_required_permission = 'read' THEN
        RETURN TRUE;
    END IF;

    -- Get user's company and groups
    SELECT company_id INTO v_user_company FROM users WHERE user_id = p_user_id;
    SELECT ARRAY_AGG(group_id) INTO v_user_groups FROM user_groups WHERE user_id = p_user_id;

    -- Company-level access
    IF v_visibility = 'company' AND v_company_id = v_user_company THEN
        RETURN TRUE;
    END IF;

    -- Check explicit permissions
    SELECT EXISTS(
        SELECT 1 FROM resource_permissions
        WHERE resource_id = p_resource_id
        AND (
            (entity_type = 'user' AND entity_id = p_user_id)
            OR (entity_type = 'group' AND entity_id = ANY(v_user_groups))
        )
        AND (
            permission_level = 'admin'
            OR (permission_level = 'write' AND p_required_permission IN ('read', 'write'))
            OR (permission_level = 'read' AND p_required_permission = 'read')
        )
        AND (expires_at IS NULL OR expires_at > NOW())
    ) INTO v_has_permission;

    RETURN v_has_permission;
END;
$$ LANGUAGE plpgsql;

-- Grant permissions
GRANT ALL PRIVILEGES ON ALL TABLES IN SCHEMA public TO finbuddy_app;
GRANT ALL PRIVILEGES ON ALL SEQUENCES IN SCHEMA public TO finbuddy_app;
GRANT EXECUTE ON ALL FUNCTIONS IN SCHEMA public TO finbuddy_app;

-- ============================================================
-- RESOURCE-SPECIFIC METADATA TABLES
-- ============================================================

-- File metadata
CREATE TABLE IF NOT EXISTS file_metadata (
    file_id VARCHAR PRIMARY KEY REFERENCES resources(resource_id) ON DELETE CASCADE,
    s3_path VARCHAR NOT NULL,
    filename VARCHAR NOT NULL,
    file_size BIGINT,
    mime_type VARCHAR,
    checksum VARCHAR,
    version INTEGER DEFAULT 1,  -- Current version number
    uploaded_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- File versions history (track all changes)
CREATE TABLE IF NOT EXISTS file_versions (
    version_id VARCHAR PRIMARY KEY,
    file_id VARCHAR REFERENCES resources(resource_id) ON DELETE CASCADE,
    version_number INTEGER NOT NULL,
    s3_path VARCHAR NOT NULL,  -- Path to this version
    file_size BIGINT,
    checksum VARCHAR,
    uploaded_by VARCHAR,
    uploaded_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    change_description TEXT,
    UNIQUE(file_id, version_number)
);

CREATE INDEX IF NOT EXISTS idx_file_versions_file ON file_versions(file_id);

-- Directory structure (linking files to directories)
CREATE TABLE IF NOT EXISTS directory_contents (
    directory_id VARCHAR REFERENCES resources(resource_id) ON DELETE CASCADE,
    file_id VARCHAR REFERENCES resources(resource_id) ON DELETE CASCADE,
    added_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    added_by VARCHAR,
    PRIMARY KEY (directory_id, file_id)
);

-- Chat metadata
CREATE TABLE IF NOT EXISTS chat_metadata (
    chat_id VARCHAR PRIMARY KEY REFERENCES resources(resource_id) ON DELETE CASCADE,
    title VARCHAR NOT NULL,
    agent_id VARCHAR REFERENCES agents(id) ON DELETE SET NULL,
    message_count INTEGER DEFAULT 0,
    s3_prefix VARCHAR,  -- Where message files are stored
    last_message_at TIMESTAMP,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Compute resources metadata
CREATE TABLE IF NOT EXISTS compute_resources (
    compute_id VARCHAR PRIMARY KEY REFERENCES resources(resource_id) ON DELETE CASCADE,
    resource_name VARCHAR NOT NULL,
    instance_type VARCHAR,  -- e.g., 'n1-highmem-8', 'db.t3.micro'
    status VARCHAR DEFAULT 'stopped',  -- 'running', 'stopped', 'error', 'provisioning'
    cloud_provider VARCHAR,  -- 'gcp', 'aws', 'local'
    cloud_instance_id VARCHAR,  -- Cloud provider's instance ID
    endpoint VARCHAR,  -- Access URL/IP
    region VARCHAR,
    cost_per_hour DECIMAL(10,4),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    started_at TIMESTAMP,
    stopped_at TIMESTAMP
);

-- ============================================================
-- RESOURCE COLLECTIONS (Generic Groups)
-- ============================================================

-- Resource collections table (portfolios, projects, bundles, etc.)
CREATE TABLE IF NOT EXISTS resource_collections (
    collection_id VARCHAR PRIMARY KEY REFERENCES resources(resource_id) ON DELETE CASCADE,
    collection_type VARCHAR NOT NULL,  -- 'portfolio', 'project', 'bundle', 'dataset', etc.
    name VARCHAR NOT NULL,
    description TEXT,
    metadata JSONB,  -- Flexible storage for type-specific data
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Collection membership (which resources belong to which collections)
CREATE TABLE IF NOT EXISTS collection_members (
    collection_id VARCHAR REFERENCES resource_collections(collection_id) ON DELETE CASCADE,
    member_resource_id VARCHAR REFERENCES resources(resource_id) ON DELETE CASCADE,
    member_order INTEGER DEFAULT 0,  -- For ordered collections
    added_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    added_by VARCHAR,
    metadata JSONB,  -- Member-specific metadata (e.g., role in portfolio)
    PRIMARY KEY (collection_id, member_resource_id)
);

-- Additional indexes for metadata tables
CREATE INDEX IF NOT EXISTS idx_file_metadata_filename ON file_metadata(filename);
CREATE INDEX IF NOT EXISTS idx_file_metadata_s3_path ON file_metadata(s3_path);
CREATE INDEX IF NOT EXISTS idx_directory_contents_file ON directory_contents(file_id);
CREATE INDEX IF NOT EXISTS idx_chat_metadata_agent ON chat_metadata(agent_id);
CREATE INDEX IF NOT EXISTS idx_compute_resources_status ON compute_resources(status);
CREATE INDEX IF NOT EXISTS idx_resource_collections_type ON resource_collections(collection_type);
CREATE INDEX IF NOT EXISTS idx_collection_members_resource ON collection_members(member_resource_id);

-- ============================================================
-- DATA QUERIES TABLE (for Dispatcher system)
-- ============================================================

-- Data queries table (stores translated queries for dispatcher)
CREATE TABLE IF NOT EXISTS data_queries (
    query_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),

    -- Query content
    natural_language_request TEXT NOT NULL,    -- Original user request
    duckdb_sql TEXT,                            -- Generated SQL query (NULL for pass_through)

    -- Linked datasets (array for multi-dataset support)
    dataset_names TEXT[] NOT NULL,              -- ['equity_db'] or ['equity_db', 'bonds_db']

    -- Event types (WHEN to fire - batch events like 'eod_usa', 'news_update', 'macro_release')
    -- If empty, trigger matches by dataset_name only (backwards compatible)
    event_types TEXT[] DEFAULT '{}',            -- ['eod_usa'] or ['news_update', 'macro_release']

    -- Ownership
    owner_id VARCHAR NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
    company_id VARCHAR,

    -- Query type
    query_type VARCHAR DEFAULT 'trigger',       -- 'trigger' (runs on new data) or 'one_time'
    is_active BOOLEAN DEFAULT TRUE,             -- Can be disabled without deleting

    -- Notification target (where to send results)
    notify_type VARCHAR,                        -- 'user', 'agent', 'webhook'
    notify_target VARCHAR,                      -- user_id, agent_instance_id, or webhook URL

    -- Session tracking (for agent notifications to continue existing chat)
    session_id VARCHAR,                         -- Chat session ID (NULL for user notifications)

    -- Trigger chain configuration
    chain_type VARCHAR(50) DEFAULT 'query_only',  -- 'pass_through', 'query_only', 'query_plus_analysis'
    analysis_enabled BOOLEAN DEFAULT FALSE,       -- Whether to run LLM analysis on results
    analysis_prompt TEXT,                         -- LLM instruction for analyzing query results
    analysis_model VARCHAR(100) DEFAULT 'openrouter:anthropic/claude-sonnet-4',  -- LLM model to use

    -- Metadata
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    last_run_at TIMESTAMP,                      -- When dispatcher last ran this query
    run_count INTEGER DEFAULT 0,                -- How many times it has been executed

    -- Constraint for valid chain_type values
    CONSTRAINT valid_chain_type CHECK (chain_type IN ('pass_through', 'query_only', 'query_plus_analysis'))
);

-- Indexes for dispatcher: find queries by dataset or event_type
CREATE INDEX IF NOT EXISTS idx_queries_by_dataset ON data_queries USING GIN (dataset_names);
CREATE INDEX IF NOT EXISTS idx_queries_by_event_type ON data_queries USING GIN (event_types);
CREATE INDEX IF NOT EXISTS idx_queries_active ON data_queries (is_active) WHERE is_active = TRUE;
CREATE INDEX IF NOT EXISTS idx_queries_owner ON data_queries (owner_id);
CREATE INDEX IF NOT EXISTS idx_queries_type ON data_queries (query_type);
CREATE INDEX IF NOT EXISTS idx_queries_session ON data_queries (session_id) WHERE session_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_queries_chain_type ON data_queries (chain_type);

-- Grant permissions on new table
GRANT ALL PRIVILEGES ON data_queries TO finbuddy_app;

-- ============================================================
-- NOTIFICATIONS TABLE (for Dispatcher query results)
-- ============================================================

-- Notifications table (stores results when dispatcher runs queries)
CREATE TABLE IF NOT EXISTS notifications (
    id SERIAL PRIMARY KEY,
    query_id UUID NOT NULL REFERENCES data_queries(query_id) ON DELETE CASCADE,

    -- Notification content
    message TEXT NOT NULL DEFAULT 'Query executed',
    row_count INTEGER DEFAULT 0,
    data_json JSONB,                          -- Query result data (limited rows for display)

    -- Status
    is_read BOOLEAN DEFAULT FALSE,

    -- Metadata
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    dataset_name VARCHAR                       -- Which dataset triggered this notification
);

-- Indexes for notifications
CREATE INDEX IF NOT EXISTS idx_notifications_query ON notifications(query_id);
CREATE INDEX IF NOT EXISTS idx_notifications_created ON notifications(created_at DESC);
CREATE INDEX IF NOT EXISTS idx_notifications_unread ON notifications(query_id, is_read) WHERE is_read = FALSE;

-- Grant permissions on notifications table
GRANT ALL PRIVILEGES ON notifications TO finbuddy_app;
GRANT USAGE, SELECT ON SEQUENCE notifications_id_seq TO finbuddy_app;

-- ============================================================
-- PENDING VERIFICATIONS TABLE (for Email Signup Verification)
-- ============================================================

-- Pending verifications table (stores email verification codes during signup)
CREATE TABLE IF NOT EXISTS pending_verifications (
    id SERIAL PRIMARY KEY,
    email VARCHAR UNIQUE NOT NULL,
    verification_code VARCHAR(6) NOT NULL,
    attempts INTEGER DEFAULT 0,              -- Failed verification attempts
    resend_count INTEGER DEFAULT 0,          -- How many times code was resent
    last_resend_at TIMESTAMP,                -- For rate limiting resends
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    expires_at TIMESTAMP NOT NULL            -- Code expiration (e.g., 15 min from creation)
);

-- Index for cleanup of expired verifications
CREATE INDEX IF NOT EXISTS idx_pending_verifications_expires ON pending_verifications(expires_at);
CREATE INDEX IF NOT EXISTS idx_pending_verifications_email ON pending_verifications(email);

-- Grant permissions on pending_verifications table
GRANT ALL PRIVILEGES ON pending_verifications TO finbuddy_app;
GRANT USAGE, SELECT ON SEQUENCE pending_verifications_id_seq TO finbuddy_app;

-- ============================================================
-- TRADING AGENT TABLES
-- ============================================================

-- Trading portfolios - Master portfolio records for trading system
CREATE TABLE IF NOT EXISTS trading_portfolios (
    portfolio_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id VARCHAR(255) NOT NULL,
    name VARCHAR(255) NOT NULL,
    description TEXT,

    -- Portfolio type
    portfolio_type VARCHAR(50) DEFAULT 'equity',       -- 'equity', 'multi_asset'
    portfolio_mode VARCHAR(20) DEFAULT 'discretionary', -- 'discretionary', 'systematic', 'hybrid'

    -- NAV tracking
    base_currency VARCHAR(10) DEFAULT 'USD',
    initial_nav DECIMAL(20,2),
    current_nav DECIMAL(20,2),
    current_cash DECIMAL(20,2) DEFAULT 0,

    -- Benchmark
    benchmark VARCHAR(50),

    -- Link to equity_analyst CSV files (source of initial portfolio)
    equity_portfolio_name VARCHAR(255),  -- e.g., "portfolio_20250418_121911"

    -- Timestamps
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW(),
    last_rebalance_at TIMESTAMP,

    -- Status
    is_active BOOLEAN DEFAULT TRUE,
    status VARCHAR(20) DEFAULT 'backtest',    -- 'live', 'paused', 'backtest' - protects portfolios from backtest modifications

    UNIQUE(user_id, name),
    CONSTRAINT chk_portfolio_status CHECK (status IN ('live', 'paused', 'backtest'))
);

CREATE INDEX IF NOT EXISTS idx_trading_portfolios_user ON trading_portfolios(user_id);
CREATE INDEX IF NOT EXISTS idx_trading_portfolios_mode ON trading_portfolios(portfolio_mode);
CREATE INDEX IF NOT EXISTS idx_trading_portfolios_active ON trading_portfolios(is_active) WHERE is_active = TRUE;
CREATE INDEX IF NOT EXISTS idx_trading_portfolios_status ON trading_portfolios(status);
CREATE INDEX IF NOT EXISTS idx_trading_portfolios_user_status ON trading_portfolios(user_id, status);

-- Positions table (THE source of truth for current holdings)
CREATE TABLE IF NOT EXISTS positions (
    id SERIAL PRIMARY KEY,
    portfolio_id UUID NOT NULL REFERENCES trading_portfolios(portfolio_id) ON DELETE CASCADE,

    -- Instrument identification
    ticker VARCHAR(50) NOT NULL,
    instrument_type VARCHAR(20) DEFAULT 'equity',      -- 'equity', 'etf', 'bond', etc.

    -- Position data
    quantity DECIMAL(20,6) NOT NULL DEFAULT 0,
    avg_cost DECIMAL(20,6),                            -- Average cost basis
    current_price DECIMAL(20,6),                       -- Latest price

    -- Calculated fields (updated by position_manager)
    notional DECIMAL(20,2),                            -- quantity * current_price
    weight DECIMAL(10,6),                              -- Position weight in portfolio
    unrealized_pnl DECIMAL(20,2),                      -- (current_price - avg_cost) * quantity

    -- Metadata
    sector VARCHAR(100),

    -- Timestamps
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW(),

    UNIQUE(portfolio_id, ticker)
);

CREATE INDEX IF NOT EXISTS idx_positions_portfolio ON positions(portfolio_id);
CREATE INDEX IF NOT EXISTS idx_positions_ticker ON positions(ticker);
CREATE INDEX IF NOT EXISTS idx_positions_sector ON positions(sector);

-- Transactions table (Trade history)
CREATE TABLE IF NOT EXISTS transactions (
    transaction_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    portfolio_id UUID NOT NULL REFERENCES trading_portfolios(portfolio_id) ON DELETE CASCADE,
    decision_id UUID,                                  -- FK to decision_log (optional)

    -- Instrument
    ticker VARCHAR(50) NOT NULL,
    instrument_type VARCHAR(20) DEFAULT 'equity',

    -- Transaction details
    transaction_type VARCHAR(20) NOT NULL,             -- 'buy', 'sell', 'dividend', 'rebalance'
    quantity DECIMAL(20,6) NOT NULL,
    price DECIMAL(20,6) NOT NULL,
    amount DECIMAL(20,2) NOT NULL,                     -- quantity * price
    fees DECIMAL(20,2) DEFAULT 0,

    -- Execution info
    executed_at TIMESTAMP NOT NULL DEFAULT NOW(),

    -- Notes
    notes TEXT,

    -- Timestamps
    created_at TIMESTAMP DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_transactions_portfolio ON transactions(portfolio_id, executed_at DESC);
CREATE INDEX IF NOT EXISTS idx_transactions_ticker ON transactions(ticker, executed_at DESC);
CREATE INDEX IF NOT EXISTS idx_transactions_decision ON transactions(decision_id);
CREATE INDEX IF NOT EXISTS idx_transactions_type ON transactions(transaction_type);

-- Decision log table (Audit trail)
CREATE TABLE IF NOT EXISTS decision_log (
    decision_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    portfolio_id UUID REFERENCES trading_portfolios(portfolio_id) ON DELETE SET NULL,
    user_id VARCHAR(255) NOT NULL,

    -- Decision source
    strategist_type VARCHAR(50) NOT NULL,              -- 'macro_strategist', 'equity_analyst', 'user_override', 'system'
    source VARCHAR(50) NOT NULL,                       -- 'fed_minutes', 'user_chat', 'rebalance', 'sync'
    source_content TEXT,                               -- Fed text excerpt, user command, etc.
    source_metadata JSONB,                             -- {fed_date, chat_id, etc.}

    -- Decision details
    action VARCHAR(50) NOT NULL,                       -- 'create_portfolio', 'sync_positions', 'buy', 'sell', 'rebalance'
    rationale TEXT,

    -- Target state (what the decision aims for)
    target_weights JSONB,                              -- {"AAPL": 0.05, "MSFT": 0.04}
    target_positions JSONB,                            -- [{"ticker": "AAPL", "qty": 100}, ...]

    -- Execution results
    executed_trades JSONB,                             -- [{"ticker": "AAPL", "qty": 100, "price": 175}]
    execution_status VARCHAR(20) DEFAULT 'pending',    -- 'pending', 'complete', 'partial', 'failed'
    execution_error TEXT,

    -- Context
    chat_session_id VARCHAR(255),

    -- Timestamps
    created_at TIMESTAMP DEFAULT NOW(),
    executed_at TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_decision_portfolio ON decision_log(portfolio_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_decision_user ON decision_log(user_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_decision_source ON decision_log(source, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_decision_strategist ON decision_log(strategist_type);
CREATE INDEX IF NOT EXISTS idx_decision_status ON decision_log(execution_status);

-- Portfolio MTM (Mark-to-Market) daily tracking
CREATE TABLE IF NOT EXISTS portfolio_mtm (
    id SERIAL PRIMARY KEY,
    portfolio_id UUID NOT NULL REFERENCES trading_portfolios(portfolio_id) ON DELETE CASCADE,
    date DATE NOT NULL,

    -- NAV and notional values
    total_nav DECIMAL(18,2),
    stock_notional DECIMAL(18,2),
    cash_balance DECIMAL(18,2),
    long_notional DECIMAL(18,2),
    short_notional DECIMAL(18,2),

    -- Returns
    daily_return DECIMAL(12,8),
    cum_return DECIMAL(12,8),

    -- Dividends
    net_dividend DECIMAL(18,2) DEFAULT 0,
    cum_dividend DECIMAL(18,2) DEFAULT 0,

    -- Metadata
    price_date DATE,
    created_at TIMESTAMP DEFAULT NOW(),

    UNIQUE(portfolio_id, date)
);

CREATE INDEX IF NOT EXISTS idx_portfolio_mtm_portfolio_date ON portfolio_mtm(portfolio_id, date DESC);

-- Portfolio Constraints table (sector constraints for live trading)
CREATE TABLE IF NOT EXISTS portfolio_constraints (
    id SERIAL PRIMARY KEY,
    portfolio_id UUID NOT NULL REFERENCES trading_portfolios(portfolio_id) ON DELETE CASCADE,
    sector VARCHAR(100) NOT NULL,
    constraint_type VARCHAR(20) NOT NULL,  -- 'overweight', 'underweight', 'fixed'
    value DECIMAL(10,6) NOT NULL,
    source VARCHAR(50) NOT NULL,           -- 'user_chat', 'eq_analyst'
    source_file VARCHAR(500),              -- eq_analyst file path if applicable
    decision_id UUID,                      -- Links to decision_log entry that LAST set this constraint
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW(),
    UNIQUE(portfolio_id, sector),          -- Only ONE active constraint per sector per portfolio
    CONSTRAINT chk_constraint_type CHECK (constraint_type IN ('overweight', 'underweight', 'fixed')),
    CONSTRAINT chk_source CHECK (source IN ('user_chat', 'eq_analyst'))
);

CREATE INDEX IF NOT EXISTS idx_portfolio_constraints_portfolio ON portfolio_constraints(portfolio_id);

-- Grant permissions on trading tables
GRANT ALL PRIVILEGES ON trading_portfolios TO finbuddy_app;
GRANT ALL PRIVILEGES ON positions TO finbuddy_app;
GRANT ALL PRIVILEGES ON transactions TO finbuddy_app;
GRANT ALL PRIVILEGES ON decision_log TO finbuddy_app;
GRANT ALL PRIVILEGES ON portfolio_mtm TO finbuddy_app;
GRANT ALL PRIVILEGES ON portfolio_constraints TO finbuddy_app;
GRANT USAGE, SELECT ON SEQUENCE positions_id_seq TO finbuddy_app;
GRANT USAGE, SELECT ON SEQUENCE portfolio_mtm_id_seq TO finbuddy_app;
GRANT USAGE, SELECT ON SEQUENCE portfolio_constraints_id_seq TO finbuddy_app;

-- Success message
DO $$
BEGIN
    RAISE NOTICE '✅ finbuddy database initialized with role-based access control and trading tables';
END $$;
