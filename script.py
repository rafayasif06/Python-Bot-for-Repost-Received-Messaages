import asyncio
import os
import re
import sys
import json
from datetime import datetime
from pathlib import Path
from urllib.parse import urlparse
from playwright.async_api import async_playwright
import logging

# Load configuration from config.json


def load_config():
  """Load configuration from config.json file."""
  try:
    config_path = os.path.join(os.path.dirname(
      os.path.abspath(__file__)), 'config.json')
    with open(config_path, 'r', encoding='utf-8') as f:
      config = json.load(f)
    print(f"Configuration loaded successfully from {config_path}")
    return config
  except FileNotFoundError:
    print("Warning: config.json not found. Using default values.")
    return {
        "done_message_text": "Done",
        "scrolls_count_for_each_capture": 2,
        "iterations_count": 2
    }
  except json.JSONDecodeError as e:
    print(f"Error parsing config.json: {e}. Using default values.")
    return {
        "done_message_text": "Done",
        "scrolls_count_for_each_capture": 2,
        "iterations_count": 2
    }


# Load configuration
CONFIG = load_config()

# User-configurable constants from config
DONE_MESSAGE_TEXT = CONFIG.get("done_message_text", "Done")
SCROLLS_COUNT_FOR_EACH_CAPTURE = CONFIG.get(
  "scrolls_count_for_each_capture", 2)
ITERATIONS_COUNT = CONFIG.get("iterations_count", 3)


# Setup logging to file
logs_dir = Path(os.path.dirname(os.path.abspath(__file__))) / 'logs'
logs_dir.mkdir(exist_ok=True)
log_filename = datetime.now().strftime('%Y-%m-%d_%H-%M-%S.log')
log_path = logs_dir / log_filename
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s %(levelname)s %(message)s',
    handlers=[
        logging.FileHandler(log_path, encoding='utf-8'),
        # Uncomment the next line to also log to console
        # logging.StreamHandler(sys.stdout)
    ]
)


def log(msg):
  logging.info(msg)
  print(msg)


def get_int_input(prompt, valid_options=None):
  """Gets integer input from the user, ensuring it's valid."""
  while True:
    try:
      user_input = int(input(prompt))
      if valid_options and user_input not in valid_options:
        print(f"Invalid choice. Please enter one of {valid_options}.")
      else:
        return user_input
    except ValueError:
      print("Invalid input. Please enter a number.")


def get_interval_hours():
  """Gets the time interval in hours (1-5)."""
  while True:
    hours = get_int_input("Enter time interval in hours (1-5): ")
    if 1 <= hours <= 5:
      return hours
    print("Please enter a value between 1 and 5 hours.")


def parse_cookies_from_file(file_path):
  """Parse cookies from a tab-separated file."""
  cookies = []

  try:
    with open(file_path, 'r', encoding='utf-8') as file:
      lines = file.readlines()

      for line in lines:
        # Skip comments and empty lines
        if line.strip() == '' or line.strip().startswith('//'):
          continue

        # Split by tabs
        parts = line.strip().split('\t')
        if len(parts) < 3:  # Need at least name, value, domain
          continue

        cookie = {
            'name': parts[0],
            'value': parts[1],
            'domain': parts[2],
        }

        # Add path if available
        if len(parts) > 3:
          cookie['path'] = parts[3]

        # Check for secure flag (✓ character in part 5 or 6)
        if len(parts) > 5 and '✓' in parts[5]:
          cookie['secure'] = True

        # Check for httpOnly flag (✓ character in part 6)
        if len(parts) > 6 and '✓' in parts[6]:
          cookie['httpOnly'] = True

        # Add sameSite if available (part 7)
        if len(parts) > 7 and parts[7] in ['None', 'Lax', 'Strict']:
          cookie['sameSite'] = parts[7]

        cookies.append(cookie)
  except Exception as e:
    print(f"Error parsing cookies: {e}")

  return cookies


async def retweet_post(page, retry_count=0, max_retries=3):
  """Retweets a post that's open in the current page."""
  try:
    if retry_count > 0:
      log(f"Retrying retweet attempt {retry_count + 1}/{max_retries + 1}...")
      # Reload page and wait longer on retry with increasing wait times
      log("Reloading page before retry...")
      await page.reload(wait_until="domcontentloaded")
      # Increasing wait times: 5s, 8s, 12s for retries 1, 2, 3
      wait_time = 5 + (retry_count * 3)
      log(f"Waiting {wait_time} seconds after page reload...")
      await asyncio.sleep(wait_time)
    else:
      log("Attempting to retweet the post...")
      # Wait a moment to make sure the page is fully loaded
      await asyncio.sleep(3)

    # Check if the tweet is already retweeted by looking for unretweet data-testid
    try:
      unretweet_exists = await page.get_by_test_id("unretweet").count() > 0

      if unretweet_exists:
        log("Found unretweet button - post is already retweeted, skipping...")
        return "already_retweeted"

      # Double check with text as backup
      already_retweeted = await page.get_by_text("Undo repost", exact=True).count() > 0
      if not already_retweeted:
        already_retweeted = await page.get_by_text("Undo Retweet", exact=True).count() > 0

      if already_retweeted:
        log("Tweet is already retweeted (confirmed by text), skipping...")
        return "already_retweeted"
    except Exception as e:
      # Try multiple selectors to find the retweet button
      log(f"Error checking if tweet is already retweeted: {e}")
    retweet_button_selectors = [
        'button[data-testid="retweet"]',
        'button[aria-label*="repost"]',
        'button[aria-label*="Repost"]',
        'button[aria-label*="reposts"]',
        'button[aria-label*="Reposts"]',
        'button[aria-label*="retweet"]',
        'button[aria-label*="Retweet"]',
        'div[role="button"][data-testid="retweet"]',
        'div[aria-label*="repost"][role="button"]'
    ]

    retweet_button = None
    for selector in retweet_button_selectors:
      try:
        log(f"Trying to find retweet button with selector: {selector}")
        # Increase timeout for retries
        timeout = 5000 + (retry_count * 2000)  # 5s, 7s, 9s, 11s
        button = await page.wait_for_selector(selector, timeout=timeout)
        if button:
          retweet_button = button
          log(f"Found retweet button with selector: {selector}")
          break
      except Exception as e:
        log(f"Selector {selector} failed: {e}")
        continue

    if not retweet_button:
      log("Could not find retweet button with any selector")
      # Last resort: try to find any buttons that might be the retweet button
      try:
        log("Trying to find any button that might be the retweet button...")
        all_buttons = await page.query_selector_all('button')

        for btn in all_buttons:
          try:
            aria_label = await btn.get_attribute('aria-label')
            if aria_label and ('retweet' in aria_label.lower() or 'repost' in aria_label.lower()):
              log(
                f"Found potential retweet button with aria-label: {aria_label}")
              retweet_button = btn
              break
          except:
            pass
      except Exception as e:
        log(f"Last resort button search failed: {e}")

    if not retweet_button:
      log("Could not find retweet button with any method")
      return "failed"

    # Click the retweet button
    await retweet_button.click()
    log("Clicked retweet button")

    # Wait for the retweet menu to appear
    # Try multiple selectors for the retweet/repost option in the menu
    await asyncio.sleep(1.5)
    retweet_option_selectors = [
        'div[data-testid="retweetConfirm"]',
        'div[role="menuitem"][data-testid="retweet"]',
        'div[data-testid="repost"]',
        'span:has-text("Retweet")',
        'span:has-text("Repost")',
        'div[role="menuitem"]:has-text("Repost")',
        'div[role="menuitem"]:has-text("Retweet")',
        'div[role="menu"] span:has-text("Retweet")',
        'div[role="menu"] span:has-text("Repost")'
    ]

    retweet_option = None
    for selector in retweet_option_selectors:
      try:
        log(f"Trying to find retweet option with selector: {selector}")
        # Increase timeout for retries
        timeout = 5000 + (retry_count * 2000)  # 5s, 7s, 9s, 11s
        option = await page.wait_for_selector(selector, timeout=timeout)
        if option:
          retweet_option = option
          log(f"Found retweet option with selector: {selector}")
          break
      except Exception as e:
        log(f"Selector {selector} failed: {e}")

    if not retweet_option:
      log("Could not find retweet option with primary selectors")
      # Last resort: try to find any menu item that might be the retweet option
      try:
        log("Trying to find any menu item that might be the retweet option...")
        menu_items = await page.query_selector_all('div[role="menuitem"]')

        for item in menu_items:
          try:
            item_text = await page.evaluate('(element) => element.textContent', item)
            if item_text and ('retweet' in item_text.lower() or 'repost' in item_text.lower()):
              log(f"Found potential retweet option with text: {item_text}")
              retweet_option = item
              break
          except:
            pass
      except Exception as e:
        log(f"Last resort menu item search failed: {e}")

      if not retweet_option:
        log("Could not find retweet option in menu")
        return "failed"    # Click the retweet option
    await retweet_option.click()
    # Wait a moment for the retweet to complete
    log("Clicked retweet option, post has been retweeted")
    # Check for confirmation or success indicator if available
    await asyncio.sleep(2)
    try:
      confirmation = await page.wait_for_selector('div[role="alert"], div[data-testid="toast"]', timeout=4000)
      if confirmation:
        log("Found confirmation of successful retweet")
    except:
      # No confirmation found, but continue anyway
      pass

    return True
  except Exception as e:
    log(f"Error retweeting post: {e}")

    # Retry logic for failed attempts with increased retries
    if retry_count < max_retries:
      # Increasing wait times: 3s, 5s, 8s for retries 1, 2, 3
      wait_time = 3 + (retry_count * 2)
      log(
        f"Retrying retweet after error (attempt {retry_count + 2}/{max_retries + 1}) in {wait_time} seconds...")
      await asyncio.sleep(wait_time)
      return await retweet_post(page, retry_count + 1, max_retries)
    else:
      log(f"Failed to retweet after {max_retries + 1} attempts")
      return "failed"


def extract_status_signature(href):
  """Extract the status signature from a Twitter/X URL for duplicate detection.

  Args:
    href: The URL string to extract signature from

  Returns:
    A tuple (account_name, status_id) or None if not a valid status URL
  """
  if not href:
    return None

  # Handle both full URLs and relative paths
  if href.startswith('http'):
    # Extract path from full URL
    try:
      parsed = urlparse(href)
      path = parsed.path
    except:
      return None
  else:
    path = href

  # Match pattern: /account_name/status/status_id (with optional additional parts)
  match = re.match(r'/([^/]+)/status/(\d+)', path)
  if match:
    account_name = match.group(1)
    status_id = match.group(2)
    return (account_name, status_id)

  return None


def filter_duplicate_direct_links(captured_links):
  """Filter out duplicate direct links based on status signature.

  For links with the same account_name/status/status_id pattern, keep only the first occurrence.
  """
  seen_signatures = set()
  filtered_links = []
  removed_count = 0

  for link_item in captured_links:
    if link_item['type'] == 'direct_link':
      href = link_item.get('href')
      signature = extract_status_signature(href)

      if signature:
        if signature not in seen_signatures:
          seen_signatures.add(signature)
          filtered_links.append(link_item)
        else:
          removed_count += 1
          log(
            f"Removing duplicate link: {href} (signature: {signature[0]}/status/{signature[1]})")
      else:
        # Keep non-status links as they are
        filtered_links.append(link_item)
    else:
      # Keep embedded tweets and other types as they are
      filtered_links.append(link_item)

  if removed_count > 0:
    log(f"Filtered out {removed_count} duplicate direct links")
  return filtered_links


async def extract_embedded_signature(page, element):
  """Extract a unique signature from an embedded tweet element for duplicate detection.

  Args:
    page: The Playwright page object
    element: The embedded tweet element

  Returns:
    A string signature or None if extraction fails
  """
  try:
    # Try to extract unique identifiers from the element
    signature_parts = []

    # Get text content as a signature component
    text_content = await page.evaluate('(element) => element.textContent', element)
    if text_content:
      # Use first 100 characters and clean whitespace for signature
      clean_text = ' '.join(text_content.strip().split())[:100]
      signature_parts.append(clean_text)

    # Get any data attributes that might be unique
    element_html = await page.evaluate('(element) => element.outerHTML', element)

    # Look for tweet-specific patterns in the HTML
    import re

    # Extract any tweet IDs or account references from the HTML
    tweet_id_match = re.search(r'status/(\d+)', element_html)
    if tweet_id_match:
      signature_parts.append(f"status_{tweet_id_match.group(1)}")

    account_match = re.search(r'/([^/\s"]+)/status/', element_html)
    if account_match:
      signature_parts.append(f"account_{account_match.group(1)}")

    # If we have signature parts, join them
    if signature_parts:
      return '|'.join(signature_parts)

    # Fallback: use element position and some attributes
    bounding_box = await element.bounding_box()
    if bounding_box:
      signature_parts.append(
        f"pos_{int(bounding_box['x'])}_{int(bounding_box['y'])}")

    if signature_parts:
      return '|'.join(signature_parts)

    return None

  except Exception as e:
    log(f"Error extracting embedded signature: {e}")
    return None


def filter_duplicate_embedded_links(captured_links):
  """Filter out duplicate embedded links based on element signatures.

  For embedded tweets with similar signatures, keep only the first occurrence.
  """
  seen_signatures = set()
  filtered_links = []
  removed_count = 0

  for link_item in captured_links:
    if link_item['type'] == 'embedded':
      # We'll add this in the main function
      signature = link_item.get('signature')

      if signature:
        if signature not in seen_signatures:
          seen_signatures.add(signature)
          filtered_links.append(link_item)
        else:
          removed_count += 1
          log(
            f"Removing duplicate embedded tweet with signature: {signature[:50]}...")
      else:
        # Keep tweets without signatures
        filtered_links.append(link_item)
    else:
      # Keep direct links and other types as they are
      filtered_links.append(link_item)

  if removed_count > 0:
    log(f"Filtered out {removed_count} duplicate embedded links")
  return filtered_links


async def filter_duplicate_embedded_by_position(page, captured_links):
  """Filter out duplicate embedded links based on element position.

  This is a simpler approach that compares element positions to detect duplicates.
  """
  position_signatures = set()
  filtered_links = []
  removed_count = 0

  for link_item in captured_links:
    if link_item['type'] == 'embedded':
      try:
        element = link_item['element']
        bounding_box = await element.bounding_box()

        if bounding_box:
          # Create position signature with some tolerance for minor position differences
          x = round(bounding_box['x'] / 10) * 10  # Round to nearest 10 pixels
          y = round(bounding_box['y'] / 10) * 10
          width = round(bounding_box['width'] / 10) * 10
          height = round(bounding_box['height'] / 10) * 10

          position_sig = f"{x}_{y}_{width}_{height}"

          if position_sig not in position_signatures:
            position_signatures.add(position_sig)
            filtered_links.append(link_item)
          else:
            removed_count += 1
            log(
              f"Removing duplicate embedded tweet at position: {position_sig}")
        else:
          # Keep tweets without bounding box
          filtered_links.append(link_item)
      except Exception as e:
        log(f"Error checking embedded element position: {e}")
        # Keep the element if we can't check its position
        filtered_links.append(link_item)
    else:
      # Keep direct links and other types as they are
      filtered_links.append(link_item)

  if removed_count > 0:
    log(f"Filtered out {removed_count} duplicate embedded links by position")
  return filtered_links


def log_captured_links_summary(captured_links, chat_index):
  """Log all captured links in a user-friendly format before processing."""
  if not captured_links:
    log(f"\n=== No links found in Chat {chat_index + 1} ===")
    return

  log(f"\n=== Links Found in Chat {chat_index + 1} ===")
  log(f"Total links captured: {len(captured_links)}")

  # Separate by type
  direct_links = [
    item for item in captured_links if item['type'] == 'direct_link']
  embedded_tweets = [
    item for item in captured_links if item['type'] == 'embedded']

  log(f"Direct links: {len(direct_links)}")
  log(f"Embedded tweets: {len(embedded_tweets)}")

  # Log direct links with details
  if direct_links:
    log(f"\n--- Direct Links ({len(direct_links)}) ---")
    for i, link_item in enumerate(direct_links, 1):
      href = link_item.get('href', 'No URL')
      signature = extract_status_signature(href)
      if signature:
        log(f"{i}. {href} (Account: {signature[0]}, Status: {signature[1]})")
      else:
        log(f"{i}. {href} (Non-status link)")

  # Log embedded tweets
  if embedded_tweets:
    log(f"\n--- Embedded Tweets ({len(embedded_tweets)}) ---")
    for i, tweet_item in enumerate(embedded_tweets, 1):
      log(f"{i}. Embedded tweet element (requires click to get URL)")

  log(f"\n--- Starting to process all {len(captured_links)} links ---")


async def scroll_and_capture_links(page):
  """Scroll incrementally and capture links until 'Done' message is found or top of chat is reached."""
  log("Starting incremental scrolling to capture links...")

  captured_links = []
  done_message_found = False
  scroll_count = 0
  previous_scroll_top = None

  # Selectors for capturing elements
  embedded_selector = 'div[role="link"].css-175oi2r.r-adacv.r-1udh08x.r-1867qdf'
  link_selector = 'a[role="link"][href*="/status/"]'

  while not done_message_found:
    scroll_count += 1
    log(f"Performing scroll {scroll_count}...")

    # Get current scroll position before scrolling
    current_scroll_top = await page.evaluate("document.querySelector('[data-testid=\"DmActivityViewport\"]').scrollTop")

    # Check if we've reached the top of the chat (no more scrolling possible)
    if previous_scroll_top is not None and current_scroll_top == previous_scroll_top:
      log("Reached the top of the chat, no more content to scroll.")
      break

    # Scroll up within the specific viewport div
    await page.evaluate("document.querySelector('[data-testid=\"DmActivityViewport\"]').scrollBy(0, -window.innerHeight)")
    # Wait for new content to load    # Update previous scroll position
    await asyncio.sleep(2)
    # Capture links after every configured number of scrolls or if we've found the done message
    previous_scroll_top = current_scroll_top
    # Capture embedded tweets (divs with role="link" and specific classnames)
    if scroll_count % SCROLLS_COUNT_FOR_EACH_CAPTURE == 0:
      # Get existing elements to avoid redundant processing
      existing_embedded_elements = [item['element']
                                    for item in captured_links if item['type'] == 'embedded']
      existing_direct_hrefs = [
        item['href'] for item in captured_links if item['type'] == 'direct_link' and item['href']]

      embedded_elements = await page.query_selector_all(embedded_selector)
      log(
        f"Found {len(embedded_elements)} embedded tweet elements during scroll {scroll_count}.")

      new_embedded_count = 0
      for element in embedded_elements:
        if element not in existing_embedded_elements:
          # Extract signature for duplicate detection
          signature = await extract_embedded_signature(page, element)
          captured_links.append(
            {'href': None, 'type': 'embedded', 'element': element, 'signature': signature})
          new_embedded_count += 1

      # Capture direct Twitter/X links (a elements with role="link" and href containing "/status/")
      direct_link_elements = await page.query_selector_all(link_selector)
      log(f"Found {len(direct_link_elements)} direct Twitter link elements during scroll {scroll_count}.")

      new_direct_count = 0
      for link in direct_link_elements:
        href = await link.get_attribute('href')
        if href and href not in existing_direct_hrefs:
          captured_links.append(
            {'href': href, 'type': 'direct_link', 'element': link})
          new_direct_count += 1

      log(f"Captured {new_embedded_count} new embedded and {new_direct_count} new direct links during scroll {scroll_count}.")
    # Check for 'Done' message using the constant - look only within the chat viewport
    chat_viewport = await page.query_selector('[data-testid="DmActivityViewport"]')
    if chat_viewport:
      done_message = await chat_viewport.query_selector(f'div:has-text("{DONE_MESSAGE_TEXT}")')
      if done_message:
        log(f"'{DONE_MESSAGE_TEXT}' message found in chat, stopping scroll.")
        done_message_found = True
        break

    # Safety check to prevent infinite scrolling
    if scroll_count >= 50:
      log("Reached maximum scroll limit (50), stopping scroll.")
      break

  # Perform a final capture to ensure we get all links
  log("Performing final capture after scrolling completed...")

  # Get existing elements to avoid redundant processing
  existing_elements = [item['element']
                       for item in captured_links if item['type'] == 'embedded']
  existing_hrefs = [item['href']
                    for item in captured_links if item['type'] == 'direct_link' and item['href']]

  embedded_elements_final = await page.query_selector_all(embedded_selector)
  new_embedded_count = 0
  for element in embedded_elements_final:
    if element not in existing_elements:
      # Extract signature for duplicate detection (only for truly new elements)
      signature = await extract_embedded_signature(page, element)
      captured_links.append(
        {'href': None, 'type': 'embedded', 'element': element, 'signature': signature})
      new_embedded_count += 1

  links_final = await page.query_selector_all(link_selector)
  new_direct_count = 0
  for link in links_final:
    href = await link.get_attribute('href')
    if href and href not in existing_hrefs:
      captured_links.append(
        {'href': href, 'type': 'direct_link', 'element': link})
      new_direct_count += 1

  log(
    f"Final capture added {new_embedded_count} new embedded elements and {new_direct_count} new direct links.")

  # Filter out duplicate direct links based on status signature
  original_count = len(captured_links)
  captured_links = filter_duplicate_direct_links(captured_links)

  # Filter out duplicate embedded links based on element signatures
  captured_links = filter_duplicate_embedded_links(captured_links)

  # Alternative: Use position-based filtering for embedded tweets
  # captured_links = await filter_duplicate_embedded_by_position(page, captured_links)

  final_count = len(captured_links)

  log(
    f"Captured a total of {original_count} links, filtered to {final_count} unique links after {scroll_count} scrolls.")
  return captured_links


async def open_tweet_in_new_tab(context, page, post_item, tweet_index):
  """Open a tweet in a new tab by clicking on the tweet element at the specified index."""
  try:
    element_type = post_item['type']
    post_element = post_item['element']

    log(
      f"Processing Twitter post at index {tweet_index} (type: {element_type})...")
    url_page = None
    max_retries = 3  # Increased to 3 retries for better reliability

    # Store original URL to detect navigation
    original_url = page.url    # Handle direct links differently from embedded tweets
    log(f"Original URL before clicking: {original_url}")
    if element_type == 'direct_link':
      # Retry logic for direct links
      for retry_attempt in range(max_retries + 1):
        try:
          if retry_attempt > 0:
            log(
              f"Retrying direct link processing (attempt {retry_attempt + 1}/{max_retries + 1})...")
            # Increasing wait times: 3s, 5s, 8s for retries
            wait_time = 3 + (retry_attempt * 2)
            await asyncio.sleep(wait_time)

          href = post_item.get('href')
          if href:
            # Ensure it's a full URL
            if href.startswith('/'):
              tweet_url = f"https://x.com{href}"
            else:
              tweet_url = href

            log(f"Opening direct link: {tweet_url}")

            # Open in new tab
            url_page = await context.new_page()
            await url_page.goto(tweet_url, wait_until="domcontentloaded")
            await asyncio.sleep(2)

            # Try to retweet (this function already has its own retry logic)
            retweet_result = await retweet_post(url_page)

            if url_page:
              await url_page.close()
              url_page = None

            if retweet_result == "already_retweeted":
              log(f"Tweet already retweeted (index {tweet_index})")
              return "already_retweeted"
            elif retweet_result == True:
              log(f"Successfully retweeted post (index {tweet_index})")
              return "retweeted"
            elif retweet_result == "failed" and retry_attempt < max_retries:
              log(f"Retweet failed, will retry direct link processing...")
              continue
            else:
              log(f"Failed to retweet post (index {tweet_index})")
              return "failed"
          else:
            log(
              f"Could not get href attribute for direct link at index {tweet_index}")
            return "failed"

        except Exception as e:
          log(f"Error handling direct link (attempt {retry_attempt + 1}): {e}")
          if url_page:
            await url_page.close()
            url_page = None
          if retry_attempt >= max_retries:
            return "failed"
          continue    # Handle embedded tweets with enhanced retry logic
    for retry in range(max_retries + 1):  # Changed to max_retries + 1 for consistency
      try:
        if retry > 0:
          log(
            f"Retrying embedded tweet processing (attempt {retry + 1}/{max_retries + 1})...")
          # Reload page before retry with increasing wait times
          log("Reloading page before retry...")
          await page.goto(original_url)
          wait_time = 5 + (retry * 3)  # 5s, 8s, 11s for retries
          log(f"Waiting {wait_time} seconds after page reload...")
          await asyncio.sleep(wait_time)
        else:
          log(
            f"Attempt #{retry+1} to find and click embedded tweet elements...")

        # First, ensure we're on the messages page
        if not page.url.startswith("https://x.com/messages"):
          log("Navigating back to messages page...")
          await page.goto(original_url)
          await asyncio.sleep(3)

        # Click the specific div element with role="link" based on index
        clicked = await page.evaluate(f"""(targetIndex) => {{
          // Find div elements with role="link" and specific classnames for tweets
          const linkElements = document.querySelectorAll('div[role="link"].css-175oi2r.r-adacv.r-1udh08x.r-1867qdf');
          console.log(`Found ${{linkElements.length}} div[role="link"] elements with tweet classnames`);
          
          if (linkElements.length === 0) {{
            return false;
          }}
          
          // Use direct order (no reverse calculation)
          console.log(`Target index: ${{targetIndex}}, Using direct index: ${{targetIndex}}`);
          
          if (targetIndex >= 0 && targetIndex < linkElements.length) {{
            try {{
              const targetElement = linkElements[targetIndex];
              targetElement.scrollIntoView({{behavior: 'auto', block: 'center'}});
              console.log(`Clicking div[role="link"] element at direct index ${{targetIndex}}`);
              targetElement.click();
              return true;
            }} catch(e) {{
              console.error("Error clicking target element:", e);
            }}
          }}
          
          // Fallback: if index is out of range, try the first available element
          if (linkElements.length > 0) {{
            try {{
              console.log("Index out of range, clicking first available tweet div");
              linkElements[0].scrollIntoView({{behavior: 'auto', block: 'center'}});
              linkElements[0].click();
              return true;
            }} catch(e) {{
              console.error("Error clicking fallback element:", e);
            }}
          }}
          
          return false;
        }}""", tweet_index)

        if clicked:
          log("Clicked on a potential tweet element")
          await asyncio.sleep(3)  # Give it time to navigate

          # Check if we navigated to a tweet page
          current_url = page.url
          log(f"Current URL after clicking: {current_url}")

          if current_url != original_url and ('status' in current_url):
            log(f"Successfully navigated to tweet page: {current_url}")

            # Open in new tab
            url_page = await context.new_page()
            await url_page.goto(current_url, wait_until="domcontentloaded")
            await asyncio.sleep(2)            # Return to messages page
            await page.goto(original_url)
            await asyncio.sleep(2)

            # Try to retweet
            retweet_result = await retweet_post(url_page)

            if url_page:
              await url_page.close()

            if retweet_result == "already_retweeted":
              log(f"Tweet already retweeted (index {tweet_index})")
              return "already_retweeted"
            elif retweet_result == True:
              log(f"Successfully retweeted post (index {tweet_index})")
              return "retweeted"
            else:
              log(f"Failed to retweet post (index {tweet_index})")
              return "failed"
          else:
            log("Click didn't navigate to a tweet page")
            # Continue to next retry if available
            if retry < max_retries:
              continue

        # If no click worked or we didn't navigate to a status page, continue to next retry
        # The enhanced retry logic with page reload is already handled at the top of the loop

      except Exception as e:
        log(f"Error on attempt {retry+1}: {e}")
        if url_page:
          await url_page.close()
          url_page = None

        # Continue to next retry if available (page reload handled at top of loop)
        if retry >= max_retries:
          break

    log(
      f"Could not process embedded tweet {tweet_index} after {max_retries + 1} attempts")
    return "failed"
  except Exception as e:
    log(f"Failed to process Twitter post {tweet_index}: {e}")
    if url_page:
      await url_page.close()
    return "failed"


async def open_chat_by_index(page, chat_index):
  """Open a specific chat by its index."""
  try:
    log(f"Attempting to open chat at index {chat_index}...")

    # Find all chat elements
    chat_elements = await find_chat_elements(page)

    if chat_index >= len(chat_elements):
      log(
        f"Chat index {chat_index} out of range (only {len(chat_elements)} chats found)")
      return False

    chat_element = chat_elements[chat_index]

    # Extract message ID from the element for direct navigation
    chat_html = await page.evaluate("element => element.outerHTML", chat_element)

    # Look for message ID in the HTML
    message_id_match = re.search(r'/messages/(\d+)', chat_html)
    if message_id_match:
      message_id = message_id_match.group(1)
      # Navigate to the specific chat using the ID
      log(f"Found message ID: {message_id}")
      await page.goto(f"https://x.com/messages/{message_id}")
      log(f"Opened chat using extracted message ID: {message_id}")
      await asyncio.sleep(5)
    else:
      # Fallback to direct clicking if we couldn't find an ID
      try:
        # Try to find the main conversation element
        main_conversation = await chat_element.query_selector('[data-testid="conversation"]')
        if not main_conversation:
          main_conversation = chat_element

        await main_conversation.click()
        log("Opened chat by direct click")
        await asyncio.sleep(5)
      except Exception as e:
        log(f"Click failed: {e}")
        return False

    return True
  except Exception as e:
    log(f"Failed to open chat: {e}")
    return False


async def process_chat_tweets(context, page, chat_index, retry_count=0, max_retries=1):
  """Process all tweets in a single chat."""
  try:
    if retry_count > 0:
      log(
        f"\n--- Retrying Chat {chat_index + 1} (Attempt {retry_count + 1}) ---")
    else:
      log(f"\n--- Processing Chat {chat_index + 1} ---")

    # Open the chat
    chat_opened = await open_chat_by_index(page, chat_index)

    if not chat_opened:
      log(f"Failed to open chat {chat_index + 1}")

      # Retry logic for failed chat opening
      if retry_count < max_retries:
        log(
          f"Retrying chat {chat_index + 1} after failed opening (attempt {retry_count + 2}/{max_retries + 1})...")
        await asyncio.sleep(5)
        return await process_chat_tweets(context, page, chat_index, retry_count + 1, max_retries)
      else:
        log(
          f"Failed to open chat {chat_index + 1} after {max_retries + 1} attempts")
        return 0

    # Wait for chat to load with a reasonable delay
    # Use scroll_and_capture_links to find Twitter posts in the chat
    await asyncio.sleep(8)
    post_elements = await scroll_and_capture_links(page)
    log(f"Found {len(post_elements)} tweet(s) in chat {chat_index + 1}")

    if len(post_elements) == 0:
      log("No tweets found. Refreshing page to try again...")
      await page.reload()
      await asyncio.sleep(5)
      post_elements = await scroll_and_capture_links(page)
      log(
        f"After refresh: found {len(post_elements)} tweet(s) in chat {chat_index + 1}")

      # If still no tweets and this isn't a retry, try once more
      if len(post_elements) == 0 and retry_count < max_retries:
        log(f"Still no tweets found in chat {chat_index + 1}, retrying...")
        await asyncio.sleep(3)
        return await process_chat_tweets(context, page, chat_index, retry_count + 1, max_retries)

    # Log all captured links in a user-friendly format before processing
    # Process each Twitter post
    log_captured_links_summary(post_elements, chat_index)
    tweets_retweeted = 0
    tweets_already_retweeted = 0
    tweets_failed = 0

    for j in range(len(post_elements)):
      post_item = post_elements[j]
      if not isinstance(post_item, dict):
        log(f"Skipping invalid post item at index {j}: {post_item}")
        continue

      element_type = post_item.get('type', 'unknown')
      log(
        f"\n--- Processing Tweet {j + 1}/{len(post_elements)} ({element_type}) ---")

      result = await open_tweet_in_new_tab(context, page, post_item, j)

      if result == "retweeted":
        tweets_retweeted += 1
      elif result == "already_retweeted":
        tweets_already_retweeted += 1
      else:
        tweets_failed += 1

      await asyncio.sleep(2)

    # Display summary for this chat
    total_processed = tweets_retweeted + tweets_already_retweeted + tweets_failed
    log(f"\n=== Chat {chat_index + 1} Summary ===")
    log(f"Total tweets found: {len(post_elements)}")
    log(f"Successfully retweeted: {tweets_retweeted}")
    log(f"Already retweeted: {tweets_already_retweeted}")
    log(f"Failed to process: {tweets_failed}")

    # Automatically send "Done" message only if at least one tweet was successfully retweeted
    if tweets_retweeted > 0:
      log("Automatically sending 'Done' message (new retweets were made)...")
      done_sent = await send_done_message(page)
      if done_sent:
        log("'Done' message sent successfully")
      else:
        log("Failed to send 'Done' message automatically")
    else:
      log("No new retweets made, skipping 'Done' message")

    log(f"Finished processing chat {chat_index + 1}")
    return tweets_retweeted
  except Exception as e:
    log(f"Error processing chat {chat_index + 1}: {e}")

    # Retry logic for general processing errors
    if retry_count < max_retries:
      log(
        f"Retrying chat {chat_index + 1} after error (attempt {retry_count + 2}/{max_retries + 1})...")
      await asyncio.sleep(5)
      return await process_chat_tweets(context, page, chat_index, retry_count + 1, max_retries)
    else:
      log(
        f"Failed to process chat {chat_index + 1} after {max_retries + 1} attempts")
      return 0
      return 0


async def find_chat_elements(page):
  """Find chat conversation elements using multiple strategies."""
  chat_elements = []

  # First attempt - try to find individual conversations with the conversation data-testid
  try:
    await page.wait_for_selector('[data-testid="conversation"]', timeout=15000, state='visible')
    log("Found conversation elements by data-testid")
    chat_elements = await page.query_selector_all('[data-testid="conversation"]')
    log(f"Found {len(chat_elements)} chat conversations by data-testid")
  except Exception as e:
    log(f"First attempt failed: {e}")
    try:
      # Second attempt - try to find based on cellInnerDiv
      await page.wait_for_selector('div[data-testid="cellInnerDiv"]', timeout=15000, state='visible')
      log("Found cellInnerDiv elements")
      chat_elements = await page.query_selector_all('div[data-testid="cellInnerDiv"]')
      log(f"Found {len(chat_elements)} cellInnerDiv elements")
    except Exception as e2:
      log(f"No conversation elements found: {e2}")
      return []
  return chat_elements


async def send_done_message(page):
  """Automatically send the 'Done' message in the current chat."""
  try:
    log(f"Attempting to send '{DONE_MESSAGE_TEXT}' message...")

    # Wait for the message input area to be available
    await page.wait_for_selector('[data-testid="dmComposerTextInput"]', timeout=10000)

    # Find the message input field
    message_input = await page.query_selector('[data-testid="dmComposerTextInput"]')
    if not message_input:
      log("Could not find message input field")
      return False

    # Click on the input field to focus it
    await message_input.click()
    await asyncio.sleep(0.5)

    # Type the done message
    await message_input.fill(DONE_MESSAGE_TEXT)
    await asyncio.sleep(0.5)

    # Find and click the send button
    send_button = await page.query_selector('[data-testid="dmComposerSendButton"]')
    if not send_button:
      # Try alternative selector
      send_button = await page.query_selector('button[aria-label="Send message"]')

    if send_button:
      await send_button.click()
      log(f"Successfully sent '{DONE_MESSAGE_TEXT}' message")
      await asyncio.sleep(1)
      return True
    else:
      log("Could not find send button")
      return False

  except Exception as e:
    log(f"Error sending '{DONE_MESSAGE_TEXT}' message: {e}")
    return False


async def run_script():
  """Main function to run the Twitter automation script."""
  try:
    async with async_playwright() as p:
      # Launch browser with error handling and fullscreen mode
      browser = await p.chromium.launch(
          headless=False,
          args=['--start-maximized', '--disable-gpu', '--no-sandbox',
                '--window-size=1550,720', '--window-position=0,0']
      )

      # Create context with specific viewport settings
      context = await browser.new_context(
          viewport={"width": 1550, "height": 720},
          screen={"width": 1550, "height": 720}
      )

      # Initialize first page and maximize window
      default_page = await context.new_page()
      await default_page.evaluate("() => { window.moveTo(0,0); window.resizeTo(screen.width,screen.height); }")
      await default_page.close()

      # Load cookies
      try:
        cookies_file_path = os.path.join(os.path.dirname(
          os.path.abspath(__file__)), 'cookies.txt')
        cookies = parse_cookies_from_file(cookies_file_path)
        await context.add_cookies(cookies)
        log(f"Loaded {len(cookies)} cookies")
      except Exception as e:
        log(f"Error loading cookies: {e}")
        return

      # Create main page
      page = await context.new_page()

      # Main program loop - will restart after each session
      while True:
        # Ask for execution mode at the beginning of each session
        log("\nHow would you like to start?")
        log("1 - Single iteration")
        log("2 - Multiple iterations with time interval")
        initial_choice = get_int_input("Enter your choice (1-2): ", [1, 2])

        hours = 0
        if initial_choice == 2:
          # Get interval in hours for multiple iterations
          while hours < 1 or hours > 5:
            hours = get_int_input("Enter time interval in hours (1-5): ")
            if hours < 1 or hours > 5:
              log("Please enter a value between 1 and 5 hours.")
          log(
            f"\nStarting multiple iterations mode with {hours} hour interval.")
          log("Press Ctrl+C to pause/stop.")        # Session execution loop
        running_session = True
        while running_session:
          # Perform multiple iterations based on config
          for iteration_num in range(ITERATIONS_COUNT):
            try:
              if iteration_num > 0:
                log(
                  f"\n--- Starting iteration {iteration_num+1} of {ITERATIONS_COUNT} ---")
                # Small delay between iterations
                await asyncio.sleep(2)

              # Navigate to messages
              await page.goto('https://x.com/messages')
              log("X.com messages page opened")

              # Wait for page to load
              try:
                await page.wait_for_selector('[data-testid=\"conversation\"], div[role=\"tablist\"]',
                                             timeout=15000, state='visible')
              except Exception as e:
                log(f"Timed out waiting for conversations: {e}")
                await asyncio.sleep(5)

              # Find and process chats
              initial_chat_elements = await find_chat_elements(page)
              chat_count = len(initial_chat_elements)

              # Process chats if found
              if chat_count > 0:
                total_tweets_opened = 0
                for i in range(chat_count):
                  if i > 0:
                    await page.goto('https://x.com/messages')
                    await asyncio.sleep(5)
                  tweets_opened = await process_chat_tweets(context, page, i)
                  total_tweets_opened += tweets_opened
                log(
                  f"\nIteration {iteration_num+1}: {total_tweets_opened} tweets processed from {chat_count} chats")
              else:
                log(f"Iteration {iteration_num+1}: No chats found to process")

            except Exception as e:
              log(f"Error in iteration {iteration_num+1}: {e}")
              choice = get_int_input(
                "\nRetry this iteration? (1 for yes, 2 for skip to next): ", [1, 2])
              if choice == 1:
                # Retry current iteration
                iteration_num -= 1
                continue
              else:
                # Skip to next iteration
                continue

          log(
            f"\nCompleted all {ITERATIONS_COUNT} iterations for this session.")

          # For multiple iterations mode, continue with the interval or handle interruption
          if initial_choice == 2:
            try:
              log(f"\nWaiting {hours} hour(s) before next iteration...")
              log("(Press Ctrl+C to interrupt)")
              await asyncio.sleep(hours * 3600)
              log("\nStarting next iteration...")
              continue
            except KeyboardInterrupt:
              log("\nMultiple iterations mode interrupted.")
              log("\nWhat would you like to do?")
              log("1 - Resume multiple iterations")
              log("2 - Return to main menu")
              log("3 - Stop and close browser")

              sub_choice = get_int_input(
                "Enter your choice (1-3): ", [1, 2, 3])

              if sub_choice == 1:
                log("\nResuming multiple iterations...")
                continue
              elif sub_choice == 2:
                log("\nReturning to main menu...")
                running_session = False  # Exit the session loop to return to main menu
              else:
                log("Closing browser...")
                return

          # For single iteration mode or to handle completion
          # End the session and return to the initial menu
          log("\nSession completed!")
          log("\nWhat would you like to do next?")
          log("1 - Return to main menu")
          log("2 - Stop and close browser")

          choice = get_int_input("Enter your choice (1-2): ", [1, 2])

          if choice == 1:
            log("\nReturning to main menu...")
            running_session = False  # Exit the session loop to return to main menu
          else:
            log("Closing browser...")
            return

  except Exception as e:
    log(f"Critical error: {e}")

if __name__ == "__main__":
  asyncio.run(run_script())
