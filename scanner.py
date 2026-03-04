import os
import feedparser
import google.generativeai as genai
import urllib.parse
from bs4 import BeautifulSoup
import smtplib
from email.message import EmailMessage

# --- CONFIGURATION ---
# Now pulling securely from the system environment
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")
EMAIL_ADDRESS = os.environ.get("EMAIL_ADDRESS")
EMAIL_PASSWORD = os.environ.get("EMAIL_PASSWORD")

# ... (Keep the rest of your arXiv categories and code exactly the same) ...

# Specific concepts to explicitly filter for in the daily feed
RESEARCH_KEYWORDS = [
    "Carnot groups",
    "geometric measure theory",
    "rectifiability",
    "Lie groups"
]

# Authors to build the thematic baseline via the arXiv API
AUTHOR_NAMES = [
    "Terence Tao",
    "Peter Scholze"
]

# Every top-level arXiv category
ARXIV_CATEGORIES = [
    "math", "cs", "physics", "astro-ph", "cond-mat", "gr-qc", 
    "hep-ex", "hep-lat", "hep-ph", "hep-th", "math-ph", "nlin", 
    "nucl-ex", "nucl-th", "q-bio", "q-fin", "quant-ph", "stat", 
    "eess", "econ"
]

# Programmatically generate the official RSS URLs
RSS_URLS = [f"https://rss.arxiv.org/rss/{cat}" for cat in ARXIV_CATEGORIES]

genai.configure(api_key=GEMINI_API_KEY)
model = genai.GenerativeModel('gemini-2.0-flash')

def get_arxiv_context(author_list):
    """Fetches publication titles and abstracts from the arXiv API for specific authors."""
    all_context = []
    
    for author in author_list:
        print(f"Fetching arXiv baseline records for: {author}")
        query = f'au:"{author}"'
        encoded_query = urllib.parse.quote(query)
        
        url = f"http://export.arxiv.org/api/query?search_query={encoded_query}&max_results=5&sortBy=submittedDate&sortOrder=descending"
        
        try:
            feed = feedparser.parse(url)
            for entry in feed.entries:
                clean_summary = BeautifulSoup(entry.summary, 'html.parser').get_text().strip()
                context_string = f"Title: {entry.title}\nAbstract: {clean_summary[:400]}"
                all_context.append(context_string)
        except Exception as e:
            print(f"Warning: Could not fetch arXiv data for {author} ({e}).")
            
    return all_context

def get_all_rss_items(url_list):
    """Loops through the entire arXiv daily firehose."""
    all_entries = []
    print(f"Scanning {len(url_list)} arXiv categories. This may take a minute or two...")
    
    for url in url_list:
        try:
            feed = feedparser.parse(url)
            # Fallback category name if the feed title is missing
            category_name = feed.feed.get('title', url.split('/')[-1].upper()) 
            
            for entry in feed.entries:
                raw_summary = entry.get('summary', '')
                clean_summary = BeautifulSoup(raw_summary, 'html.parser').get_text().strip()
                
                all_entries.append({
                    "category": category_name,
                    "title": entry.title,
                    "link": entry.link,
                    "summary": clean_summary[:400] 
                })
        except Exception as e:
            print(f"Failed to parse {url}: {e}")
            
    return all_entries

def get_ai_analysis(new_items, arxiv_context, keywords):
    """Feeds the massive daily list to Gemini to find the needles in the haystack."""
    prompt = f"""
    CONTEXT - RESEARCH FOCUS:
    I am actively looking for new papers directly related to these concepts:
    {keywords}
    
    Additionally, I track the overarching themes found in these recent baseline publications:
    {arxiv_context}
    
    TASK:
    Review the following massive list of daily arXiv submissions.
    1. Identify which papers have a strong mathematical or thematic connection to the concepts and baseline publications provided above.
    2. Select ONLY the highly relevant items. Be incredibly strict. Do not include loose matches.
    3. Group them by their arXiv category.
    4. Provide a 1-2 sentence summary for each explaining exactly WHY it is relevant, and include the raw URL on a new line.
    
    FORMATTING CONSTRAINT:
    Do NOT use Markdown. Do not use asterisks for bolding. Just use plain text formatting with standard spacing and raw URLs so it renders well in a plain text email.

    DAILY ARXIV SUBMISSIONS:
    {new_items}

    If no items strongly overlap with the research focus today, exactly respond with: No relevant content today.
    """
    
    try:
        response = model.generate_content(prompt, generation_config={"temperature": 0.1})
        return response.text.strip()
    except Exception as e:
        print(f"Gemini API Error: {e}")
        return "Error generating AI summary."

def send_email(summary):
    msg = EmailMessage()
    msg.set_content(summary)
    msg['Subject'] = f"Daily arXiv Digest: AI Curated Updates"
    msg['From'] = EMAIL_ADDRESS
    msg['To'] = EMAIL_ADDRESS

    try:
        with smtplib.SMTP_SSL('smtp.gmail.com', 465) as smtp:
            smtp.login(EMAIL_ADDRESS, EMAIL_PASSWORD)
            smtp.send_message(msg)
    except Exception as e:
        print(f"Failed to send email: {e}")

# --- EXECUTION ---
print("Extracting baseline themes from arXiv API...")
arxiv_themes = get_arxiv_context(AUTHOR_NAMES)

print("Fetching the daily arXiv feeds...")
all_new_stuff = get_all_rss_items(RSS_URLS)

if all_new_stuff:
    print(f"Analyzing {len(all_new_stuff)} daily submissions against your research focus...")
    ai_summary = get_ai_analysis(all_new_stuff, arxiv_themes, RESEARCH_KEYWORDS)
    
    if ai_summary == "Error generating AI summary.":
        print("Script halted due to API error.")
    elif "No relevant content today" not in ai_summary:
        print("Sending email...")
        send_email(ai_summary)
        print("Success: Curated research email sent.")
    else:
        print("Nothing matching your research themes found today.")
else:
    print("No items found in any arXiv feeds today. (Note: arXiv does not announce papers on Friday or Saturday nights).")
