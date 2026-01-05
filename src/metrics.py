"""Prometheus metrics for concert management service."""
from prometheus_client import Counter, Histogram, Gauge
from cloudsound_shared.metrics import (
    http_requests_total,
    http_request_duration_seconds,
)

# Concert management specific metrics
concerts_total = Gauge(
    'concerts_total',
    'Total number of concerts',
    ['status']  # 'upcoming', 'past', 'all'
)

concerts_created_total = Counter(
    'concerts_created_total',
    'Total number of concerts created'
)

concerts_updated_total = Counter(
    'concerts_updated_total',
    'Total number of concerts updated'
)

concerts_deleted_total = Counter(
    'concerts_deleted_total',
    'Total number of concerts deleted'
)

concert_api_requests_total = Counter(
    'concert_api_requests_total',
    'Total number of concert API requests',
    ['method', 'endpoint', 'status']
)

concert_api_request_duration_seconds = Histogram(
    'concert_api_request_duration_seconds',
    'Duration of concert API requests in seconds',
    ['method', 'endpoint']
)

