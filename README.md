## Setup Instructions

1. Create a new Django project directory and navigate to it
2. Create a virtual environment: `python -m venv venv`
3. Activate it: `source venv/bin/activate` (Linux/Mac) or `venv\Scripts\activate` (Windows)
4. Install dependencies: `pip install -r requirements.txt`
5. Create the project structure and add all the files above
6. Run migrations: `python manage.py makemigrations` then `python manage.py migrate`
7. Create a superuser: `python manage.py createsuperuser`
8. Run the server: `python manage.py runserver`

## API Endpoints

### Authentication
- POST `/api/auth/register/` - User registration
- POST `/api/auth/login/` - User login

### Users
- GET/POST `/api/users/` - List/Create users
- GET/PUT/DELETE `/api/users/{id}/` - User detail operations

### Teams
- GET/POST `/api/teams/` - List/Create teams
- GET/PUT/DELETE `/api/teams/{id}/` - Team detail operations
- GET `/api/teams/{id}/salary/` - Get team total salary
- GET `/api/teams/{id}/players/` - Get team players and count
- GET `/api/teams/{id}/picks/` - Get team's draft picks

### Players
- GET/POST `/api/players/` - List/Create players
- GET/PUT/DELETE `/api/players/{id}/` - Player detail operations

### Draft Capital (Picks)
- GET/POST `/api/picks/` - List/Create picks
- GET/PUT/DELETE `/api/picks/{id}/` - Pick detail operations

### Drafts
- GET/POST `/api/drafts/` - List/Create drafts
- GET/PUT/DELETE `/api/drafts/{id}/` - Draft detail operations
- POST `/api/drafts/{id}/generate-order/` - Generate draft order for a draft
- GET `/api/drafts/{id}/board/` - Get current draft board state

### Draft Positions (Draft Order)
- GET/POST `/api/draft-positions/` - List/Create draft positions
- GET/PUT/DELETE `/api/draft-positions/{id}/` - Draft position detail operations
- POST `/api/draft-positions/{id}/pick/` - Make a draft pick

## OpenAPI Documentation Generation

### Setup Instructions

1. Install the requirements including `drf-spectacular==0.27.0`
2. Run migrations: `python manage.py makemigrations` then `python manage.py migrate`
3. Create a superuser: `python manage.py createsuperuser`
4. Run the server: `python manage.py runserver`

### Accessing the OpenAPI Documentation

Once your server is running, you can access the API documentation at:

- **Swagger UI**: `http://127.0.0.1:8000/api/docs/` - Interactive API documentation
- **ReDoc**: `http://127.0.0.1:8000/api/redoc/` - Alternative documentation interface
- **Raw OpenAPI Schema**: `http://127.0.0.1:8000/api/schema/` - JSON schema file

### Generating OpenAPI Schema File

To generate a static OpenAPI schema file:

```bash
# Generate schema.yml file
python manage.py spectacular --file schema.yml

# Generate schema.json file
python manage.py spectacular --format=openapi-json --file schema.json
```

### Example API Usage

#### Authentication
```bash
# Register a new user
curl -X POST http://127.0.0.1:8000/api/auth/register/ \
  -H "Content-Type: application/json" \
  -d '{
    "username": "testuser",
    "email": "test@example.com",
    "first_name": "Test",
    "last_name": "User",
    "password": "testpass123",
    "password_confirm": "testpass123"
  }'

# Login
curl -X POST http://127.0.0.1:8000/api/auth/login/ \
  -H "Content-Type: application/json" \
  -d '{
    "username": "testuser",
    "password": "testpass123"
  }'
```

#### Using JWT Tokens
```bash
# Use the access token in subsequent requests
curl -X GET http://127.0.0.1:8000/api/teams/ \
  -H "Authorization: Bearer YOUR_ACCESS_TOKEN"
```

#### Draft Workflow Example
```bash
# 1. Create a draft
curl -X POST http://127.0.0.1:8000/api/drafts/ \
  -H "Authorization: Bearer YOUR_ACCESS_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "year": 2025,
    "is_snake_draft": true
  }'

# 2. Generate draft order
curl -X POST http://127.0.0.1:8000/api/drafts/1/generate-order/ \
  -H "Authorization: Bearer YOUR_ACCESS_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "teams_order": [3, 1, 5, 2, 4],
    "rounds": 2
  }'

# 3. View draft board
curl -X GET http://127.0.0.1:8000/api/drafts/1/board/ \
  -H "Authorization: Bearer YOUR_ACCESS_TOKEN"

# 4. Make a draft pick
curl -X POST http://127.0.0.1:8000/api/draft-positions/1/pick/ \
  -H "Authorization: Bearer YOUR_ACCESS_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "player_id": 15
  }'
```

### Key OpenAPI Features

The generated OpenAPI spec includes:

- **Comprehensive endpoint documentation** with descriptions, parameters, and response schemas
- **Request/response examples** for all endpoints
- **Authentication scheme** (JWT Bearer tokens)
- **Model schemas** with field descriptions and validation rules
- **Error response definitions** with appropriate HTTP status codes
- **Query parameter filtering** documentation
- **Organized by tags** for better navigation

### Customizing Documentation

To add more detailed descriptions or examples, you can:

1. **Add docstrings to view methods**:
```python
def get(self, request, *args, **kwargs):
    """
    Retrieve a list of all teams with their statistics.

    This endpoint returns paginated results including team salary totals
    and player counts.
    """
    return super().get(request, *args, **kwargs)
```

2. **Use `@extend_schema` decorators** for complex customization:
```python
@extend_schema(
    summary="Custom endpoint summary",
    description="Detailed description of what this endpoint does",
    parameters=[...],
    examples=[...],
    responses={...}
)
```

3. **Add field help text** in models and serializers:
```python
class Player(models.Model):
    name = models.CharField(
        max_length=100,
        help_text="Player's full name"
    )
```

The OpenAPI spec will be automatically updated when you modify your views, serializers, or models with proper documentation.
