## Tech Stack

- **Backend**: FastAPI
- **Task Queue**: Celery
- **Database**: Prisma Client Python with PostgreSQL
- **Broker**: Redis

## Installation

To get this project running locally, follow these steps:

1. **Clone the repository**
   ```bash
   git clone https://yourrepository.git
   cd your-project-folder
   ```

2. **Set up a virtual environment**
   ```bash
   python -m venv .venv
   source .venv/bin/activate  # On Windows use `.venv\Scripts\activate`
   ```

3. **Install dependencies**
   ```bash
   pip install -r requirements.txt
   ```

4. **Set up environment variables**
   Create a `.env` file in the root directory and populate it with the necessary environment variables:
   ```
   REDIS_HOST=localhost
   REDIS_PORT=6379
   DATABASE_URL=postgresql://user:password@localhost:5432/mydatabase
   ```

5. **Run the application**
   ```bash
   uvicorn main:app --reload
   ```

6. **Start Celery worker**
   ```bash
   celery -A commons.celery.celery_app worker --loglevel=info
   ```
   