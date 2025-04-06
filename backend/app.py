# app.py - FastAPI Backend
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
import uvicorn
import psycopg2
from psycopg2.extras import RealDictCursor
import csv
import requests
from io import StringIO
import zipfile
from typing import List, Optional
import os
from pydantic import BaseModel
import logging

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(title="UK Companies API")

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # In production, replace with specific origins
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Database connection parameters - use environment variables in production
DB_HOST = os.getenv("DB_HOST", "localhost")
DB_NAME = os.getenv("DB_NAME", "companies_db")
DB_USER = os.getenv("DB_USER", "postgres")
DB_PASS = os.getenv("DB_PASS", "postgres")
DB_PORT = os.getenv("DB_PORT", "5432")

# Response models
class Company(BaseModel):
    company_number: str
    company_name: str
    registered_office_address: Optional[str] = None
    company_category: Optional[str] = None
    company_status: Optional[str] = None
    country_of_origin: Optional[str] = None
    incorporation_date: Optional[str] = None
    sic_codes: Optional[str] = None

class SearchResponse(BaseModel):
    companies: List[Company]
    total: int
    page: int
    per_page: int

def get_db_connection():
    """Create a database connection"""
    try:
        conn = psycopg2.connect(
            host=DB_HOST,
            database=DB_NAME,
            user=DB_USER,
            password=DB_PASS,
            port=DB_PORT,
            cursor_factory=RealDictCursor
        )
        return conn
    except Exception as e:
        logger.error(f"Database connection error: {e}")
        raise HTTPException(status_code=500, detail=f"Database connection error: {str(e)}")

def init_db():
    """Initialize database tables if they don't exist"""
    conn = get_db_connection()
    cur = conn.cursor()
    try:
        # Create companies table
        cur.execute('''
        CREATE TABLE IF NOT EXISTS companies (
            id SERIAL PRIMARY KEY,
            company_number VARCHAR(10) UNIQUE,
            company_name TEXT,
            registered_office_address TEXT,
            company_category VARCHAR(100),
            company_status VARCHAR(50),
            country_of_origin VARCHAR(50),
            incorporation_date DATE,
            sic_codes TEXT,
            search_vector TSVECTOR
        );
        ''')
        
        # Create GIN index for full-text search
        cur.execute('''
        CREATE INDEX IF NOT EXISTS idx_companies_search_vector ON companies USING GIN(search_vector);
        ''')
        
        # Create a trigger to update the search vector
        cur.execute('''
        CREATE OR REPLACE FUNCTION companies_search_vector_update() RETURNS TRIGGER AS $$
        BEGIN
            NEW.search_vector = to_tsvector('english', 
                COALESCE(NEW.company_name, '') || ' ' || 
                COALESCE(NEW.company_number, '') || ' ' || 
                COALESCE(NEW.registered_office_address, '') || ' ' || 
                COALESCE(NEW.company_category, '') || ' ' || 
                COALESCE(NEW.company_status, '') || ' ' || 
                COALESCE(NEW.country_of_origin, '') || ' ' || 
                COALESCE(NEW.sic_codes, '')
            );
            RETURN NEW;
        END
        $$ LANGUAGE plpgsql;
        ''')
        
        # Drop the trigger if it exists
        cur.execute('''
        DROP TRIGGER IF EXISTS companies_search_vector_update_trigger ON companies;
        ''')
        
        # Create the trigger
        cur.execute('''
        CREATE TRIGGER companies_search_vector_update_trigger
        BEFORE INSERT OR UPDATE ON companies
        FOR EACH ROW EXECUTE FUNCTION companies_search_vector_update();
        ''')
        
        conn.commit()
        logger.info("Database initialized successfully")
    except Exception as e:
        conn.rollback()
        logger.error(f"Database initialization error: {e}")
        raise e
    finally:
        cur.close()
        conn.close()

@app.on_event("startup")
async def startup_event():
    """Run on application startup"""
    try:
        init_db()
    except Exception as e:
        logger.error(f"Startup error: {e}")

@app.get("/")
async def root():
    """Root endpoint"""
    return {"message": "UK Companies House API"}

@app.post("/download")
async def download_companies_data():
    """Download and import Companies House data"""
    try:
        # Companies House data URL
        url = "https://download.companieshouse.gov.uk/BasicCompanyDataAsOneFile-2024-04-01.zip"
        
        logger.info(f"Downloading data from {url}")
        response = requests.get(url, stream=True)
        
        if response.status_code != 200:
            raise HTTPException(status_code=response.status_code, detail="Failed to download data")
        
        # Create temporary file to store the zip
        with open("companies_data.zip", "wb") as f:
            for chunk in response.iter_content(chunk_size=8192):
                f.write(chunk)
        
        logger.info("Download complete, extracting data")
        
        # Extract the csv from the zip
        with zipfile.ZipFile("companies_data.zip", "r") as zip_ref:
            csv_filename = zip_ref.namelist()[0]  # Assuming there's only one file
            with zip_ref.open(csv_filename) as csv_file:
                csv_content = csv_file.read().decode('utf-8')
        
        # Delete the zip file
        os.remove("companies_data.zip")
        
        # Process the CSV data
        reader = csv.DictReader(StringIO(csv_content))
        conn = get_db_connection()
        cur = conn.cursor()
        
        # Clear existing data
        cur.execute("TRUNCATE TABLE companies RESTART IDENTITY;")
        
        # Batch insert for better performance
        batch_size = 1000
        insert_count = 0
        batch = []
        
        for row in reader:
            # Map CSV columns to database columns
            company_data = {
                "company_number": row.get("CompanyNumber", ""),
                "company_name": row.get("CompanyName", ""),
                "registered_office_address": ", ".join(filter(None, [
                    row.get("RegAddress.CareOf", ""),
                    row.get("RegAddress.POBox", ""),
                    row.get("RegAddress.AddressLine1", ""),
                    row.get("RegAddress.AddressLine2", ""),
                    row.get("RegAddress.PostTown", ""),
                    row.get("RegAddress.County", ""),
                    row.get("RegAddress.Country", ""),
                    row.get("RegAddress.PostCode", "")
                ])),
                "company_category": row.get("CompanyCategory", ""),
                "company_status": row.get("CompanyStatus", ""),
                "country_of_origin": row.get("CountryOfOrigin", ""),
                "incorporation_date": row.get("IncorporationDate", None),
                "sic_codes": row.get("SICCode.SicText_1", "") or row.get("SICCodes", "")
            }
            
            # Add to batch
            batch.append(company_data)
            
            if len(batch) >= batch_size:
                insert_batch(cur, batch)
                insert_count += len(batch)
                logger.info(f"Inserted {insert_count} companies")
                batch = []
        
        # Insert any remaining records
        if batch:
            insert_batch(cur, batch)
            insert_count += len(batch)
        
        conn.commit()
        logger.info(f"Import complete. Total companies inserted: {insert_count}")
        
        return {"status": "success", "companies_imported": insert_count}
    
    except Exception as e:
        logger.error(f"Error in download_companies_data: {e}")
        raise HTTPException(status_code=500, detail=str(e))

def insert_batch(cursor, batch):
    """Insert a batch of company records"""
    insert_query = """
    INSERT INTO companies 
    (company_number, company_name, registered_office_address, company_category, 
    company_status, country_of_origin, incorporation_date, sic_codes)
    VALUES (%(company_number)s, %(company_name)s, %(registered_office_address)s, 
    %(company_category)s, %(company_status)s, %(country_of_origin)s, 
    %(incorporation_date)s, %(sic_codes)s)
    ON CONFLICT (company_number) DO UPDATE SET
    company_name = EXCLUDED.company_name,
    registered_office_address = EXCLUDED.registered_office_address,
    company_category = EXCLUDED.company_category,
    company_status = EXCLUDED.company_status,
    country_of_origin = EXCLUDED.country_of_origin,
    incorporation_date = EXCLUDED.incorporation_date,
    sic_codes = EXCLUDED.sic_codes
    """
    cursor.executemany(insert_query, batch)

@app.get("/search", response_model=SearchResponse)
async def search_companies(
    query: str = Query(..., min_length=1, description="Search query"),
    page: int = Query(1, ge=1, description="Page number"),
    per_page: int = Query(20, ge=1, le=100, description="Results per page")
):
    """Search companies by name, number, address or other fields"""
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        
        # Calculate offset
        offset = (page - 1) * per_page
        
        # Get total count
        cur.execute(
            "SELECT COUNT(*) as total FROM companies WHERE search_vector @@ plainto_tsquery('english', %s)",
            (query,)
        )
        total = cur.fetchone()["total"]
        
        # Get paginated results
        cur.execute(
            """
            SELECT company_number, company_name, registered_office_address, 
                company_category, company_status, country_of_origin, 
                incorporation_date, sic_codes
            FROM companies 
            WHERE search_vector @@ plainto_tsquery('english', %s)
            ORDER BY ts_rank(search_vector, plainto_tsquery('english', %s)) DESC
            LIMIT %s OFFSET %s
            """,
            (query, query, per_page, offset)
        )
        
        companies = cur.fetchall()
        
        # Convert to list of Company objects
        company_list = []
        for row in companies:
            company = Company(
                company_number=row["company_number"],
                company_name=row["company_name"],
                registered_office_address=row["registered_office_address"],
                company_category=row["company_category"],
                company_status=row["company_status"],
                country_of_origin=row["country_of_origin"],
                incorporation_date=str(row["incorporation_date"]) if row["incorporation_date"] else None,
                sic_codes=row["sic_codes"]
            )
            company_list.append(company)
        
        return {
            "companies": company_list,
            "total": total,
            "page": page,
            "per_page": per_page
        }
    
    except Exception as e:
        logger.error(f"Search error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/company/{company_number}", response_model=Company)
async def get_company_details(company_number: str):
    """Get detailed information for a specific company by number"""
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        
        cur.execute(
            """
            SELECT company_number, company_name, registered_office_address, 
                company_category, company_status, country_of_origin, 
                incorporation_date, sic_codes
            FROM companies 
            WHERE company_number = %s
            """,
            (company_number,)
        )
        
        company = cur.fetchone()
        
        if not company:
            raise HTTPException(status_code=404, detail="Company not found")
        
        return Company(
            company_number=company["company_number"],
            company_name=company["company_name"],
            registered_office_address=company["registered_office_address"],
            company_category=company["company_category"],
            company_status=company["company_status"],
            country_of_origin=company["country_of_origin"],
            incorporation_date=str(company["incorporation_date"]) if company["incorporation_date"] else None,
            sic_codes=company["sic_codes"]
        )
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Get company error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

if __name__ == "__main__":
    uvicorn.run("app:app", host="0.0.0.0", port=8000, reload=True)