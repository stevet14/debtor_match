-- Create the database
DO
$$
BEGIN
   IF NOT EXISTS (
      SELECT FROM pg_database WHERE datname = 'companies_db'
   ) THEN
      CREATE DATABASE companies_db;
   END IF;
END
$$;

-- Connect to the database
\c companies_db

-- Create the companies table with expanded address fields
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

-- Create an index for the full-text search
CREATE INDEX IF NOT EXISTS idx_companies_search_vector ON companies USING GIN(search_vector);

-- Create a function to update the search vector, including all address fields
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

-- Drop the trigger if it exists
DROP TRIGGER IF EXISTS companies_search_vector_update_trigger ON companies;

-- Create the trigger
CREATE TRIGGER companies_search_vector_update_trigger
BEFORE INSERT OR UPDATE ON companies
FOR EACH ROW EXECUTE FUNCTION companies_search_vector_update();

-- Create an index on company_number for faster lookups
CREATE INDEX IF NOT EXISTS idx_company_number ON companies(company_number);

-- Create indexes on commonly searched address fields
CREATE INDEX IF NOT EXISTS idx_reg_address_postcode ON companies(reg_address_postcode);
CREATE INDEX IF NOT EXISTS idx_reg_address_town ON companies(reg_address_town);