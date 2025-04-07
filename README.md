# UK Companies Search App

This application provides a mobile interface to search UK company data fetched from Companies House. The system consists of a Python FastAPI backend and a React Native mobile app.

## Architecture Overview

1. **React Native Mobile App** - iOS app for searching and viewing UK company data
2. **Python FastAPI Backend** - REST API for data processing and search functionality
3. **PostgreSQL Database** - Storage for company data with full-text search capabilities

## Requirements

### Backend Requirements
- Docker and Docker Compose
- PostgreSQL 14+
- Python 3.11+
- FastAPI

### Mobile App Requirements
- Node.js 16+
- React Native / Expo CLI
- iOS Simulator or physical iOS device for testing

## Setup Instructions

### Backend Setup

1. Clone the repository
2. Navigate to the project root directory
3. Create the backend directory structure:
   ```
   mkdir -p backend
   ```
4. Copy the following files to their respective locations:
   - `app.py` → `backend/app.py`
   - `requirements.txt` → `backend/requirements.txt`
   - `Dockerfile` → `backend/Dockerfile`
   - `init-db.sql` → `./init-db.sql`
   - `docker-compose.yml` → `./docker-compose.yml`

5. Start the backend services:
   ```
   docker compose up -d
   ```

6. The API will be available at `http://localhost:8000`

### Mobile App Setup

1. Create a new React Native project:
   ```
   npx create-expo-app uk-companies-app
   cd uk-companies-app
   ```

2. Install dependencies:
   ```
   npm install @react-navigation/native @react-navigation/stack
   npx expo install react-native-gesture-handler react-native-screens react-native-safe-area-context
   ```

3. Copy the provided files:
   - `App.js` → `App.js`
   - `config.js` → `config.js`
   - Update `app.json` and `package.json` with the provided content

4. Update the API URL in `config.js` to match your backend server's address

5. Start the app:
   ```
   npx expo start
   ```

6. Press 'i' to open in iOS simulator or scan the QR code with the Expo Go app on your device

## Usage Instructions

### Downloading Company Data

1. Launch the app
2. Tap the "Download Company Data" button
3. Wait for the download and import process to complete
   - This may take several minutes depending on your internet connection and computer performance

### Searching Companies

1. Enter a search term in the search box
2. Tap "Search" or press Enter
3. View the search results
4. Tap on a company to see detailed information

## Data Source

The app uses data from Companies House, available at:
https://download.companieshouse.gov.uk/en_output.html

## API Endpoints

- `GET /search?query={query}&page={page}&per_page={per_page}` - Search companies by name or number
- `GET /company/{company_number}` - Get details for a specific company
- `POST /download` - Download and import the latest company data

## Performance Considerations

- The full dataset is large (approximately 4-5 million companies)
- Initial data import can take 10-30 minutes
- PostgreSQL with full-text search provides efficient query performance