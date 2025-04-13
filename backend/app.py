# app.py - FastAPI Backend
from fastapi import FastAPI, HTTPException, Query, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
import uvicorn
import psycopg2
from psycopg2.extras import RealDictCursor
import csv
import requests
import zipfile
from typing import List, Optional, Dict, Any
import os
from pydantic import BaseModel
import logging
import codecs
from datetime import datetime
import threading
import time

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

# Global status tracker for download task
download_status = {
    "is_running": False,
    "start_time": None,
    "completion_percentage": 0,
    "status": "idle",  # idle, downloading, processing, completed, failed
    "error": None,
    "total_records": 0,
    "processed_records": 0
}


# Response models
class Address(BaseModel):
    care_of: Optional[str] = None
    po_box: Optional[str] = None
    address_line_1: Optional[str] = None
    address_line_2: Optional[str] = None
    town: Optional[str] = None
    county: Optional[str] = None
    country: Optional[str] = None
    postcode: Optional[str] = None

class Company(BaseModel):
    company_number: str
    company_name: str
    registered_office_address: Optional[Address] = None
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
    
    
class DownloadStatus(BaseModel):
    is_running: bool
    start_time: Optional[str] = None
    completion_percentage: float
    status: str
    error: Optional[str] = None
    total_records: int
    processed_records: int


def get_db_connection():
    """Create a database connection"""
    try:
        conn = psycopg2.connect(
            host=DB_HOST,
            database=DB_NAME,
            user=DB_USER,
            password=DB_PASS,
            port=DB_PORT,
            cursor_factory=RealDictCursor,
        )
        return conn
    except Exception as e:
        logger.error(f"Database connection error: {e}")
        raise HTTPException(
            status_code=500, detail=f"Database connection error: {str(e)}"
        )


def init_db():
    """Initialize database tables if they don't exist"""
    conn = get_db_connection()
    cur = conn.cursor()
    try:
        # Create companies table with address fields
        cur.execute(
            """
        CREATE TABLE IF NOT EXISTS companies (
            id SERIAL PRIMARY KEY,
            company_number VARCHAR(10) UNIQUE,
            company_name TEXT,
            reg_address_care_of TEXT,
            reg_address_po_box TEXT,
            reg_address_line_1 TEXT,
            reg_address_line_2 TEXT,
            reg_address_town TEXT,
            reg_address_county TEXT,
            reg_address_country TEXT,
            reg_address_postcode TEXT,
            company_category VARCHAR(100),
            company_status VARCHAR(50),
            country_of_origin VARCHAR(50),
            incorporation_date DATE,
            sic_codes TEXT,
            search_vector TSVECTOR
        );
        """
        )

        # Create GIN index for full-text search
        cur.execute(
            """
        CREATE INDEX IF NOT EXISTS idx_companies_search_vector ON companies USING GIN(search_vector);
        """
        )

        # Create a trigger to update the search vector
        cur.execute(
            """
        CREATE OR REPLACE FUNCTION companies_search_vector_update() RETURNS TRIGGER AS $$
        BEGIN
            NEW.search_vector = to_tsvector('english', 
                COALESCE(NEW.company_name, '') || ' ' || 
                COALESCE(NEW.company_number, '') || ' ' || 
                COALESCE(NEW.reg_address_care_of, '') || ' ' ||
                COALESCE(NEW.reg_address_po_box, '') || ' ' ||
                COALESCE(NEW.reg_address_line_1, '') || ' ' ||
                COALESCE(NEW.reg_address_line_2, '') || ' ' ||
                COALESCE(NEW.reg_address_town, '') || ' ' ||
                COALESCE(NEW.reg_address_county, '') || ' ' ||
                COALESCE(NEW.reg_address_country, '') || ' ' ||
                COALESCE(NEW.reg_address_postcode, '') || ' ' ||
                COALESCE(NEW.company_category, '') || ' ' || 
                COALESCE(NEW.company_status, '') || ' ' || 
                COALESCE(NEW.country_of_origin, '') || ' ' || 
                COALESCE(NEW.sic_codes, '')
            );
            RETURN NEW;
        END
        $$ LANGUAGE plpgsql;
        """
        )

        # Drop the trigger if it exists
        cur.execute(
            """
        DROP TRIGGER IF EXISTS companies_search_vector_update_trigger ON companies;
        """
        )

        # Create the trigger
        cur.execute(
            """
        CREATE TRIGGER companies_search_vector_update_trigger
        BEFORE INSERT OR UPDATE ON companies
        FOR EACH ROW EXECUTE FUNCTION companies_search_vector_update();
        """
        )

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


def process_companies_data_in_background():
    """Function to handle the download and import process in the background"""
    global download_status
    
    try:
        # Mark as running and reset status
        download_status = {
            "is_running": True,
            "start_time": datetime.now().isoformat(),
            "completion_percentage": 0,
            "status": "downloading",
            "error": None,
            "total_records": 0,
            "processed_records": 0
        }
        
        # Companies House data URL
        url = "https://download.companieshouse.gov.uk/BasicCompanyDataAsOneFile-2024-04-01.zip"

        logger.info(f"Downloading data from {url}")
        response = requests.get(url, stream=True)

        if response.status_code != 200:
            raise Exception(f"Failed to download data, status code: {response.status_code}")

        # Create temporary file to store the zip
        with open("companies_data.zip", "wb") as f:
            total_size = int(response.headers.get('content-length', 0))
            downloaded = 0
            
            for chunk in response.iter_content(chunk_size=8192):
                f.write(chunk)
                downloaded += len(chunk)
                if total_size > 0:
                    # Update download progress
                    download_status["completion_percentage"] = min(50, int(downloaded * 50 / total_size))
                    
        logger.info("Download complete, extracting data")
        download_status["status"] = "processing"
        
        # Extract the CSV from the zip
        with zipfile.ZipFile("companies_data.zip", "r") as zip_ref:
            csv_filename = zip_ref.namelist()[0]  # Assuming there's only one file
            with zip_ref.open(csv_filename) as csv_file:
                # Count total records for progress tracking
                line_count = sum(1 for _ in codecs.iterdecode(csv_file, "utf-8"))
                download_status["total_records"] = line_count - 1  # Subtract header row
                
            # Reopen the file for processing
            with zip_ref.open(csv_filename) as csv_file:
                # Map required columns including full address fields
                required_columns = {
                    " CompanyNumber": "company_number",
                    "CompanyName": "company_name",
                    "RegAddress.CareOf": "reg_address_care_of",
                    "RegAddress.POBox": "reg_address_po_box",
                    "RegAddress.AddressLine1": "reg_address_line_1",
                    "RegAddress.AddressLine2": "reg_address_line_2",
                    "RegAddress.PostTown": "reg_address_town",
                    "RegAddress.County": "reg_address_county",
                    "RegAddress.Country": "reg_address_country",
                    "RegAddress.PostCode": "reg_address_postcode",
                    "CompanyCategory": "company_category",
                    "CompanyStatus": "company_status",
                    "CountryOfOrigin": "country_of_origin",
                    "IncorporationDate": "incorporation_date",
                    "SICCode.SicText_1": "sic_codes",
                }

                with open(
                    "temp_companies_corrected.csv", "w", encoding="utf-8"
                ) as corrected_csv:
                    writer = csv.DictWriter(
                        corrected_csv, fieldnames=required_columns.values()
                    )
                    writer.writeheader()

                    reader = csv.DictReader(codecs.iterdecode(csv_file, "utf-8"))
                    records_processed = 0
                    
                    for row in reader:
                        # Map and transform the required columns
                        mapped_row = {}
                        for csv_col, db_col in required_columns.items():
                            value = row.get(csv_col, None)
                            if csv_col == "IncorporationDate" and value:
                                try:
                                    # Convert from DD/MM/YYYY to YYYY-MM-DD
                                    value = datetime.strptime(
                                        value, "%d/%m/%Y"
                                    ).strftime("%Y-%m-%d")
                                except ValueError:
                                    logger.warning(
                                        f"Invalid date format for IncorporationDate: {value}"
                                    )
                                    value = None  # Set to NULL if invalid
                            mapped_row[db_col] = value
                        writer.writerow(mapped_row)
                        
                        # Update progress
                        records_processed += 1
                        if records_processed % 1000 == 0:  # Update every 1000 records
                            download_status["processed_records"] = records_processed
                            download_status["completion_percentage"] = 50 + int(records_processed * 50 / download_status["total_records"])

        logger.info("Temporary corrected CSV file created, loading into database")

        # Use PostgreSQL's COPY command to load the corrected data
        conn = get_db_connection()
        cur = conn.cursor()

        # Clear existing data
        cur.execute("TRUNCATE TABLE companies RESTART IDENTITY;")

        # Load data using COPY
        with open(
            "temp_companies_corrected.csv", "r", encoding="utf-8"
        ) as corrected_csv:
            cur.copy_expert(
                """
                COPY companies (company_number, company_name, 
                reg_address_care_of, reg_address_po_box, reg_address_line_1, reg_address_line_2,
                reg_address_town, reg_address_county, reg_address_country, reg_address_postcode,
                company_category, company_status, country_of_origin, incorporation_date, sic_codes)
                FROM STDIN WITH CSV HEADER
                """,
                corrected_csv,
            )

        conn.commit()
        logger.info("Data successfully loaded into the database")

        # Clean up temporary files
        os.remove("companies_data.zip")
        os.remove("temp_companies_corrected.csv")

        # Update final status
        download_status["completion_percentage"] = 100
        download_status["status"] = "completed"
        download_status["processed_records"] = download_status["total_records"]
        logger.info("Download and import process completed successfully")
        
    except Exception as e:
        logger.error(f"Error in background process: {e}")
        download_status["status"] = "failed"
        download_status["error"] = str(e)
    finally:
        download_status["is_running"] = False


@app.post("/download")
async def download_companies_data(background_tasks: BackgroundTasks):
    """Start the download process in the background"""
    global download_status
    
    # If already running, return current status
    if download_status["is_running"]:
        return {
            "status": "running",
            "message": "Download already in progress",
            "current_status": download_status
        }
    
    # Start background task
    background_tasks.add_task(process_companies_data_in_background)
    
    return {
        "status": "started",
        "message": "Download process started in the background"
    }


@app.get("/download/status", response_model=DownloadStatus)
async def get_download_status():
    """Get the current status of the download process"""
    return download_status


def insert_batch(cursor, batch):
    """Insert a batch of company records"""
    insert_query = """
    INSERT INTO companies 
    (company_number, company_name, 
    reg_address_care_of, reg_address_po_box, reg_address_line_1, reg_address_line_2,
    reg_address_town, reg_address_county, reg_address_country, reg_address_postcode,
    company_category, company_status, country_of_origin, incorporation_date, sic_codes)
    VALUES (%(company_number)s, %(company_name)s, 
    %(reg_address_care_of)s, %(reg_address_po_box)s, %(reg_address_line_1)s, %(reg_address_line_2)s,
    %(reg_address_town)s, %(reg_address_county)s, %(reg_address_country)s, %(reg_address_postcode)s,
    %(company_category)s, %(company_status)s, %(country_of_origin)s, 
    %(incorporation_date)s, %(sic_codes)s)
    ON CONFLICT (company_number) DO UPDATE SET
    company_name = EXCLUDED.company_name,
    reg_address_care_of = EXCLUDED.reg_address_care_of,
    reg_address_po_box = EXCLUDED.reg_address_po_box,
    reg_address_line_1 = EXCLUDED.reg_address_line_1,
    reg_address_line_2 = EXCLUDED.reg_address_line_2,
    reg_address_town = EXCLUDED.reg_address_town,
    reg_address_county = EXCLUDED.reg_address_county,
    reg_address_country = EXCLUDED.reg_address_country,
    reg_address_postcode = EXCLUDED.reg_address_postcode,
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
    per_page: int = Query(20, ge=1, le=100, description="Results per page"),
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
            (query,),
        )
        total = cur.fetchone()["total"]

        # Get paginated results
        cur.execute(
            """
            SELECT company_number, company_name, 
                reg_address_care_of, reg_address_po_box, reg_address_line_1, reg_address_line_2,
                reg_address_town, reg_address_county, reg_address_country, reg_address_postcode,
                company_category, company_status, country_of_origin, 
                incorporation_date, sic_codes
            FROM companies 
            WHERE search_vector @@ plainto_tsquery('english', %s)
            ORDER BY ts_rank(search_vector, plainto_tsquery('english', %s)) DESC
            LIMIT %s OFFSET %s
            """,
            (query, query, per_page, offset),
        )

        companies = cur.fetchall()

        # Convert to list of Company objects
        company_list = []
        for row in companies:
            # Create address object
            address = Address(
                care_of=row["reg_address_care_of"],
                po_box=row["reg_address_po_box"],
                address_line_1=row["reg_address_line_1"],
                address_line_2=row["reg_address_line_2"],
                town=row["reg_address_town"],
                county=row["reg_address_county"],
                country=row["reg_address_country"],
                postcode=row["reg_address_postcode"],
            )
            
            company = Company(
                company_number=row["company_number"],
                company_name=row["company_name"],
                registered_office_address=address,
                company_category=row["company_category"],
                company_status=row["company_status"],
                country_of_origin=row["country_of_origin"],
                incorporation_date=(
                    str(row["incorporation_date"])
                    if row["incorporation_date"]
                    else None
                ),
                sic_codes=row["sic_codes"],
            )
            company_list.append(company)

        return {
            "companies": company_list,
            "total": total,
            "page": page,
            "per_page": per_page,
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
            SELECT company_number, company_name, 
                reg_address_care_of, reg_address_po_box, reg_address_line_1, reg_address_line_2,
                reg_address_town, reg_address_county, reg_address_country, reg_address_postcode,
                company_category, company_status, country_of_origin, 
                incorporation_date, sic_codes
            FROM companies 
            WHERE company_number = %s
            """,
            (company_number,),
        )

        company = cur.fetchone()

        if not company:
            raise HTTPException(status_code=404, detail="Company not found")

        # Create address object
        address = Address(
            care_of=company["reg_address_care_of"],
            po_box=company["reg_address_po_box"],
            address_line_1=company["reg_address_line_1"],
            address_line_2=company["reg_address_line_2"],
            town=company["reg_address_town"],
            county=company["reg_address_county"],
            country=company["reg_address_country"],
            postcode=company["reg_address_postcode"],
        )
        
        return Company(
            company_number=company["company_number"],
            company_name=company["company_name"],
            registered_office_address=address,
            company_category=company["company_category"],
            company_status=company["company_status"],
            country_of_origin=company["country_of_origin"],
            incorporation_date=(
                str(company["incorporation_date"])
                if company["incorporation_date"]
                else None
            ),
            sic_codes=company["sic_codes"],
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Get company error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


if __name__ == "__main__":
    uvicorn.run("app:app", host="0.0.0.0", port=8000, reload=True)