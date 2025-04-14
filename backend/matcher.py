import pandas as pd
import numpy as np
import re
import string
from fuzzywuzzy import fuzz, process
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity
import spacy
import nltk
from nltk.corpus import stopwords
from nltk.tokenize import word_tokenize

# Download necessary NLTK resources
nltk.download('punkt')
nltk.download('stopwords')

# Load English language model for spaCy
try:
    nlp = spacy.load("en_core_web_md")
except:
    # If model not installed, download it
    import subprocess
    subprocess.call([f"python -m spacy download en_core_web_md"], shell=True)
    nlp = spacy.load("en_core_web_md")

class CompanyNameMatcher:
    def __init__(self):
        """Initialize the company name matcher with required resources"""
        self.stop_words = set(stopwords.words('english'))
        self.company_suffixes = {
            'ltd': 'limited',
            'inc': 'incorporated',
            'llc': 'limited liability company',
            'llp': 'limited liability partnership',
            'corp': 'corporation',
            'co': 'company',
            'gmbh': 'gesellschaft mit beschränkter haftung',
            'ag': 'aktiengesellschaft',
            'sa': 'société anonyme',
            'nv': 'naamloze vennootschap',
            'bv': 'besloten vennootschap',
            'plc': 'public limited company',
            'lp': 'limited partnership',
            'pllc': 'professional limited liability company',
            'pty': 'proprietary',
            'pvt': 'private',
        }
        
        # Legal entity type patterns for removal
        self.entity_patterns = [
            r'\b(?:limited|ltd|inc|incorporated|llc|llp|corp|corporation|co|company|'
            r'gmbh|ag|sa|nv|bv|plc|lp|pllc|pty|pvt)\b',
            r'\bl\.?l\.?c\.?\b',
            r'\bl\.?l\.?p\.?\b',
            r'\bp\.?l\.?c\.?\b',
            r'\bp\.?t\.?y\.?\b',
            r'\bp\.?v\.?t\.?\b',
            r'\bi\.?n\.?c\.?\b',
            r'\bl\.?t\.?d\.?\b',
            r'\bc\.?o\.?\b',
            r'\bc\.?o\.?r\.?p\.?\b',
        ]
        
        # Common words in company names that don't add much meaning
        self.common_words = {
            'group', 'holdings', 'international', 'global', 'world', 'worldwide', 
            'solutions', 'services', 'technologies', 'systems', 'industries', 'products',
            'enterprises', 'ventures', 'partners', 'consulting', 'investment', 'investments',
            'management', 'financial', 'capital', 'bank', 'trust', 'trading', 'media',
            'communications', 'technology', 'tech', 'software', 'networks', 'network',
            'pharmaceuticals', 'pharma', 'healthcare', 'medical', 'research', 'development',
            'energy', 'resources', 'property', 'properties', 'real estate', 'construction'
        }
        
        # Abbreviation mappings
        self.abbreviation_map = {
            'intl': 'international',
            'int': 'international',
            'natl': 'national',
            'nat': 'national',
            'grp': 'group',
            'tech': 'technology',
            'techs': 'technologies',
            'sys': 'systems',
            'svcs': 'services',
            'svc': 'service',
            'sol': 'solutions',
            'assoc': 'associates',
            'assn': 'association',
            'bros': 'brothers',
            'ctr': 'center',
            'cntl': 'control',
            'comm': 'communications',
            'comm': 'community',
            'mgmt': 'management',
            'mfg': 'manufacturing',
            'eng': 'engineering',
            'equip': 'equipment',
            'elec': 'electric',
            'elec': 'electronic',
            'envir': 'environmental',
            'dev': 'development',
            'dist': 'distributing',
            'distr': 'distribution',
            'ent': 'enterprises',
            'govt': 'government',
            'hosp': 'hospital',
            'inst': 'institute',
            'labs': 'laboratories',
            'maint': 'maintenance',
            'mtc': 'maintenance',
            'med': 'medical',
            'petro': 'petroleum',
            'prod': 'products',
            'pub': 'publishing',
            'transp': 'transportation',
            'univ': 'university',
            'util': 'utility',
            'utils': 'utilities'
        }
        
        # Countries and locations for contextual matching
        self.countries = {
            'us': 'united states', 'usa': 'united states', 'uk': 'united kingdom', 
            'gb': 'great britain', 'uae': 'united arab emirates'
        }

    def preprocess_company_name(self, name):
        """
        Preprocess a company name by:
        1. Converting to lowercase
        2. Removing punctuation
        3. Standardizing spacing
        """
        if name is None or not isinstance(name, str):
            return ""
        
        # Convert to lowercase
        name = name.lower()
        
        # Remove certain punctuation but keep some meaningful ones
        for char in "'\"!@#$%^&*()_+={}[]|\\:;<>,.?/~`":
            name = name.replace(char, ' ')
        
        # Replace ampersand with 'and'
        name = name.replace('&', ' and ')
        
        # Normalize whitespaces
        name = ' '.join(name.split())
        
        return name
        
    def normalize_company_name(self, name):
        """
        Normalize a company name by:
        1. Performing basic preprocessing
        2. Expanding abbreviations
        3. Removing common legal entity types
        4. Standardizing common terms
        """
        # Basic preprocessing
        name = self.preprocess_company_name(name)
        if not name:
            return ""
            
        # Expand abbreviations
        tokens = name.split()
        normalized_tokens = []
        
        for token in tokens:
            # Check if token is an abbreviation and expand it
            if token in self.abbreviation_map:
                normalized_tokens.append(self.abbreviation_map[token])
            # Check if token is a country code and expand it
            elif token in self.countries:
                normalized_tokens.append(self.countries[token])
            # Add the token as is
            else:
                normalized_tokens.append(token)
        
        # Join tokens back into a string
        normalized_name = ' '.join(normalized_tokens)
        
        # Remove legal entity types
        for pattern in self.entity_patterns:
            normalized_name = re.sub(pattern, '', normalized_name, flags=re.IGNORECASE)
        
        # Remove common words at the end of company names if they're standalone
        for common_word in self.common_words:
            pattern = r'\s+' + re.escape(common_word) + r'$'
            normalized_name = re.sub(pattern, '', normalized_name, flags=re.IGNORECASE)
            
        # Standardize common terms
        normalized_name = normalized_name.replace('and co', '')
        normalized_name = normalized_name.replace('& co', '')
        
        # Final cleanup of extra spaces
        normalized_name = re.sub(r'\s+', ' ', normalized_name).strip()
        
        return normalized_name
    
    def extract_core_name(self, name):
        """Extract the core name by removing common words and entity types"""
        normalized = self.normalize_company_name(name)
        
        # Remove stopwords
        tokens = word_tokenize(normalized)
        filtered_tokens = [w for w in tokens if w.lower() not in self.stop_words]
        
        # Remove common words in company names
        filtered_tokens = [w for w in filtered_tokens if w.lower() not in self.common_words]
        
        # Join back
        core_name = ' '.join(filtered_tokens)
        
        return core_name
    
    def tokenize_company_name(self, name):
        """Tokenize and normalize a company name using NLP"""
        if not name:
            return []
            
        # Process with spaCy for advanced entity recognition
        doc = nlp(name)
        
        # Extract meaningful tokens
        tokens = []
        for token in doc:
            if not token.is_stop and not token.is_punct and token.text.strip():
                # Lemmatize and add to tokens
                tokens.append(token.lemma_.lower())
                
        return tokens
    
    def calculate_similarity_scores(self, name1, name2):
        """
        Calculate multiple similarity scores between two company names:
        1. Exact match (after normalization)
        2. Token match ratio
        3. Fuzzy string ratio
        4. Partial token ratio
        5. TF-IDF cosine similarity
        6. Word embedding similarity
        """
        # Step 1: Normalize both names
        norm_name1 = self.normalize_company_name(name1)
        norm_name2 = self.normalize_company_name(name2)
        
        # Step 2: Extract core names
        core_name1 = self.extract_core_name(name1)
        core_name2 = self.extract_core_name(name2)
        
        # Step 3: Tokenize names
        tokens1 = set(self.tokenize_company_name(norm_name1))
        tokens2 = set(self.tokenize_company_name(norm_name2))
        
        scores = {}
        
        # Exact match after normalization
        scores['exact_match'] = 1.0 if norm_name1 == norm_name2 else 0.0
        
        # Core name exact match
        scores['core_match'] = 1.0 if core_name1 == core_name2 and core_name1 != "" else 0.0
        
        # Token overlap ratio
        if tokens1 and tokens2:
            scores['token_overlap'] = len(tokens1.intersection(tokens2)) / max(len(tokens1), len(tokens2))
        else:
            scores['token_overlap'] = 0.0
        
        # Fuzzy string matching
        scores['fuzzy_ratio'] = fuzz.ratio(norm_name1, norm_name2) / 100.0
        scores['partial_ratio'] = fuzz.partial_ratio(norm_name1, norm_name2) / 100.0
        scores['token_sort_ratio'] = fuzz.token_sort_ratio(norm_name1, norm_name2) / 100.0
        scores['token_set_ratio'] = fuzz.token_set_ratio(norm_name1, norm_name2) / 100.0
        
        # Word embedding similarity using spaCy
        if norm_name1 and norm_name2:
            doc1 = nlp(norm_name1)
            doc2 = nlp(norm_name2)
            if doc1.vector_norm and doc2.vector_norm:  # Check if vectors are valid
                scores['embedding_similarity'] = doc1.similarity(doc2)
            else:
                scores['embedding_similarity'] = 0.0
        else:
            scores['embedding_similarity'] = 0.0
        
        return scores
    
    def is_high_confidence_match(self, name1, name2, threshold=0.95):
        """
        Determine if two company names match with high confidence (>95%)
        using a weighted ensemble of similarity measures
        """
        # Calculate all similarity scores
        scores = self.calculate_similarity_scores(name1, name2)
        
        # Check for exact match scenarios (highest confidence)
        if scores['exact_match'] == 1.0:
            return True, 1.0, scores
            
        if scores['core_match'] == 1.0 and scores['token_overlap'] > 0.8:
            return True, 0.98, scores
        
        # Weighted ensemble score
        weights = {
            'exact_match': 0.15,
            'core_match': 0.15,
            'token_overlap': 0.15,
            'fuzzy_ratio': 0.1,
            'partial_ratio': 0.1,
            'token_sort_ratio': 0.15,
            'token_set_ratio': 0.1,
            'embedding_similarity': 0.1
        }
        
        weighted_score = sum(scores[k] * weights[k] for k in weights)
        
        # Additional logic for high confidence matching
        # If certain key metrics are very high but others are lower
        if scores['token_set_ratio'] > 0.95 and scores['token_overlap'] > 0.8:
            weighted_score = max(weighted_score, 0.96)  # Boost confidence
            
        # If partial match is perfect but order is different
        if scores['partial_ratio'] == 1.0 and scores['token_sort_ratio'] > 0.9:
            weighted_score = max(weighted_score, 0.97)
            
        # Return result with confidence score
        return weighted_score >= threshold, weighted_score, scores
    
    def find_best_match(self, query_name, reference_list, threshold=0.95):
        """
        Find the best match for a company name from a reference list
        Returns: best match, confidence score, and detailed match information
        """
        best_match = None
        best_score = 0
        best_details = None
        
        for ref_name in reference_list:
            is_match, confidence, details = self.is_high_confidence_match(query_name, ref_name, threshold)
            
            if is_match and confidence > best_score:
                best_match = ref_name
                best_score = confidence
                best_details = details
                
        return best_match, best_score, best_details
    
    def batch_match(self, query_names, reference_names, threshold=0.95):
        """
        Match a list of query names against a reference list
        Returns a DataFrame with matches and confidence scores
        """
        results = []
        
        for query in query_names:
            best_match, confidence, details = self.find_best_match(query, reference_names, threshold)
            
            result = {
                'query_name': query,
                'normalized_query': self.normalize_company_name(query),
                'best_match': best_match,
                'normalized_match': self.normalize_company_name(best_match) if best_match else None,
                'confidence': confidence,
                'is_high_confidence': confidence >= threshold
            }
            
            # Add detailed similarity scores
            if details:
                for score_type, score in details.items():
                    result[f'score_{score_type}'] = score
                    
            results.append(result)
            
        return pd.DataFrame(results)


# Example usage
if __name__ == "__main__":
    # Create instance of the matcher
    matcher = CompanyNameMatcher()
    
    # Example company names
    query_names = [
        "Apple Inc.",
        "Microsoft Corporation",
        "Amazon.com, Inc.",
        "Google LLC",
        "International Business Machines Corp.",
        "Meta Platforms, Inc."
    ]
    
    reference_names = [
        "Apple Incorporated",
        "Apple Computer, Inc.",
        "Microsoft Corp",
        "Microsoft",
        "Amazon",
        "Amazon.com",
        "Alphabet Inc. (Google)",
        "Google",
        "IBM Corporation",
        "International Business Machines",
        "Facebook, Inc.",
        "Meta"
    ]
    
    # Test single match
    name1 = "Apple Inc."
    name2 = "Apple Incorporated"
    is_match, confidence, details = matcher.is_high_confidence_match(name1, name2)
    print(f"Match test: {name1} vs {name2}")
    print(f"Is high-confidence match: {is_match}, Confidence: {confidence:.2f}")
    print("Detailed scores:", details)
    print("\n")
    
    # Test batch matching
    results_df = matcher.batch_match(query_names, reference_names)
    print("Batch matching results:")
    print(results_df[['query_name', 'best_match', 'confidence', 'is_high_confidence']])