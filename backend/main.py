import pandas as pd
import requests
import json
from matcher import CompanyNameMatcher

def load_debtors(csv_file):
    """Load debtor information from CSV file"""
    df = pd.read_csv(csv_file)
    return df

def search_companies(query):
    """Search for companies using FastAPI endpoint"""
    try:
        response = requests.get(
            f"http://localhost:8000/search",
            params={"query": query, "per_page": 10}
        )
        response.raise_for_status()
        return response.json()["companies"]
    except Exception as e:
        print(f"Error searching for {query}: {e}")
        return []

def find_matches(debtors_df, confidence_threshold=0.95):
    """Find matches between debtor companies and Companies House data"""
    matcher = CompanyNameMatcher()
    results = []
    
    # Instead of filtering, we'll process all customer names
    # and use the matcher's preprocessing to determine if it's likely a company
    for idx, row in debtors_df.iterrows():
        original_name = row["CustomerName"]
        
        # Skip empty names
        if pd.isna(original_name) or not original_name.strip():
            continue
            
        # Use matcher's preprocessing to normalize the name
        normalized_name = matcher.normalize_company_name(original_name)
        
        # Skip if normalized name is empty (might indicate a personal name)
        if not normalized_name.strip():
            print(f"Skipping likely personal name: {original_name}")
            continue
            
        print(f"Processing: {original_name} (normalized: {normalized_name})")
        
        # Search using normalised name
        potential_matches = search_companies(normalized_name)
                
        if not potential_matches:
            print(f"No potential matches found for: {original_name}")
            results.append({
                "debtor_name": original_name,
                "normalized_name": normalized_name,
                "best_match_name": None,
                "best_match_number": None,
                "confidence": 0,
                "high_confidence_match": False,
                "match_details": None
            })
            continue
        
        # Find the best match using the matcher
        reference_names = [company["company_name"] for company in potential_matches]
        best_match, confidence, match_details = matcher.find_best_match(
            original_name, reference_names, threshold=confidence_threshold
        )
        
        # Find corresponding company details
        match_details_obj = None
        match_number = None
        
        if best_match:
            for company in potential_matches:
                if company["company_name"] == best_match:
                    match_details_obj = company
                    match_number = company["company_number"]
                    break
        
        results.append({
            "debtor_name": original_name,
            "normalized_name": normalized_name,
            "best_match_name": best_match,
            "best_match_number": match_number,
            "confidence": confidence,
            "high_confidence_match": confidence >= confidence_threshold,
            "match_details": match_details
        })
        
        print(f"Best match for '{original_name}': '{best_match}' with confidence {confidence:.2f}")
    
    return pd.DataFrame(results)

def get_company_details(company_number):
    """Get detailed information for a specific company by number"""
    try:
        response = requests.get(f"http://localhost:8000/company/{company_number}")
        response.raise_for_status()
        return response.json()
    except Exception as e:
        print(f"Error fetching company details for {company_number}: {e}")
        return None

def main():
    # Load debtor information
    debtors_df = load_debtors("backend/results-160224-debtor-info.csv")
    
    # Find matches
    matches_df = find_matches(debtors_df, confidence_threshold=0.95)
    
    # Display results
    print("\nMatching Results:")
    print(f"Total debtors processed: {len(matches_df)}")
    print(f"High confidence matches: {matches_df['high_confidence_match'].sum()}")
    
    # Get additional details for high confidence matches
    high_confidence_df = matches_df[matches_df["high_confidence_match"]]
    enriched_matches = []
    
    for idx, match in high_confidence_df.iterrows():
        if match["best_match_number"]:
            details = get_company_details(match["best_match_number"])
            if details:
                enriched_match = {
                    "debtor_name": match["debtor_name"],
                    "normalized_name": match["normalized_name"],
                    "matched_name": match["best_match_name"],
                    "company_number": match["best_match_number"],
                    "confidence": match["confidence"],
                    "company_status": details.get("company_status"),
                    "incorporation_date": details.get("incorporation_date"),
                    "company_category": details.get("company_category"),
                    "address": details.get("registered_office_address", {})
                }
                enriched_matches.append(enriched_match)
    
    # Create enriched DataFrame
    if enriched_matches:
        enriched_df = pd.DataFrame(enriched_matches)
        
        # Save results to CSV
        enriched_df.to_csv("high_confidence_matches.csv", index=False)
        matches_df.to_csv("all_matches.csv", index=False)
        
        print("\nHigh confidence matches:")
        print(enriched_df[["debtor_name", "matched_name", "company_number", "confidence"]])
        print("\nResults saved to 'high_confidence_matches.csv' and 'all_matches.csv'")
    else:
        print("No high confidence matches found")

if __name__ == "__main__":
    # Ensure the FastAPI server is running before executing this script
    main()