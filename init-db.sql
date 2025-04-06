-- Create the database
CREATE DATABASE companies_db;

-- Connect to the database
\c companies_db

-- Create the companies table
CREATE TABLE companies (
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

-- Create an index for the full-text search
CREATE INDEX idx_companies_search_vector ON companies USING GIN(search_vector);

-- Create a function to update the search vector
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

-- Create a trigger to update the search vector on insert or update
CREATE TRIGGER companies_search_vector_update_trigger
BEFORE INSERT OR UPDATE ON companies
FOR EACH ROW EXECUTE FUNCTION companies_search_vector_update();

-- Create an index on company_number for faster lookups
CREATE INDEX idx_company_number ON companies(company_number);