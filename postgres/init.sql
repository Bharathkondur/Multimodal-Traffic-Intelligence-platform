-- Create extensions
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
-- CREATE EXTENSION IF NOT EXISTS "postgis"; -- requires postgis image
CREATE EXTENSION IF NOT EXISTS "hstore";

-- Create schemas
CREATE SCHEMA IF NOT EXISTS traffic;

-- Users and Sessions table
CREATE TABLE IF NOT EXISTS traffic.users (
    user_id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    username VARCHAR(255) UNIQUE NOT NULL,
    email VARCHAR(255) UNIQUE NOT NULL,
    password_hash VARCHAR(255) NOT NULL,
    role VARCHAR(50) DEFAULT 'user',
    is_active BOOLEAN DEFAULT true,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Sessions table
CREATE TABLE IF NOT EXISTS traffic.sessions (
    session_id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id UUID REFERENCES traffic.users(user_id),
    source VARCHAR(255),
    source_type VARCHAR(50), -- 'camera', 'video_file', 'stream'
    status VARCHAR(50) DEFAULT 'active', -- 'active', 'paused', 'completed', 'failed'
    vehicle_count INTEGER DEFAULT 0,
    incident_count INTEGER DEFAULT 0,
    start_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    end_time TIMESTAMP,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT status_check CHECK (status IN ('active', 'paused', 'completed', 'failed'))
);

-- Detections table
CREATE TABLE IF NOT EXISTS traffic.detections (
    detection_id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    session_id UUID REFERENCES traffic.sessions(session_id) ON DELETE CASCADE,
    frame_number INTEGER,
    vehicle_type VARCHAR(50), -- 'car', 'truck', 'bus', 'motorcycle', 'bicycle', 'pedestrian'
    confidence DECIMAL(5, 4),
    bbox_x DECIMAL(10, 2),
    bbox_y DECIMAL(10, 2),
    bbox_width DECIMAL(10, 2),
    bbox_height DECIMAL(10, 2),
    speed DECIMAL(8, 2),
    direction VARCHAR(50),
    location VARCHAR(255),
    plate_number VARCHAR(50),
    metadata JSONB,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT vehicle_type_check CHECK (vehicle_type IN ('car', 'truck', 'bus', 'motorcycle', 'bicycle', 'pedestrian', 'unknown'))
);

-- Incidents table
CREATE TABLE IF NOT EXISTS traffic.incidents (
    incident_id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    session_id UUID REFERENCES traffic.sessions(session_id) ON DELETE CASCADE,
    incident_type VARCHAR(100), -- 'collision', 'congestion', 'wrong_way', 'stopped_vehicle', 'accident'
    severity VARCHAR(50), -- 'low', 'medium', 'high', 'critical'
    location VARCHAR(255),
    description TEXT,
    detection_ids UUID[] DEFAULT '{}',
    resolved BOOLEAN DEFAULT false,
    resolution_notes TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT severity_check CHECK (severity IN ('low', 'medium', 'high', 'critical'))
);

-- Traffic flow table
CREATE TABLE IF NOT EXISTS traffic.traffic_flow (
    flow_id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    session_id UUID REFERENCES traffic.sessions(session_id) ON DELETE CASCADE,
    time_window TIMESTAMP,
    location VARCHAR(255),
    vehicle_count INTEGER DEFAULT 0,
    speed DECIMAL(8, 2),
    congestion_level VARCHAR(50), -- 'free', 'light', 'moderate', 'heavy'
    flow_direction VARCHAR(50),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT congestion_check CHECK (congestion_level IN ('free', 'light', 'moderate', 'heavy'))
);

-- Alerts table
CREATE TABLE IF NOT EXISTS traffic.alerts (
    alert_id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    incident_id UUID REFERENCES traffic.incidents(incident_id) ON DELETE CASCADE,
    alert_type VARCHAR(100),
    message TEXT,
    is_sent BOOLEAN DEFAULT false,
    sent_to TEXT[] DEFAULT '{}',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Analytics table
CREATE TABLE IF NOT EXISTS traffic.analytics (
    analytics_id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    session_id UUID REFERENCES traffic.sessions(session_id) ON DELETE CASCADE,
    metric_name VARCHAR(255),
    metric_value DECIMAL(15, 4),
    metric_timestamp TIMESTAMP,
    tags JSONB,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Create indexes for better query performance
CREATE INDEX idx_sessions_user_id ON traffic.sessions(user_id);
CREATE INDEX idx_sessions_status ON traffic.sessions(status);
CREATE INDEX idx_sessions_created_at ON traffic.sessions(created_at);
CREATE INDEX idx_detections_session_id ON traffic.detections(session_id);
CREATE INDEX idx_detections_created_at ON traffic.detections(created_at);
CREATE INDEX idx_detections_confidence ON traffic.detections(confidence);
CREATE INDEX idx_detections_vehicle_type ON traffic.detections(vehicle_type);
CREATE INDEX idx_incidents_session_id ON traffic.incidents(session_id);
CREATE INDEX idx_incidents_created_at ON traffic.incidents(created_at);
CREATE INDEX idx_incidents_severity ON traffic.incidents(severity);
CREATE INDEX idx_traffic_flow_session_id ON traffic.traffic_flow(session_id);
CREATE INDEX idx_traffic_flow_location ON traffic.traffic_flow(location);
CREATE INDEX idx_traffic_flow_created_at ON traffic.traffic_flow(created_at);
CREATE INDEX idx_alerts_incident_id ON traffic.alerts(incident_id);
CREATE INDEX idx_alerts_created_at ON traffic.alerts(created_at);
CREATE INDEX idx_analytics_session_id ON traffic.analytics(session_id);
CREATE INDEX idx_analytics_metric_name ON traffic.analytics(metric_name);

-- Create views for common queries
CREATE OR REPLACE VIEW traffic.active_sessions_view AS
SELECT
    s.session_id,
    s.user_id,
    s.source,
    s.vehicle_count,
    s.incident_count,
    s.start_time,
    COUNT(DISTINCT d.detection_id) as detection_count,
    COUNT(DISTINCT i.incident_id) as incident_count_actual
FROM traffic.sessions s
LEFT JOIN traffic.detections d ON s.session_id = d.session_id
LEFT JOIN traffic.incidents i ON s.session_id = i.session_id
WHERE s.status = 'active'
GROUP BY s.session_id, s.user_id, s.source, s.vehicle_count, s.incident_count, s.start_time;

CREATE OR REPLACE VIEW traffic.incident_summary_view AS
SELECT
    severity,
    COUNT(*) as count,
    AVG(EXTRACT(EPOCH FROM (COALESCE(updated_at, CURRENT_TIMESTAMP) - created_at))) as avg_resolution_time
FROM traffic.incidents
GROUP BY severity;

-- Create roles and permissions
CREATE ROLE traffic_admin WITH LOGIN PASSWORD 'admin_password_change_me';
CREATE ROLE traffic_user WITH LOGIN PASSWORD 'user_password_change_me';
CREATE ROLE traffic_readonly WITH LOGIN PASSWORD 'readonly_password_change_me';

-- Grant permissions
GRANT USAGE ON SCHEMA traffic TO traffic_admin, traffic_user, traffic_readonly;
GRANT ALL PRIVILEGES ON ALL TABLES IN SCHEMA traffic TO traffic_admin;
GRANT ALL PRIVILEGES ON ALL SEQUENCES IN SCHEMA traffic TO traffic_admin;
GRANT SELECT, INSERT, UPDATE ON ALL TABLES IN SCHEMA traffic TO traffic_user;
GRANT SELECT ON ALL TABLES IN SCHEMA traffic TO traffic_readonly;

-- Function to update updated_at timestamp
CREATE OR REPLACE FUNCTION traffic.update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = CURRENT_TIMESTAMP;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- Triggers for updated_at
CREATE TRIGGER update_users_updated_at BEFORE UPDATE ON traffic.users
    FOR EACH ROW EXECUTE FUNCTION traffic.update_updated_at_column();

CREATE TRIGGER update_sessions_updated_at BEFORE UPDATE ON traffic.sessions
    FOR EACH ROW EXECUTE FUNCTION traffic.update_updated_at_column();

CREATE TRIGGER update_detections_updated_at BEFORE UPDATE ON traffic.detections
    FOR EACH ROW EXECUTE FUNCTION traffic.update_updated_at_column();

CREATE TRIGGER update_incidents_updated_at BEFORE UPDATE ON traffic.incidents
    FOR EACH ROW EXECUTE FUNCTION traffic.update_updated_at_column();

CREATE TRIGGER update_alerts_updated_at BEFORE UPDATE ON traffic.alerts
    FOR EACH ROW EXECUTE FUNCTION traffic.update_updated_at_column();
