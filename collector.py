import requests
import pandas as pd
import time
import os
import re

# Hardcoded token as suggested in the PDF. In a real project, we would load this from .env for security.
TOKEN = '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'
HEADERS = {
    'Authorization': f'token {TOKEN}',
    'Accept': 'application/vnd.github.v3+json'
}

"""
HOW WE COUNT COMMITS: 
GitHub's API does not provide a "total_commits" number. Downloading thousands 
of commits just to count them would be too slow and get us banned for API limits.
WORKAROUND: We ask the API for exactly 1 commit per page (per_page=1). GitHub 
sends back that 1 commit, plus a hidden header saying how many total pages exist. 
Since there is 1 commit per page, the total number of pages equals the exact 
total commit count. We get the whole count in one request, otherwise we would have to download every single commit.
"""

def get_commit_count(full_name):
    # Gets the exact commit count for a repository using pagination headers.
    url = f"https://api.github.com/repos/{full_name}/commits?per_page=1"
    
    while True:
        response = requests.get(url, headers=HEADERS)
        
        # Handle API rate limit specific to the call
        if response.status_code in [403, 429]: # forbidden / too many requests codes
            # This calculates exactly seconds we need to wait based on github reset clock
            reset_time = int(response.headers.get('X-RateLimit-Reset', time.time() + 60))
            sleep_time = max(reset_time - time.time(), 0) + 5
            print(f"Rate limit hit for {full_name}! Sleeping for {sleep_time:.0f} seconds...")
            time.sleep(sleep_time)
            continue # retry
            
        if response.status_code == 200: # Success code
            if 'Link' in response.headers:
                # Find the page number of the last page to get total commits
                link_header = response.headers['Link']
                last_page_match = re.search(r'page=(\d+)>; rel="last"', link_header)
                if last_page_match:
                    return int(last_page_match.group(1))
            # If no link header, there's only 1 page of commits
            return len(response.json())
        elif response.status_code == 409: # 409 repository is empty (no commits)
            return 0
        else: # Any other: fallback.
            return None

def fetch_top_repositories():
    repos_data =[]
    
    # 1: Get the first 1000 items (10 pages of 100)
    for page in range(1, 11):
        print(f"Fetching page {page}...")
        url = f"https://api.github.com/search/repositories?q=stars:>=50&sort=stars&order=desc&per_page=100&page={page}"
        
        while True:
            response = requests.get(url, headers=HEADERS)
            
            # Better Rate Limit Handling (sleep using X-RateLimit-Reset' which tells us when the limit will reset)
            if response.status_code in [403, 429]:
                reset_time = int(response.headers.get('X-RateLimit-Reset', time.time() + 60))
                sleep_time = max(reset_time - time.time(), 0) + 5
                print(f"Rate limit hit! Sleeping for {sleep_time:.0f} seconds...")
                time.sleep(sleep_time)
                continue # Retry
                
            if response.status_code == 200:
                items = response.json().get('items',[])
                for item in items:
                    # Extract the raw features the group might need
                    repo_info = {
                        'name': item['name'],
                        'full_name': item['full_name'],
                        'stars': item['stargazers_count'],
                        'forks': item['forks_count'],
                        'watchers': item['watchers_count'], 
                        'open_issues': item['open_issues_count'],
                        'language': item['language'],
                        'size': item['size'],
                        'created_at': item['created_at'],
                        'updated_at': item['updated_at']
                    }
                    repos_data.append(repo_info)
                break # Success
            else:
                print(f"Error fetching data: {response.status_code}")
                break # Break on unhandled errors
                
        # Delay to avoid the the 30 requests/min
        time.sleep(2) 
        
    # Phase 2: Add the commit counts to each repository
    print("\nFetching commit counts (takes a while due to rate limits)...")
    for index, repo in enumerate(repos_data):
        if index % 50 == 0 and index > 0:
            print(f"Processed {index} out of {len(repos_data)} repositories...")
            
        # Call the function to grab the commits and add it.
        repo['commits'] = get_commit_count(repo['full_name'])
        
        # tiny delay again
        time.sleep(0.5)
        
    return repos_data

if __name__ == "__main__":
    print("Starting data collection...")
    raw_data = fetch_top_repositories()
    
    # Convert to Pandas DataFrame
    df = pd.DataFrame(raw_data)
    
    # Save it
    os.makedirs('data/raw', exist_ok=True)
    df.to_csv('data/raw/github_repositories.csv', index=False)
    print("Data collection complete. Saved 1000 repositories with commit counts!")