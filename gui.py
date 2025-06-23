import json
import requests
import bs4
from bs4 import BeautifulSoup as bs
from urllib.parse import urlparse
import urllib3
import os
import time
from datetime import datetime
import logging
import sys

logging.basicConfig(
    level=logging.INFO,
    format='[%(asctime)s] %(levelname)s: %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout)  # Only log to terminal
    ]
)
logger = logging.getLogger(__name__)

# Disable SSL warnings
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

class BacklinkBot:
    def __init__(self):
        # Initialize variables
        self.links = []
        self.current_link_index = 0
        self.running = False
        self.paused = False
        self.line_count = 0  # Track lines printed to terminal
        
        # Headers for HTTP requests
        self.headers = {
            'cache-control': 'max-age=0',
            'upgrade-insecure-requests': '1',
            'content-type': 'application/x-www-form-urlencoded',
            'user-agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/80.0.3987.163 Safari/537.36',
            'sec-fetch-dest': 'document',
            'accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.9',
            'sec-fetch-site': 'same-origin',
            'sec-fetch-mode': 'navigate',
            'sec-fetch-user': '?1',
            'accept-language': 'en-US,en;q=0.9',
        }
        
        # Default post data
        self.post_data = {
            'author': '',
            'email': '',
            'url': '',
            'comment': '',
            'comment_post_ID': '',
            'comment_parent': '',
            'submit': 'Post Comment',
            'ak_js': ''
        }
        
        # Statistics
        self.stats = {
            'total_processed': 0,
            'total_success': 0,
            'total_failed': 0,
            'session_start': None,
            'session_duration': 0
        }
        
        # Load configuration
        self.load_config()

    def load_config(self):
        """Load configuration from JSON files"""
        try:
            if os.path.exists('bot_config.json'):
                with open('bot_config.json', 'r') as f:
                    config = json.load(f)
                
                self.post_data['author'] = config.get('author', '')
                self.post_data['email'] = config.get('email', '')
                self.post_data['url'] = config.get('url', '')
                self.post_data['comment'] = config.get('comment', '')
                self.success_file = config.get('success_file', 'success.txt')
                self.delay = float(config.get('delay', '2'))
                
                logger.info("Configuration loaded from bot_config.json")
                self.line_count += 1  # Increment line count
            elif os.path.exists('postData.json'):
                with open('postData.json', 'r') as f:
                    self.post_data = json.load(f)
                
                self.success_file = 'success.txt'
                self.delay = 2.0
                logger.info("Configuration loaded from postData.json")
                self.line_count += 1  # Increment line count
            else:
                self.success_file = 'success.txt'
                self.delay = 2.0
                logger.info("No configuration files found. Using defaults.")
                self.line_count += 1  # Increment line count
        except Exception as e:
            logger.error(f"Error loading configuration: {str(e)}")
            self.line_count += 1  # Increment line count
            self._check_clear_terminal()

    def save_config(self):
        """Save current configuration to bot_config.json"""
        config = {
            'author': self.post_data['author'],
            'email': self.post_data['email'],
            'url': self.post_data['url'],
            'comment': self.post_data['comment'],
            'success_file': self.success_file,
            'delay': str(self.delay),
            'language': 'en'  # Default language
        }
        
        try:
            with open('bot_config.json', 'w') as f:
                json.dump(config, f, indent=4)
            logger.info("Configuration saved successfully")
            self.line_count += 1  # Increment line count
        except Exception as e:
            logger.error(f"Error saving configuration: {str(e)}")
            self.line_count += 1  # Increment line count
            self._check_clear_terminal()

    def load_links(self, links_file):
        """Load links from a file"""
        if not links_file:
            logger.error("No links file specified")
            self.line_count += 1  # Increment line count
            self._check_clear_terminal()
            return False
        
        try:
            with open(links_file, 'r') as f:
                lines = f.readlines()
                self.links = [line.strip() for line in lines 
                            if line.strip() and 
                            not line.strip().startswith('#') and 
                            line.strip().startswith('http')]
            
            if not self.links:
                logger.warning(f"No valid links found in {links_file}")
                self.line_count += 1  # Increment line count
                self._check_clear_terminal()
                return False
                
            logger.info(f"Loaded {len(self.links)} links from {links_file}")
            self.line_count += 1  # Increment line count
            self._check_clear_terminal()
            return True
        except Exception as e:
            logger.error(f"Error loading links: {str(e)}")
            self.line_count += 1  # Increment line count
            self._check_clear_terminal()
            return False

    def process_link(self, link, success_file):
        """Process a single link by submitting a comment form"""
        logger.info(f"[+] Processing {link}")
        self.line_count += 1  # Increment line count
        
        try:
            r = requests.get(link, verify=False, timeout=30)
        except Exception as e:
            logger.error(f"[-] Link Error: {link}")
            logger.error(f"[-] {str(e)}")
            self.line_count += 2  # Increment line count for two log messages
            self._check_clear_terminal()
            return False
        
        if not r or r.status_code != 200:
            logger.error(f"[-] Status {r.status_code} for Link: {link}")
            self.line_count += 1  # Increment line count
            self._check_clear_terminal()
            return False
        
        soup = bs(r.text, 'lxml')
        form = soup.find(id='commentform')
        
        if not form:
            logger.warning(f"[-] Comment Form Not Found")
            self.line_count += 1  # Increment line count
            self._check_clear_terminal()
            return False
        
        logger.info(f"[+] Form Found {link}")
        self.line_count += 1  # Increment line count
        
        inputs = {inp['name']: inp.get('value', '') for inp in form.find_all(attrs={"name": True})}
        
        # Update dynamic fields
        post_data = self.post_data.copy()
        for field in ['comment_post_ID', 'comment_parent', 'ak_js']:
            if field in inputs:
                post_data[field] = inputs.get(field, '')
        
        link_parse = urlparse(link)
        post_link = form.get('action', f"{link_parse.scheme}://{link_parse.netloc}/wp-comments-post.php")
        
        logger.info(f"[+] Submitting Form")
        self.line_count += 1  # Increment line count
        
        headers = self.headers.copy()
        headers['referer'] = link
        headers['origin'] = f"{link_parse.scheme}://{link_parse.netloc}"
        headers['authority'] = f"{link_parse.netloc}"
        
        try:
            r = requests.post(post_link, verify=False, data=post_data, headers=headers, timeout=30)
            
            if r.status_code in [200, 302, 303]:
                logger.info(f"[+] Form Submitted Successfully to {link_parse.netloc}")
                self.line_count += 1  # Increment line count
                
                with open(success_file, 'a') as f:
                    f.write(f'{link}\n')
                self._check_clear_terminal()
                return True
            else:
                logger.error(f"[-] Form Submission Failed with Status Code: {r.status_code}")
                self.line_count += 1  # Increment line count
                self._check_clear_terminal()
                return False
                
        except Exception as e:
            logger.error(f"[-] Error Submitting Form: {str(e)}")
            self.line_count += 1  # Increment line count
            self._check_clear_terminal()
            return False

    def _check_clear_terminal(self):
        """Clear the terminal if 20 lines have been printed"""
        if self.line_count >= 20:
            os.system('cls' if os.name == 'nt' else 'clear')
            self.line_count = 0  # Reset line count after clearing
            logger.info("Terminal cleared")
            self.line_count += 1  # Increment for the "Terminal cleared" message

    def run_bot(self, links_file):
        """Run the bot to process all links"""
        if not self.load_links(links_file):
            return
        
        if not all([self.post_data.get(key) for key in ['author', 'email', 'url', 'comment']]):
            logger.error("Required comment fields (author, email, url, comment) are not filled")
            self.line_count += 1  # Increment line count
            self._check_clear_terminal()
            return
        
        self.stats['session_start'] = datetime.now()
        self.running = True
        self.current_link_index = 0
        
        while self.running and self.current_link_index < len(self.links):
            if self.paused:
                time.sleep(0.5)
                continue
                
            link = self.links[self.current_link_index]
            try:
                success = self.process_link(link, self.success_file)
                if success:
                    self.stats['total_success'] += 1
                else:
                    self.stats['total_failed'] += 1
                    
                self.stats['total_processed'] += 1
                
            except Exception as e:
                logger.error(f"Error processing link: {str(e)}")
                self.line_count += 1  # Increment line count
                self.stats['total_failed'] += 1
                self.stats['total_processed'] += 1
                self._check_clear_terminal()
            
            self.current_link_index += 1
            logger.info(f"Progress: {self.current_link_index}/{len(self.links)} ({(self.current_link_index/len(self.links)*100):.1f}%)")
            self.line_count += 1  # Increment line count
            self._check_clear_terminal()
            
            time.sleep(self.delay)
        
        if self.current_link_index >= len(self.links):
            logger.info("Bot finished processing all links")
            logger.info(f"Processed: {self.stats['total_processed']}, Success: {self.stats['total_success']}, Failed: {self.stats['total_failed']}")
            self.line_count += 2  # Increment line count for two log messages
            self._check_clear_terminal()
        
        self.running = False

    def pause_bot(self):
        """Pause or resume the bot"""
        if not self.running:
            logger.info("Bot is not running")
            self.line_count += 1  # Increment line count
            self._check_clear_terminal()
            return
        
        self.paused = not self.paused
        status = "paused" if self.paused else "resumed"
        logger.info(f"Bot {status}")
        self.line_count += 1  # Increment line count
        self._check_clear_terminal()

    def stop_bot(self):
        """Stop the bot"""
        if not self.running:
            logger.info("Bot is not running")
            self.line_count += 1  # Increment line count
            self._check_clear_terminal()
            return
        
        self.running = False
        self.paused = False
        logger.info("Bot stopped")
        self.line_count += 1  # Increment line count
        self._check_clear_terminal()

    def export_statistics(self, filename="backlink_stats.csv"):
        """Export statistics to a CSV file"""
        try:
            with open(filename, "w") as f:
                f.write("Statistic,Value\n")
                f.write(f"Date,{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
                f.write(f"Total Processed,{self.stats['total_processed']}\n")
                f.write(f"Total Success,{self.stats['total_success']}\n")
                f.write(f"Total Failed,{self.stats['total_failed']}\n")
                
                success_rate = 0
                if self.stats['total_processed'] > 0:
                    success_rate = (self.stats['total_success'] / self.stats['total_processed']) * 100
                f.write(f"Success Rate,{success_rate:.2f}%\n")
                
                if self.stats['session_start']:
                    duration = datetime.now() - self.stats['session_start']
                    f.write(f"Session Duration,{int(duration.total_seconds())} seconds\n")
                
            logger.info(f"Statistics exported to {filename}")
            self.line_count += 1  # Increment line count
            self._check_clear_terminal()
        except Exception as e:
            logger.error(f"Error exporting statistics: {str(e)}")
            self.line_count += 1  # Increment line count
            self._check_clear_terminal()

if __name__ == "__main__":
    # Create bot instance
    bot = BacklinkBot()
    
    # Example usage
    links_file = "links.txt"
    
    # Set example post data if not loaded from config
    if not bot.post_data['author']:
        bot.post_data['author'] = "Example Author"
        bot.post_data['email'] = "example@email.com"
        bot.post_data['url'] = "https://example.com"
        bot.post_data['comment'] = "This is an example comment."
        bot.save_config()
    
    # Run the bot
    bot.run_bot(links_file)
    
    # Export statistics
    bot.export_statistics()
