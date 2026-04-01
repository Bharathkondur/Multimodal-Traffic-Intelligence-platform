-- PostgreSQL Database Schema for Multimodal Traffic Intelligence Platform
-- Includes tables, indexes, constraints, and materialized views for analytics

-- Create extensions if needed
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS "pg_trgm";  -- For full-text search support

-- Create ENUM types
CREATE TYPE source_type AS ENUM (
    'video_stream',
    'video_file',
    'camera_feed',
    'rtsp',
    'http_stream',
    'file_upload'
);

CREATE TYPE vehicle_type AS ENUM (
    'car',
    'truck',
    'bus',
    'motorcycle',
    'bicycle',
    'pedestrian',
    'van',
    'unknown'
);

CREATE TYPE incident_type AS ENUM (
    'collision',
    'congestion',
    'stalled_vehicle',
    'hazard',
    'unusual_activity',
    'weather_related',
    'infrastructure_damage',
    'other'
);

CREATE TYPE severity_level AS ENUM (
    'low',
    'medium',
    'high',
    'critical'
);

CREATE TYPE session_status AS ENUM (
    'active',
    'completed',
    'failed',
    'paused'
);

-- Traffic Sessions Table
CREATE TABLE traffic_sessions (
    id VARCHAR(36) PRIMARY KEY,
    start_time TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP,
    end_time TIMESTAMP WITH TIME ZONE,
    source_type source_type NOT NULL,
    source_url VARCHAR(500),
    status session_status NOT NULL DEFAULT 'active',
    metadata_json JSONB,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT end_time_after_start CHECK (end_time IS NULL OR end_time > start_time)
);

-- Create indexes for traffic_sessions
CREATE INDEX ix_traffic_sessions_start_time ON traffic_sessions(start_time);
CREATE INDEX ix_traffic_sessions_status ON traffic_sessions(status);
CREATE INDEX ix_traffic_sessions_source_type ON traffic_sessions(source_type);
CREATE INDEX ix_traffic_sessions_created_at ON traffic_sessions(created_at DESC);

-- Detection Events Table
CREATE TABLE detection_events (
    id SERIAL PRIMARY KEY,
    timestamp TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP,
    session_id VARCHAR(36) NOT NULL REFERENCES traffic_sessions(id) ON DELETE CASCADE,
    frame_number INTEGER NOT NULL,
    vehicle_type vehicle_type NOT NULL,
    confidence NUMERIC(5, 4) NOT NULL,
    track_id VARCHAR(36),
    bbox_x NUMERIC(5, 4) NOT NULL,
    bbox_y NUMERIC(5, 4) NOT NULL,
    bbox_w NUMERIC(5, 4) NOT NULL,
    bbox_h NUMERIC(5, 4) NOT NULL,
    speed_estimate FLOAT,
    direction VARCHAR(50),
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT confidence_range CHECK (confidence >= 0.0 AND confidence <= 1.0),
    CONSTRAINT bbox_x_range CHECK (bbox_x >= 0.0 AND bbox_x <= 1.0),
    CONSTRAINT bbox_y_range CHECK (bbox_y >= 0.0 AND bbox_y <= 1.0),
    CONSTRAINT bbox_w_range CHECK (bbox_w >= 0.0 AND bbox_w <= 1.0),
    CONSTRAINT bbox_h_range CHECK (bbox_h >= 0.0 AND bbox_h <= 1.0)
);

-- Create indexes for detection_events
CREATE INDEX ix_detection_events_session_id ON detection_events(session_id);
CREATE INDEX ix_detection_events_timestamp ON detection_events(timestamp DESC);
CREATE INDEX ix_detection_events_track_id ON detection_events(track_id);
CREATE INDEX ix_detection_events_vehicle_type ON detection_events(vehicle_type);
CREATE INDEX ix_detection_events_session_timestamp ON detection_events(session_id, timestamp DESC);
CREATE INDEX ix_detection_events_frame ON detection_events(session_id, frame_number);
CREATE INDEX ix_detection_events_confidence ON detection_events(confidence DESC);

-- Incident Events Table
CREATE TABLE incident_events (
    id SERIAL PRIMARY KEY,
    timestamp TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP,
    session_id VARCHAR(36) NOT NULL REFERENCES traffic_sessions(id) ON DELETE CASCADE,
    incident_type incident_type NOT NULL,
    severity severity_level NOT NULL DEFAULT 'medium',
    location_description VARCHAR(256),
    bbox JSONB,
    related_track_ids JSONB,
    resolved BOOLEAN NOT NULL DEFAULT FALSE,
    resolved_at TIMESTAMP WITH TIME ZONE,
    description TEXT,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT resolved_at_after_timestamp CHECK (resolved_at IS NULL OR resolved_at > timestamp)
);

-- Create indexes for incident_events
CREATE INDEX ix_incident_events_session_id ON incident_events(session_id);
CREATE INDEX ix_incident_events_timestamp ON incident_events(timestamp DESC);
CREATE INDEX ix_incident_events_incident_type ON incident_events(incident_type);
CREATE INDEX ix_incident_events_severity ON incident_events(severity);
CREATE INDEX ix_incident_events_resolved ON incident_events(resolved);
CREATE INDEX ix_incident_events_session_timestamp ON incident_events(session_id, timestamp DESC);
CREATE INDEX ix_incident_events_unresolved ON incident_events(resolved, severity) WHERE resolved = FALSE;

-- Vehicle Counts Table
CREATE TABLE vehicle_counts (
    id SERIAL PRIMARY KEY,
    session_id VARCHAR(36) NOT NULL REFERENCES traffic_sessions(id) ON DELETE CASCADE,
    timestamp TIMESTAMP WITH TIME ZONE NOT NULL,
    interval_seconds INTEGER NOT NULL DEFAULT 60,
    vehicle_type vehicle_type NOT NULL,
    count INTEGER NOT NULL DEFAULT 0 CHECK (count >= 0),
    direction VARCHAR(50),
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT interval_positive CHECK (interval_seconds > 0),
    UNIQUE(session_id, timestamp, vehicle_type, direction)
);

-- Create indexes for vehicle_counts
CREATE INDEX ix_vehicle_counts_session_id ON vehicle_counts(session_id);
CREATE INDEX ix_vehicle_counts_timestamp ON vehicle_counts(timestamp DESC);
CREATE INDEX ix_vehicle_counts_vehicle_type ON vehicle_counts(vehicle_type);
CREATE INDEX ix_vehicle_counts_session_timestamp ON vehicle_counts(session_id, timestamp DESC);
CREATE INDEX ix_vehicle_counts_interval ON vehicle_counts(interval_seconds);

-- Traffic Reports Table
CREATE TABLE traffic_reports (
    id SERIAL PRIMARY KEY,
    session_id VARCHAR(36) NOT NULL REFERENCES traffic_sessions(id) ON DELETE CASCADE,
    generated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP,
    report_type VARCHAR(50) NOT NULL,
    content JSONB NOT NULL,
    query_text TEXT,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT report_type_not_empty CHECK (length(report_type) > 0)
);

-- Create indexes for traffic_reports
CREATE INDEX ix_traffic_reports_session_id ON traffic_reports(session_id);
CREATE INDEX ix_traffic_reports_generated_at ON traffic_reports(generated_at DESC);
CREATE INDEX ix_traffic_reports_report_type ON traffic_reports(report_type);
CREATE INDEX ix_traffic_reports_session_type ON traffic_reports(session_id, report_type);

-- ============================================================================
-- TRIGGERS for automatic timestamp management
-- ============================================================================

-- Function to update updated_at timestamp
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = CURRENT_TIMESTAMP;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- Trigger for traffic_sessions
CREATE TRIGGER traffic_sessions_updated_at
    BEFORE UPDATE ON traffic_sessions
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();

-- Trigger for incident_events
CREATE TRIGGER incident_events_updated_at
    BEFORE UPDATE ON incident_events
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();

-- ============================================================================
-- MATERIALIZED VIEWS for Analytics
-- ============================================================================

-- Hourly Traffic Summary
CREATE MATERIALIZED VIEW mv_hourly_traffic_summary AS
SELECT
    de.session_id,
    DATE_TRUNC('hour', de.timestamp) AS hour,
    de.vehicle_type,
    COUNT(*) AS detection_count,
    AVG(de.confidence) AS avg_confidence,
    AVG(de.speed_estimate) AS avg_speed,
    MIN(de.speed_estimate) AS min_speed,
    MAX(de.speed_estimate) AS max_speed
FROM detection_events de
GROUP BY de.session_id, DATE_TRUNC('hour', de.timestamp), de.vehicle_type;

CREATE INDEX ix_mv_hourly_traffic_summary_session ON mv_hourly_traffic_summary(session_id);
CREATE INDEX ix_mv_hourly_traffic_summary_hour ON mv_hourly_traffic_summary(hour DESC);

-- Incident Summary by Type and Severity
CREATE MATERIALIZED VIEW mv_incident_summary AS
SELECT
    ie.session_id,
    ie.incident_type,
    ie.severity,
    COUNT(*) AS incident_count,
    SUM(CASE WHEN ie.resolved = FALSE THEN 1 ELSE 0 END) AS unresolved_count,
    AVG(EXTRACT(EPOCH FROM (ie.resolved_at - ie.timestamp))) AS avg_resolution_time_seconds
FROM incident_events ie
GROUP BY ie.session_id, ie.incident_type, ie.severity;

CREATE INDEX ix_mv_incident_summary_session ON mv_incident_summary(session_id);
CREATE INDEX ix_mv_incident_summary_severity ON mv_incident_summary(severity);

-- Vehicle Type Distribution
CREATE MATERIALIZED VIEW mv_vehicle_distribution AS
SELECT
    vc.session_id,
    vc.vehicle_type,
    vc.direction,
    SUM(vc.count) AS total_count,
    AVG(vc.count) AS avg_count_per_interval,
    MAX(vc.count) AS max_count_per_interval
FROM vehicle_counts vc
GROUP BY vc.session_id, vc.vehicle_type, vc.direction;

CREATE INDEX ix_mv_vehicle_distribution_session ON mv_vehicle_distribution(session_id);

-- Peak Hours Analysis
CREATE MATERIALIZED VIEW mv_peak_hours AS
SELECT
    de.session_id,
    EXTRACT(HOUR FROM de.timestamp)::INTEGER AS hour_of_day,
    COUNT(*) AS detection_count,
    COUNT(DISTINCT de.track_id) AS unique_vehicles,
    AVG(de.confidence) AS avg_confidence
FROM detection_events de
GROUP BY de.session_id, EXTRACT(HOUR FROM de.timestamp);

CREATE INDEX ix_mv_peak_hours_session ON mv_peak_hours(session_id);
CREATE INDEX ix_mv_peak_hours_hour ON mv_peak_hours(hour_of_day);

-- Session Quality Metrics
CREATE MATERIALIZED VIEW mv_session_quality_metrics AS
SELECT
    ts.id AS session_id,
    ts.status,
    ts.source_type,
    COUNT(DISTINCT de.id) AS total_detections,
    COUNT(DISTINCT de.track_id) AS unique_tracks,
    COUNT(DISTINCT ie.id) AS total_incidents,
    SUM(CASE WHEN ie.resolved = FALSE THEN 1 ELSE 0 END) AS unresolved_incidents,
    AVG(de.confidence) AS avg_detection_confidence,
    MIN(de.confidence) AS min_detection_confidence,
    MAX(de.confidence) AS max_detection_confidence,
    COUNT(DISTINCT DATE(de.timestamp)) AS days_with_detections,
    (ts.end_time - ts.start_time) AS session_duration
FROM traffic_sessions ts
LEFT JOIN detection_events de ON ts.id = de.session_id
LEFT JOIN incident_events ie ON ts.id = ie.session_id
GROUP BY ts.id, ts.status, ts.source_type;

CREATE INDEX ix_mv_session_quality_metrics_status ON mv_session_quality_metrics(status);
CREATE INDEX ix_mv_session_quality_metrics_source ON mv_session_quality_metrics(source_type);

-- ============================================================================
-- REFRESH MATERIALIZED VIEWS FUNCTION
-- ============================================================================

CREATE OR REPLACE FUNCTION refresh_all_materialized_views()
RETURNS void AS $$
BEGIN
    REFRESH MATERIALIZED VIEW CONCURRENTLY mv_hourly_traffic_summary;
    REFRESH MATERIALIZED VIEW CONCURRENTLY mv_incident_summary;
    REFRESH MATERIALIZED VIEW CONCURRENTLY mv_vehicle_distribution;
    REFRESH MATERIALIZED VIEW CONCURRENTLY mv_peak_hours;
    REFRESH MATERIALIZED VIEW CONCURRENTLY mv_session_quality_metrics;
    RAISE NOTICE 'All materialized views refreshed successfully';
END;
$$ LANGUAGE plpgsql;

-- ============================================================================
-- UTILITY FUNCTIONS
-- ============================================================================

-- Function to get traffic statistics for a session
CREATE OR REPLACE FUNCTION get_session_traffic_stats(
    p_session_id VARCHAR(36),
    p_time_range_start TIMESTAMP WITH TIME ZONE DEFAULT NULL,
    p_time_range_end TIMESTAMP WITH TIME ZONE DEFAULT NULL
)
RETURNS TABLE (
    total_detections BIGINT,
    unique_tracks BIGINT,
    avg_confidence NUMERIC,
    total_incidents BIGINT,
    unresolved_incidents BIGINT,
    vehicle_type_breakdown JSONB
) AS $$
BEGIN
    RETURN QUERY
    SELECT
        COUNT(DISTINCT de.id)::BIGINT,
        COUNT(DISTINCT de.track_id)::BIGINT,
        ROUND(AVG(de.confidence), 4),
        COUNT(DISTINCT ie.id)::BIGINT,
        COUNT(DISTINCT CASE WHEN ie.resolved = FALSE THEN ie.id END)::BIGINT,
        JSONB_OBJECT_AGG(de.vehicle_type::TEXT, vehicle_counts.count)
    FROM detection_events de
    LEFT JOIN incident_events ie ON de.session_id = ie.session_id
    LEFT JOIN LATERAL (
        SELECT de.vehicle_type, COUNT(*) as count
        FROM detection_events de2
        WHERE de2.session_id = p_session_id
            AND (p_time_range_start IS NULL OR de2.timestamp >= p_time_range_start)
            AND (p_time_range_end IS NULL OR de2.timestamp <= p_time_range_end)
        GROUP BY de2.vehicle_type
    ) vehicle_counts ON TRUE
    WHERE de.session_id = p_session_id
        AND (p_time_range_start IS NULL OR de.timestamp >= p_time_range_start)
        AND (p_time_range_end IS NULL OR de.timestamp <= p_time_range_end);
END;
$$ LANGUAGE plpgsql;

-- Function to detect anomalies (vehicles with unusual speed patterns)
CREATE OR REPLACE FUNCTION detect_speed_anomalies(
    p_session_id VARCHAR(36),
    p_std_dev_threshold FLOAT DEFAULT 2.0
)
RETURNS TABLE (
    track_id VARCHAR(36),
    avg_speed FLOAT,
    std_dev FLOAT,
    min_speed FLOAT,
    max_speed FLOAT,
    detection_count BIGINT
) AS $$
BEGIN
    RETURN QUERY
    WITH track_speeds AS (
        SELECT
            de.track_id,
            AVG(de.speed_estimate) AS avg_speed,
            STDDEV(de.speed_estimate) AS std_dev,
            MIN(de.speed_estimate) AS min_speed,
            MAX(de.speed_estimate) AS max_speed,
            COUNT(*) AS detection_count
        FROM detection_events de
        WHERE de.session_id = p_session_id
            AND de.track_id IS NOT NULL
            AND de.speed_estimate IS NOT NULL
        GROUP BY de.track_id
    )
    SELECT
        ts.track_id,
        ts.avg_speed,
        ts.std_dev,
        ts.min_speed,
        ts.max_speed,
        ts.detection_count
    FROM track_speeds ts
    WHERE ts.std_dev >= p_std_dev_threshold;
END;
$$ LANGUAGE plpgsql;

-- ============================================================================
-- PARTITIONING STRATEGY (Optional - for high-volume scenarios)
-- ============================================================================
-- Note: Uncomment and configure if handling very large datasets

/*
-- Partition detection_events by month for improved performance
ALTER TABLE detection_events
PARTITION BY RANGE (EXTRACT(YEAR_MONTH FROM timestamp));

CREATE TABLE detection_events_202603
PARTITION OF detection_events
FOR VALUES FROM ('202603') TO ('202604');

-- Add more partitions as needed for your data volume
*/

-- ============================================================================
-- INITIAL SECURITY AND PERMISSIONS
-- ============================================================================

-- Create read-only role for analytics
CREATE ROLE analytics_read_only;
GRANT CONNECT ON DATABASE postgres TO analytics_read_only;
GRANT USAGE ON SCHEMA public TO analytics_read_only;
GRANT SELECT ON ALL TABLES IN SCHEMA public TO analytics_read_only;
GRANT SELECT ON ALL MATERIALIZED VIEWS IN SCHEMA public TO analytics_read_only;

-- Create application role with full access
CREATE ROLE app_user;
GRANT ALL PRIVILEGES ON ALL TABLES IN SCHEMA public TO app_user;
GRANT ALL PRIVILEGES ON ALL SEQUENCES IN SCHEMA public TO app_user;
GRANT ALL PRIVILEGES ON ALL FUNCTIONS IN SCHEMA public TO app_user;

-- ============================================================================
-- SAMPLE DATA (Optional - for development/testing)
-- ============================================================================

/*
-- Insert a sample traffic session
INSERT INTO traffic_sessions (id, source_type, source_url, status, metadata_json)
VALUES (
    'session-001',
    'video_file',
    '/videos/intersection-20240101.mp4',
    'completed',
    '{"resolution": "1920x1080", "fps": 30, "codec": "h264", "duration": 3600}'
);

-- Insert sample detection events
INSERT INTO detection_events (session_id, frame_number, vehicle_type, confidence, track_id, bbox_x, bbox_y, bbox_w, bbox_h, speed_estimate, direction)
VALUES (
    'session-001',
    100,
    'car',
    0.95,
    'track-001',
    0.1,
    0.2,
    0.3,
    0.4,
    45.5,
    'north'
);

-- Insert sample incident
INSERT INTO incident_events (session_id, incident_type, severity, location_description, resolved)
VALUES (
    'session-001',
    'congestion',
    'medium',
    'Main intersection - north bound',
    false
);
*/
