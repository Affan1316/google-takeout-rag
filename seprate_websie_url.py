import pandas as pd
import urllib.parse
import numpy as np

# 1. Define the extraction function
def get_actual_website(url):
    # Edge Case 1: Handle missing values (NaN) or non-string data
    if pd.isna(url) or not isinstance(url, str):
        return np.nan

    try:
        parsed_url = urllib.parse.urlparse(url)

        # Edge Case 2: Handle Google Redirect URLs (e.g., https://www.google.com/url?q=...)
        if 'google.' in parsed_url.netloc and parsed_url.path == '/url':
            # Extract query parameters
            query_params = urllib.parse.parse_qs(parsed_url.query)

            # Check if 'q' parameter exists (the actual destination)
            if 'q' in query_params:
                target_url = query_params['q'][0]
                target_parsed = urllib.parse.urlparse(target_url)
                return target_parsed.netloc # Returns the actual website domain (e.g., github.com)

        # Edge Case 3: Regular Google Searches or direct website links
        # If it's just a google search (path '/search'), it will return 'www.google.com'
        # If it's a direct link (e.g., developer.android.com), it returns that domain.
        return parsed_url.netloc

    except Exception as e:
        # Edge Case 4: Handle any severely malformed URLs that crash the parser
        return "Parsing Error"

# 2. Load your dataset
# Make sure your file 'parsed_Search.csv' is uploaded to your Colab environment
file_name = 'parsed_Search.csv'
try:
    df = pd.read_csv(file_name)
    print(f"Successfully loaded {len(df)} rows.")
except FileNotFoundError:
    print(f"Error: {file_name} not found. Please upload it to Colab first.")
    # Exit early if file isn't there
    raise

# 3. Apply the function to the 'Links' column to create a new column
df['Actual_Website'] = df['Links'].apply(get_actual_website)

# 4. Preview the changes
print("\nPreview of the extraction:")
print(df[['Links', 'Actual_Website']].head(10))

# 5. Save the updated dataset to a new CSV file
output_filename = 'parsed_Search_with_Websites.csv'
df.to_csv(output_filename, index=False)
print(f"\nProcessing complete! Saved the updated data to: {output_filename}")