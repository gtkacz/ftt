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

### Draft
- GET/POST `/api/picks/` - List/Create picks
- GET/PUT/DELETE `/api/picks/{id}/` - Pick detail operations
- GET/POST `/api/drafts/` - List/Create drafts
- GET/PUT/DELETE `/api/drafts/{id}/` - Draft detail operations

All endpoints require authentication except registration and login. Use JWT tokens for authentication.