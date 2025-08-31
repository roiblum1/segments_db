# Network Segment Manager

A comprehensive API and web application for managing VLAN segments and EPG configurations for OpenShift/Hypershift clusters.

## Features

- 🌐 **Modern Web UI**: Responsive interface with Tailwind CSS
- 🌙 **Dark Mode**: Toggle between light and dark themes with persistent preference
- 🔒 **Duplicate Prevention**: Enhanced validation to prevent duplicate VLAN IDs
- 📊 **Real-time Statistics**: Dashboard with utilization metrics
- 🔍 **Comprehensive Logging**: Structured logging with rotation
- 🐳 **Docker Support**: Containerized deployment with Docker Compose
- 🚀 **FastAPI**: High-performance API with automatic documentation
- 💾 **SQLite Database**: Lightweight, embedded database with persistence
- 🔀 **Traefik Proxy**: Simple reverse proxy with automatic service discovery

## Quick Start

### Using Docker (Recommended)

1. **Clone and navigate to the project:**
   ```bash
   git clone <repository-url>
   cd segment_db
   ```

2. **Start the application:**
   ```bash
   docker-compose up -d
   ```

3. **Access the application:**
   - Web UI: http://localhost:8000
   - API Documentation: http://localhost:8000/docs
   - Health Check: http://localhost:8000/health

### Using Docker with Traefik Proxy

For production deployment with Traefik reverse proxy (much simpler than Nginx):

```bash
docker-compose --profile with-proxy up -d
```

Access via:
- **Application**: http://localhost (port 80)
- **Traefik Dashboard**: http://localhost:8080 (monitoring and routing)

Traefik automatically handles:
- Load balancing
- Rate limiting (100 requests/minute burst)
- Service discovery
- Health checks

### Development Setup

1. **Create virtual environment:**
   ```bash
   python -m venv venv
   source venv/bin/activate  # On Windows: venv\Scripts\activate
   ```

2. **Install dependencies:**
   ```bash
   pip install -r requirements.txt
   ```

3. **Run the application:**
   ```bash
   python -m uvicorn app.main:app --reload
   ```

## Configuration

### Environment Variables

Copy `.env.example` to `.env` and modify as needed:

```bash
cp .env.example .env
```

Key configuration options:

| Variable | Default | Description |
|----------|---------|-------------|
| `DATABASE_URL` | `sqlite:///./data/segment_database.db` | Database connection string |
| `LOG_LEVEL` | `INFO` | Logging level (DEBUG, INFO, WARNING, ERROR) |
| `LOAD_SAMPLE_DATA` | `true` | Load sample data on first run |
| `HOST` | `0.0.0.0` | Server host |
| `PORT` | `8000` | Server port |

### Docker Configuration

The application uses volumes for data persistence:

- `segment_data`: Database and application data
- `segment_logs`: Application logs
- `nginx_logs`: Nginx access/error logs (when using proxy)

## API Endpoints

### Segments Management

- `GET /api/segments` - List all segments with filtering
- `POST /api/segments` - Create new segment
- `GET /api/segments/available` - Get next available segment
- `POST /api/segments/{id}/allocate` - Allocate segment to cluster
- `POST /api/segments/{id}/release` - Release segment from cluster
- `PUT /api/segments/{id}` - Update segment
- `DELETE /api/segments/{id}` - Delete segment

### Statistics

- `GET /api/stats` - Get usage statistics
- `GET /health` - Health check

## Data Validation

### Duplicate Prevention

- **VLAN ID**: Unique constraint prevents duplicate VLAN IDs
- **Network Segment**: Unique constraint prevents duplicate CIDR ranges
- **API Validation**: Pre-check validation with detailed error messages

### Input Validation

- **VLAN ID**: Must be between 1-4094
- **Network Segment**: Must be valid CIDR notation (e.g., `192.168.1.0/24`)
- **Cluster Names**: Lowercase, alphanumeric with hyphens only
- **EPG Names**: Alphanumeric characters, spaces, and hyphens

## Logging

Comprehensive logging system with:

- **Console Output**: Structured logs to stdout
- **File Logging**: Rotating log files in `logs/` directory
- **Log Levels**: Configurable verbosity
- **Request Tracking**: API request/response logging
- **Error Handling**: Detailed error logging with context

Log files are automatically rotated at 10MB with 5 backup files retained.

## Monitoring

### Health Checks

- **Application**: `GET /health` endpoint
- **Docker**: Built-in health checks in containers
- **Database**: Connection verification in health endpoint

### Metrics

The `/api/stats` endpoint provides:
- Total segments count
- Segments in use
- Available segments
- Utilization percentage
- Active clusters count

## Development

### Project Structure

```
segment_db/
├── app/
│   ├── api/
│   │   └── segments.py      # API endpoints
│   ├── core/
│   │   ├── config.py        # Configuration
│   │   ├── database.py      # Database setup
│   │   └── logging.py       # Logging configuration
│   ├── models/
│   │   └── segment.py       # SQLAlchemy models
│   ├── schemas/
│   │   └── segment.py       # Pydantic schemas
│   ├── static/
│   │   └── index.html       # Web UI
│   └── main.py              # FastAPI application
├── Dockerfile               # Container definition
├── docker-compose.yml      # Container orchestration
├── requirements.txt         # Python dependencies
└── README.md               # This file
```

### Adding New Features

1. **Models**: Add SQLAlchemy models in `app/models/`
2. **Schemas**: Add Pydantic schemas in `app/schemas/`
3. **Endpoints**: Add API routes in `app/api/`
4. **Configuration**: Update settings in `app/core/config.py`

## Security

- **Non-root Container**: Application runs as non-root user
- **Input Validation**: Comprehensive input sanitization
- **CORS Configuration**: Configurable CORS settings
- **Rate Limiting**: Available via nginx proxy configuration
- **Security Headers**: Implemented in nginx configuration

## Troubleshooting

### Common Issues

1. **Port Already in Use**
   ```bash
   docker-compose down
   # Or change port in docker-compose.yml
   ```

2. **Permission Issues**
   ```bash
   sudo chown -R $USER:$USER data/ logs/
   ```

3. **Database Locked**
   ```bash
   docker-compose restart segment-manager
   ```

### Logs

View application logs:
```bash
docker-compose logs -f segment-manager
```

View nginx logs (if using proxy):
```bash
docker-compose logs -f nginx
```

## Contributing

1. Fork the repository
2. Create a feature branch
3. Make changes with tests
4. Submit a pull request

## License

This project is licensed under the MIT License.