# Synapse - Personal Intelligence System

## Complete Setup and Onboarding Guide

### Table of Contents

1. [System Overview](#system-overview)
2. [Prerequisites](#prerequisites)
3. [Environment Setup](#environment-setup)
4. [Database Setup](#database-setup)
5. [Backend Setup](#backend-setup)
6. [Frontend Setup](#frontend-setup)
7. [iOS App Setup](#ios-app-setup)
8. [Running the Complete System](#running-the-complete-system)
9. [Manual Cron Job Pipeline](#manual-cron-job-pipeline)
10. [Testing the System](#testing-the-system)
11. [Troubleshooting](#troubleshooting)

---

## System Overview

**Synapse** is a personal intelligence system that captures screenshots every 2-3 seconds from your iOS device, analyzes them using AI, and creates a knowledge graph for intelligent question answering. The system consists of:

- **iOS App**: Captures screenshots using ReplayKit and sends them to backend
- **Backend API**: FastAPI server that processes screenshots and handles queries
- **Cron Processing Pipeline**: Analyzes images, creates knowledge graphs, and builds communities
- **Frontend**: Next.js web interface for querying and visualization
- **Databases**: Neo4j (knowledge graph) + PostgreSQL (vector embeddings)

### Data Flow

1. iOS app captures screenshots → Base64 encoding → Backend API
2. Backend stores raw screenshots in `content_queue.json`
3. **Manual Cron Pipeline** (you run these scripts in order):
   - Image deduplication using perceptual hashing
   - OCR + Gemini analysis → structured data
   - Neo4j knowledge graph creation
   - Community detection and summarization
   - Vector embedding storage in PostgreSQL
4. Frontend queries → Vector similarity search → Knowledge graph traversal → AI response

---

## Prerequisites

### Required Software

- **Python 3.9+** with pip
- **Node.js 18+** with npm/yarn
- **Neo4j Desktop** or Docker
- **PostgreSQL 14+** with pgvector extension
- **Xcode** (for iOS app)
- **ngrok** (for iOS to backend communication)

### Required API Keys

- **Google AI API Key** (for Gemini 2.0)
- **OpenAI API Key** (optional, if using OpenAI instead)

### Hardware Requirements

- iOS device (iPhone/iPad) for screenshot capture
- Mac for development and iOS app compilation

---

## Environment Setup

### 1. Clone and Navigate

```bash
cd /path/to/your/project
# You should be in hackru-25 directory
```

### 2. Create Environment File

Create `.env` file in the root directory:

```bash
# Google AI (Gemini)
GOOGLE_API_KEY=your_google_ai_api_key_here

# Neo4j Configuration
NEO4J_URI=bolt://localhost:7687
NEO4J_USER=neo4j
NEO4J_PASSWORD=your_neo4j_password

# PostgreSQL Configuration (with pgvector)
PG_DSN=postgresql://username:password@localhost:5432/synapse_db

# Optional: Confidence threshold for filtering
CONF_THRESHOLD=0.5
```

### 3. Install System Dependencies

#### macOS (using Homebrew)

```bash
# Install Tesseract for OCR
brew install tesseract

# Install PostgreSQL with pgvector
brew install postgresql@14
brew install pgvector
```

#### Linux (Ubuntu/Debian)

```bash
# Install Tesseract
sudo apt-get install tesseract-ocr

# Install PostgreSQL
sudo apt-get install postgresql-14 postgresql-client-14
```

---

## Database Setup

### Neo4j Setup

#### Option A: Neo4j Desktop (Recommended)

1. Download and install [Neo4j Desktop](https://neo4j.com/download/)
2. Create a new project
3. Create a new database with:
   - Name: `synapse`
   - Password: (set in your `.env` file)
   - Version: 5.x
4. Start the database
5. Access Neo4j Browser at `http://localhost:7474`

#### Option B: Docker

```bash
docker run -d \
  --name neo4j-synapse \
  -p 7474:7474 -p 7687:7687 \
  -e NEO4J_AUTH=neo4j/your_password \
  neo4j:5.15
```

### PostgreSQL Setup

#### 1. Create Database

```bash
# Connect to PostgreSQL
psql -U postgres

# Create database and user
CREATE DATABASE synapse_db;
CREATE USER synapse_user WITH PASSWORD 'your_password';
GRANT ALL PRIVILEGES ON DATABASE synapse_db TO synapse_user;
\q
```

#### 2. Install pgvector Extension

```bash
# Connect to your database
psql -U synapse_user -d synapse_db

# Install pgvector extension
CREATE EXTENSION IF NOT EXISTS vector;
\q
```

#### 3. Verify Setup

```bash
psql -U synapse_user -d synapse_db -c "SELECT * FROM pg_extension WHERE extname = 'vector';"
```

---

## Backend Setup

### 1. Install Python Dependencies

#### Main Backend

```bash
cd backend
pip install -r requirements.txt
```

#### Cron Server

```bash
cd backend/cron_server
pip install -r requirements.txt
```

**Additional dependencies needed:**

```bash
pip install python-dotenv
pip install google-generativeai
pip install neo4j
pip install psycopg[binary]
pip install pytesseract
pip install umap-learn  # optional, for UMAP projection
pip install scikit-learn  # optional, for t-SNE
```

### 2. Create Database Directories

```bash
cd backend
mkdir -p database
touch database/content_queue.json
echo "[]" > database/content_queue.json
touch database/representative_images.json
echo "{}" > database/representative_images.json
```

### 3. Test Backend Connection

```bash
cd backend
python -c "
from cron_server.datasetup import graph_driver, pg, gemini_model
print('✅ Neo4j connected:', graph_driver.verify_connectivity())
print('✅ PostgreSQL connected:', pg.info.host)
print('✅ Gemini model loaded:', gemini_model.model_name)
"
```

---

## Frontend Setup

### 1. Install Dependencies

#### Main Frontend (brainApp)

```bash
cd frontend/brainApp/web
npm install
```

#### Alternative Frontend (personal-intelligence-system)

```bash
cd frontend/personal-intelligence-system
npm install
```

### 2. Configure Frontend

The frontend is already configured to connect to `localhost:8000` for the backend API.

---

## iOS App Setup

### 1. Open Xcode Project

```bash
open nourishment/nourishment.xcodeproj
```

### 2. Configure App Settings

1. Select your development team in **Signing & Capabilities**
2. Change bundle identifier to something unique (e.g., `com.yourname.synapse`)
3. Ensure both main app and broadcast extension have the same team/signing

### 3. Update Backend URL

Edit `nourishment/nourishmentBroadcast/SampleHandler.swift`:

```swift
// Line 9: Update this URL to your ngrok or local network IP
private let uploadURL = URL(string: "https://your-ngrok-url.ngrok-free.app/upload")!
```

### 4. Build and Install

1. Connect your iOS device
2. Build and run the app on your device
3. Trust the developer profile in Settings → General → VPN & Device Management

---

## Running the Complete System

### 1. Start Databases

```bash
# Start Neo4j (if using Docker)
docker start neo4j-synapse

# Start PostgreSQL (if not running)
brew services start postgresql@14
# or on Linux:
sudo systemctl start postgresql
```

### 2. Start Backend API

```bash
cd backend
python server.py
```

The server will show you the URLs:

```
Dashboard:  http://YOUR_IP:8000
Upload URL: http://YOUR_IP:8000/upload
```

### 3. Expose Backend with ngrok (for iOS)

```bash
# In another terminal
ngrok http 8000
```

Copy the HTTPS URL and update it in your iOS app's `SampleHandler.swift`.

### 4. Start Frontend

```bash
cd frontend/brainApp/web
npm run dev
```

Frontend will be available at `http://localhost:3000`

### 5. Start iOS App

1. Open the Synapse app on your iOS device
2. Tap "Start Streaming Reels"
3. Select your app from the broadcast picker
4. Start screen recording

---

## Manual Cron Job Pipeline

Since the automated cron job wasn't fully implemented, you need to run these scripts manually in the correct order:

### Step 1: Image Analysis and Deduplication

```bash
cd backend/cron_server
python main.py
```

**What this does:**

- Loads all images from `backend/database/content_queue.json`
- Groups images by `content_id` (scroll sessions)
- Uses perceptual hashing + greedy maximal diversity sampling
- Filters out redundant/similar frames
- Saves representative images to `backend/database/representative_images.json`
- **Calls Gemini API** to analyze representative images
- **Creates Neo4j knowledge graph nodes and relationships**

### Step 2: Community Detection and Summarization

```bash
cd backend/cron_server
python community.py
```

**What this does:**

- Queries Neo4j for subject-based communities
- Groups clips by subject matter
- **Calls Gemini API** to summarize each community
- Creates vector embeddings of summaries
- Stores community data in PostgreSQL `community_reports` table

### Step 3: Manual Database Table Creation

The tables should be created automatically, but if needed:

```sql
-- Connect to PostgreSQL
psql -U synapse_user -d synapse_db

-- Create image_cards table
CREATE EXTENSION IF NOT EXISTS vector;
CREATE TABLE IF NOT EXISTS image_cards (
  clip_id       text PRIMARY KEY,
  timebin       text,
  subject       text,
  aesthetic     text,
  trend         text,
  celebrity     text,
  current_event text,
  content_type  text,
  brief_caption text,
  emb           vector(768)
);
CREATE INDEX IF NOT EXISTS idx_image_cards_emb
ON image_cards USING ivfflat (emb vector_cosine_ops) WITH (lists=100);

-- Create community_reports table
CREATE TABLE IF NOT EXISTS community_reports (
  community_id text PRIMARY KEY,
  size integer,
  level integer,
  summary text,
  top_k jsonb,
  emb vector(768)
);
CREATE INDEX IF NOT EXISTS idx_community_reports_emb
ON community_reports USING ivfflat (emb vector_cosine_ops) WITH (lists=100);
```

### Recommended Pipeline Schedule

**For development/testing:**

- Run every 30 minutes to 1 hour while actively using the iOS app

**For production:**

- Run every 2-4 hours as originally intended

**Command sequence:**

```bash
cd backend/cron_server
echo "🔄 Starting pipeline at $(date)"
python main.py && echo "✅ Step 1 complete" || echo "❌ Step 1 failed"
python -c "from community import summarize_and_index_communities; summarize_and_index_communities()" && echo "✅ Step 2 complete" || echo "❌ Step 2 failed"
echo "🎉 Pipeline complete at $(date)"
```

---

## Testing the System

### 1. Test iOS Screenshot Capture

1. Start the iOS app and begin screen recording
2. Navigate through some apps (TikTok, Instagram, etc.)
3. Check backend logs for incoming frames
4. Verify `backend/database/content_queue.json` has entries

### 2. Test Manual Pipeline

```bash
cd backend/cron_server
python main.py
```

Check for:

- `backend/database/representative_images.json` created
- Neo4j has Clip nodes: `MATCH (c:Clip) RETURN count(c)`
- PostgreSQL has records: `SELECT count(*) FROM image_cards;`

### 3. Test Query System

1. Open frontend at `http://localhost:3000`
2. Navigate to `/chat`
3. Ask questions like:
   - "What kind of content do I watch?"
   - "Explain machine learning using my viewing habits"
   - "What trends am I following?"

### 4. Test Screenshot Analysis

1. Take a screenshot (Cmd+J on frontend)
2. Ask about the screenshot content
3. Should get AI analysis based on your viewing patterns

---

## Troubleshooting

### Common Issues

#### 1. iOS App Not Connecting

- **Check ngrok URL**: Ensure SampleHandler.swift has correct URL
- **Check network**: iOS and computer on same network for local testing
- **Check backend logs**: Should see POST requests to `/upload`

#### 2. Gemini API Errors

- **Verify API key**: Test with simple API call
- **Check quota**: Gemini has rate limits
- **Check model name**: Ensure `gemini-2.0-flash-001` is available

#### 3. Database Connection Issues

- **Neo4j**: Check if running on port 7687
- **PostgreSQL**: Verify pgvector extension installed
- **Permissions**: Ensure database user has proper permissions

#### 4. No Results from Queries

- **Run pipeline**: Ensure you've run the manual cron jobs
- **Check data**: Verify Neo4j has nodes and PostgreSQL has embeddings
- **Check logs**: Look for errors in synthesis.py

#### 5. Frontend Not Loading

- **Port conflicts**: Ensure port 3000 is available
- **Backend connection**: Frontend expects backend on port 8000
- **CORS issues**: Backend has CORS enabled for all origins

### Debug Commands

#### Check Data Status

```bash
# Neo4j data
echo "MATCH (c:Clip) RETURN count(c) as clips" | cypher-shell -u neo4j -p your_password

# PostgreSQL data
psql -U synapse_user -d synapse_db -c "SELECT count(*) FROM image_cards;"
psql -U synapse_user -d synapse_db -c "SELECT count(*) FROM community_reports;"

# Content queue
wc -l backend/database/content_queue.json
```

#### Test Individual Components

```bash
# Test Gemini
python -c "from cron_server.datasetup import gemini_model; print(gemini_model.generate_content('Hello').text)"

# Test embeddings
python -c "from cron_server.datasetup import embed_text; print(len(embed_text('test')['embedding']))"

# Test query system
python -c "from cron_server.synthesis import ask; print(ask('test query'))"
```

---

## Next Steps

1. **Automate the Pipeline**: Convert manual scripts to actual cron jobs
2. **Improve iOS App**: Add better error handling and status indicators
3. **Enhanced Analysis**: Add more sophisticated content analysis
4. **Mobile Frontend**: Create iOS/Android app for querying
5. **Privacy Controls**: Add data retention and deletion features

---

## File Structure Reference

```
hackru-25/
├── backend/
│   ├── server.py              # Main FastAPI server
│   ├── requirements.txt       # Python dependencies
│   ├── database/             # Local JSON storage
│   ├── cron_server/          # Analysis pipeline
│   │   ├── main.py           # Step 1: Image analysis
│   │   ├── community.py      # Step 2: Community detection
│   │   ├── synthesis.py      # Query processing
│   │   ├── datasetup.py      # Database connections
│   │   └── queries/          # Cypher queries
│   └── detection/            # App/scroll detection
├── frontend/
│   ├── brainApp/web/         # Main Next.js frontend
│   └── personal-intelligence-system/  # Alternative frontend
├── nourishment/              # iOS app
│   ├── nourishment/          # Main app
│   └── nourishmentBroadcast/ # Screen recording extension
└── .env                      # Environment variables
```

This completes your setup! The system should now capture screenshots from iOS, process them through the AI pipeline, and provide intelligent responses based on your viewing patterns.
