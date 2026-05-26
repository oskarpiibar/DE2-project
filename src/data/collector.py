import requests
import pandas as pd
import time
import os
import re

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# We are hardcoding the token here for grading purposes
# Normally we'd use a .env file.
TOKEN = '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'
HEADERS = {
    'Authorization': f'token {TOKEN}',
    'Accept': 'application/vnd.github.v3+json'
}

"""
QUICK NOTE ON HOW WE COUNT THINGS (COMMITS, PRS, CONTRIBUTORS):
GitHub doesn't easily give us a single number for "total commits". 
If we downloaded every single commit just to count them, it would take forever and we'd get banned by the API.
WORKAROUND: We ask GitHub for exactly 1 item per page (per_page=1). 
GitHub sends back that 1 item, but also includes a hidden header saying how many total pages exist. 
Since there is 1 item per page, the total number of pages equals the exact total count! 
This lets us get the total number in just one fast request.
"""

def make_github_request(url):
    """
    This is a helper function to safely fetch data from GitHub.
    It automatically pauses the script if we hit GitHub's API rate limits,
    so it doesn't just crash and lose all the data.
    """
    while True:
        response = requests.get(url, headers=HEADERS)
        
        # Check if we ran out of our standard API requests
        remaining = int(response.headers.get('X-RateLimit-Remaining', 1))
        if remaining == 0:
            # Figure out exactly how long we need to wait until our limits reset
            reset_time = int(response.headers.get('X-RateLimit-Reset', time.time() + 60))
            sleep_time = max(reset_time - time.time(), 0) + 5
            print(f"\n[!] Out of API requests. Pausing script for {sleep_time:.0f} seconds until limits reset...")
            time.sleep(sleep_time)
            continue
            
        # Check if we triggered GitHub's abuse limits (asking too fast)
        if response.status_code == 403 and 'retry-after' in response.headers:
            sleep_time = int(response.headers.get('retry-after')) + 2
            print(f"\n[!] Asked too fast! Pausing for {sleep_time} seconds...")
            time.sleep(sleep_time)
            continue
            
        # Some repos disable features or have contributor lists that are too huge to load.
        # If that happens, just ignore it and return nothing.
        if response.status_code == 403:
            return None 
            
        # If it's a success (200), not found (404), or empty repo (409), we return the response.
        if response.status_code in [200, 404, 409]:
            return response
            
        # If something else goes wrong, return None so we can skip it.
        return None

def get_pagination_count(url):
    """Uses our pagination trick (from the note above) to count items without downloading them."""
    response = make_github_request(url)
    if response is None or response.status_code != 200:
        return None
        
    # Look for the 'Link' header where GitHub tells us the last page number
    if 'Link' in response.headers:
        link_header = response.headers['Link']
        last_page_match = re.search(r'page=(\d+)>; rel="last"', link_header)
        if last_page_match:
            return int(last_page_match.group(1))
            
    # If there is no Link header, it means everything fit on page 1
    data = response.json()
    if isinstance(data, list):
        return len(data)
    return 0

def fetch_top_repositories():
    repos_data = []
    
    print("Phase 1: Getting the initial list of repositories and basic stats...")
    for page in range(1, 11):
        print(f"Fetching search page {page}/10...")
        # Get repos with >50 stars, sorted by stars
        url = f"https://api.github.com/search/repositories?q=stars:>=50&sort=stars&order=desc&per_page=100&page={page}"
        
        response = make_github_request(url)
        if response and response.status_code == 200:
            for item in response.json().get('items', []):
                # Grab all the basic info for the rest of the group to use
                repos_data.append({
                    'name': item['name'],
                    'full_name': item['full_name'],
                    'stars': item['stargazers_count'],
                    'forks': item['forks_count'],
                    'watchers': item['watchers_count'],
                    'open_issues': item['open_issues_count'],
                    'language': item['language'],
                    'size': item['size'],
                    'created_at': item['created_at'],
                    'updated_at': item['updated_at'],
                    'description': item.get('description'),
                    'homepage': item.get('homepage'),
                    'license': item['license']['name'] if item.get('license') else None,
                    'topics': ", ".join(item.get('topics', [])),
                    'has_wiki': item.get('has_wiki'),
                    'has_pages': item.get('has_pages'),
                    'is_fork': item.get('fork'),
                    'archived': item.get('archived')
                })
        time.sleep(2) # Being polite to the GitHub search API
        
    print(f"\nPhase 2: Fetching the heavy metrics (Commits, PRs, etc.) for the {len(repos_data)} repos...")
    for index, repo in enumerate(repos_data):
        if index % 20 == 0 and index > 0:
            print(f"Update: Processed {index} out of {len(repos_data)} repositories...")
            
        full_name = repo['full_name']
        
        # 1. Use our pagination trick to rapidly count the heavy stuff
        repo['commits'] = get_pagination_count(f"https://api.github.com/repos/{full_name}/commits?per_page=1")
        repo['contributors'] = get_pagination_count(f"https://api.github.com/repos/{full_name}/contributors?per_page=1&anon=true")
        repo['releases'] = get_pagination_count(f"https://api.github.com/repos/{full_name}/releases?per_page=1")
        repo['open_pull_requests'] = get_pagination_count(f"https://api.github.com/repos/{full_name}/pulls?state=open&per_page=1")
        
        # 2. Make one extra call to the main repo object to get subscribers and network count
        detail_resp = make_github_request(f"https://api.github.com/repos/{full_name}")
        if detail_resp and detail_resp.status_code == 200:
            data = detail_resp.json()
            repo['subscribers_count'] = data.get('subscribers_count')
            repo['network_count'] = data.get('network_count')
        else:
            repo['subscribers_count'] = None
            repo['network_count'] = None
            
    return repos_data

if __name__ == "__main__":
    print("Starting data collection...")
    raw_data = fetch_top_repositories()
    
    # Save everything nicely into a CSV file using pandas
    df = pd.DataFrame(raw_data)
    os.makedirs(os.path.join(ROOT_DIR, 'data', 'raw'), exist_ok=True)
    df.to_csv(os.path.join(ROOT_DIR, 'data', 'raw', 'github_repositories.csv'), index=False)
    print("All done! Saved the dataset. Check the 'data/raw' folder for the CSV file.")