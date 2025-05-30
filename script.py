import asyncio
import os
import re
from datetime import datetime
from playwright.async_api import async_playwright


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





async def retweet_post(page):
  """Retweets a post that's open in the current page."""
  try:
    print("Attempting to retweet the post...")
    
    # Wait a moment to make sure the page is fully loaded
    await asyncio.sleep(3)    # Check if the tweet is already retweeted by looking for unretweet data-testid
    try:
      unretweet_exists = await page.get_by_test_id("unretweet").count() > 0
      
      if unretweet_exists:
        print("Found unretweet button - post is already retweeted, skipping...")
        return "already_retweeted"
        
      # Double check with text as backup
      already_retweeted = await page.get_by_text("Undo repost", exact=True).count() > 0
      if not already_retweeted:
        already_retweeted = await page.get_by_text("Undo Retweet", exact=True).count() > 0
      
      if already_retweeted:
        print("Tweet is already retweeted (confirmed by text), skipping...")
        return "already_retweeted"
    except Exception as e:
      print(f"Error checking if tweet is already retweeted: {e}")
    
    # Try multiple selectors to find the retweet button
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
        print(f"Trying to find retweet button with selector: {selector}")
        button = await page.wait_for_selector(selector, timeout=5000)
        if button:
          retweet_button = button
          print(f"Found retweet button with selector: {selector}")
          break
      except Exception as e:
        print(f"Selector {selector} failed: {e}")
    
    if not retweet_button:
      print("Could not find retweet button with any selector")
      
      # Last resort: try to find any buttons that might be the retweet button
      try:
        print("Trying to find any button that might be the retweet button...")
        all_buttons = await page.query_selector_all('button')
        
        for btn in all_buttons:
          try:
            aria_label = await btn.get_attribute('aria-label')
            if aria_label and ('retweet' in aria_label.lower() or 'repost' in aria_label.lower()):
              print(f"Found potential retweet button with aria-label: {aria_label}")
              retweet_button = btn
              break
          except:
            pass
      except Exception as e:
        print(f"Last resort button search failed: {e}")
      
      if not retweet_button:
        return False
    
    # Click the retweet button
    await retweet_button.click()
    print("Clicked retweet button")
    
    # Wait for the retweet menu to appear
    await asyncio.sleep(1.5);
    
    # Try multiple selectors for the retweet/repost option in the menu
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
        print(f"Trying to find retweet option with selector: {selector}")
        option = await page.wait_for_selector(selector, timeout=5000)
        if option:
          retweet_option = option
          print(f"Found retweet option with selector: {selector}")
          break
      except Exception as e:
        print(f"Selector {selector} failed: {e}")
    
    if not retweet_option:
      # Last resort: try to find any menu item that might be the retweet option
      try:
        print("Trying to find any menu item that might be the retweet option...")
        menu_items = await page.query_selector_all('div[role="menuitem"]')
        
        for item in menu_items:
          try:
            item_text = await page.evaluate('(element) => element.textContent', item)
            if item_text and ('retweet' in item_text.lower() or 'repost' in item_text.lower()):
              print(f"Found potential retweet option with text: {item_text}")
              retweet_option = item
              break
          except:
            pass
      except Exception as e:
        print(f"Last resort menu item search failed: {e}")
      
      if not retweet_option:
        print("Could not find retweet option in menu")
        return False
    
    # Click the retweet option
    await retweet_option.click()
    print("Clicked retweet option, post has been retweeted")
    
    # Wait a moment for the retweet to complete
    await asyncio.sleep(2)
    
    # Check for confirmation or success indicator if available
    try:
      confirmation = await page.wait_for_selector('div[role="alert"], div[data-testid="toast"]', timeout=4000)
      if confirmation:
        print("Found confirmation of successful retweet")
    except:
      # No confirmation found, but continue anyway
      pass
    
    return True
  except Exception as e:
    print(f"Error retweeting post: {e}")
    return False


async def find_tweets_in_chat(page):
  """Find received Twitter posts in the chat."""
  print("Looking for received Twitter posts in the chat...")

  # Wait for messages container or chat content to be visible
  try:
    await page.wait_for_selector('div[data-testid="DMDrawer"], div[data-testid="conversation"]', timeout=10000)
    print("Chat content container found")
    # Give the page a little extra time to render content
    await asyncio.sleep(3)
  except Exception as e:
    print(f"Wait for messages container timed out, continuing anyway: {e}")

  # Try multiple strategies to find tweet elements
  post_elements = []

  # Strategy 1: Look for received messages with quote tweets
  try:
    # Look for elements with tabindex="0" that are received messages (not buttons)
    elements = await page.query_selector_all('div[tabindex="0"][data-testid="messageEntry"] div[role="link"]')
    post_elements.extend(elements)
    print(
      f"Strategy 1 found {len(elements)} received posts")
  except Exception as e:
    print(f"Strategy 1 error: {e}")

  # Strategy 2: Look for composite messages in received messages
  if not post_elements:
    try:
      elements = await page.query_selector_all('div[tabindex="0"][data-testid="messageEntry"] div[data-testid="DMCompositeMessage"] div[role="link"]')
      post_elements.extend(elements)
      print(
        f"Strategy 2 found {len(elements)} received composite messages")
    except Exception as e:
      print(f"Strategy 2 error: {e}")

  # Strategy 3: Look for links within received messages
  if not post_elements:
    try:
      elements = await page.query_selector_all('div[tabindex="0"][data-testid="messageEntry"] .r-adacv')
      post_elements.extend(elements)
      print(
        f"Strategy 3 found {len(elements)} posts in received messages")
    except Exception as e:
      print(f"Strategy 3 error: {e}")

  # Strategy 4: Look specifically in received message cells
  if not post_elements:
    try:
      elements = await page.query_selector_all('div[tabindex="0"][data-testid="messageEntry"] div[data-testid="cellInnerDiv"]')
      post_elements.extend(elements)
      print(f"Strategy 4 found {len(elements)} cell elements in received messages")
    except Exception as e:
      print(f"Strategy 4 error: {e}")

  # Strategy 5: Look for links in received messages
  if not post_elements:
    try:
      # Only look within divs that have tabindex="0"
      elements = await page.query_selector_all('div[tabindex="0"][data-testid="messageEntry"] div[role="link"]')
      post_elements.extend(elements)
      print(f"Strategy 5 found {len(elements)} links in received messages")
    except Exception as e:
      print(f"Strategy 5 error: {e}")

  # Strategy 6: Look for tweet text elements in received messages
  try:
    tweet_text_elements = await page.query_selector_all('div[tabindex="0"][data-testid="messageEntry"] span[data-testid="tweetText"]')
    print(f"Found {len(tweet_text_elements)} tweet text elements in received messages")

    # If we found tweet text elements but no post elements, try to get the parent posts
    if not post_elements and tweet_text_elements:
      for tweet_text in tweet_text_elements:
        try:
          # Try to find the parent post element within the received message
          parent = await page.evaluate("""
                    (element) => {
                        // Try to find a parent with role="link"
                        let parent = element;
                        for (let i = 0; i < 5; i++) {  // Look up to 5 levels up
                            if (!parent) break;
                            parent = parent.parentElement;
                            if (parent && (parent.getAttribute('role') === 'link' || 
                                          parent.getAttribute('data-testid') === 'cellInnerDiv')) {
                                return parent;
                            }
                        }
                        return null;
                    }
                    """, tweet_text)

          if parent:
            post_elements.append(parent)
        except Exception as e:
          print(f"Error finding parent of tweet text: {e}")
  except Exception as e:
    print(f"Strategy 6 error: {e}")

  print(f"Found {len(post_elements)} total received Twitter posts in the chat")
  return post_elements


async def open_tweet_in_new_tab(context, page, post_element, index):
  """Try multiple methods to open a tweet in a new tab."""
  try:
    print(f"Processing Twitter post {index}...")

    # First try to extract any URLs from the post's text
    post_html = await page.evaluate('(element) => element.outerHTML', post_element)
    post_urls = []

    if post_html:
      # Extract URLs using regex - ONLY look for Twitter status URLs
      url_matches = re.findall(
        r'https?://(?:www\.)?(?:twitter\.com|x\.com)/[a-zA-Z0-9_]+/status/\d+', post_html)
      post_urls.extend(url_matches)

    # Method 1: If we found valid status URLs, try them one by one
    if post_urls:
      # Open each extracted valid status URL in a new tab
      for url in post_urls:
        url_page = None
        try:
          # Clean up the URL - remove any trailing quotes, brackets, or other characters
          clean_url = re.sub(r"['\"\)\]>,]+$", '', url)
          print(f"Opening valid Twitter status URL from post {index}: {clean_url}")
          url_page = await context.new_page()
          await url_page.goto(clean_url)
          await asyncio.sleep(2) # Wait for page to load
          
          # Try to retweet the post
          retweet_result = await retweet_post(url_page)
          
          if retweet_result == "already_retweeted":
            print(f"Tweet already retweeted: {clean_url}")
            await url_page.close()
            return True  # Stop processing this post entirely
          elif retweet_result:
            print(f"Successfully retweeted post from URL: {clean_url}")
            await url_page.close()
            return True  # Stop processing this post after successful retweet
          else:
            print(f"Failed to retweet post from URL: {clean_url}")
            await url_page.close()
            # Continue to try other URLs if available
          
          await asyncio.sleep(1)  # Brief pause between attempts
        except Exception as e:
          print(f"Error opening valid status URL {clean_url}: {e}")
          if url_page:
            await url_page.close()

    print(f"No valid status URL found in post {index} directly, trying alternative methods...")

    # Method 2: Try to extract href attributes from any links inside
    try:
      href_values = await page.evaluate("""
        (element) => {
          const links = element.querySelectorAll('a[href]');
          const hrefs = [];
          for (let i = 0; i < links.length; i++) {
            hrefs.push(links[i].getAttribute('href'));
          }
          return hrefs;
        }
      """, post_element)

      if href_values and len(href_values) > 0:
        for href in href_values:
          url_page = None
          if href and href.strip():
            print(f"Found href: {href}")
            full_url = href
            if href.startswith('/'):
              full_url = 'https://x.com' + href
            elif not href.startswith('http'):
              full_url = 'https://x.com/' + href

            if re.match(r'https?://(?:www\.)?(?:twitter\.com|x\.com)/[a-zA-Z0-9_]+/status/\d+$', full_url):
              try:
                print(f"Opening valid href in new tab: {full_url}")
                url_page = await context.new_page()
                await url_page.goto(full_url)
                await asyncio.sleep(2)
                
                retweet_result = await retweet_post(url_page)
                
                if retweet_result == "already_retweeted":
                  print(f"Tweet already retweeted: {full_url}")
                  await url_page.close()
                  return True  # Stop processing this post entirely
                elif retweet_result:
                  print(f"Successfully retweeted post from URL: {full_url}")
                  await url_page.close()
                  return True  # Stop processing after successful retweet
                else:
                  print(f"Failed to retweet post from URL: {full_url}")
                  await url_page.close()
                  # Continue to next method on failure
              except Exception as e:
                print(f"Error opening valid href {full_url}: {e}")
                if url_page:
                  await url_page.close()
            else:
              print(f"Skipping non-status URL found in href: {full_url}")
    except Exception as e:
      print(f"Error extracting href values: {e}")

    # Method 3: Try constructing URL from post content
    try:
      if post_html:
        status_id_match = re.search(r'status[/=](\d+)', post_html)
        if status_id_match:
          status_id = status_id_match.group(1)
          username_match = re.search(r'@([a-zA-Z0-9_]+)', post_html)
          username = username_match.group(1) if username_match else 'twitter'

          constructed_url = f'https://x.com/{username}/status/{status_id}'
          print(f"Constructed URL from post: {constructed_url}")

          url_page = await context.new_page()
          await url_page.goto(constructed_url)
          await asyncio.sleep(2)
          
          retweet_result = await retweet_post(url_page)
          
          if retweet_result == "already_retweeted":
            print(f"Tweet already retweeted: {constructed_url}")
            await url_page.close()
            return True  # Stop processing this post entirely
          elif retweet_result:
            print(f"Successfully retweeted post from URL: {constructed_url}")
            await url_page.close()
            return True  # Stop processing after successful retweet
          else:
            print(f"Failed to retweet post from URL: {constructed_url}")
            await url_page.close()
            return False  # All methods tried and failed
    except Exception as e:
      print(f"Error constructing URL from post: {e}")
      if url_page:
        await url_page.close()

    print("Failed to open a valid status URL for this post")
    return False
  except Exception as e:
    print(f"Failed to process Twitter post {index}: {e}")
    return False


async def open_chat_by_index(page, chat_index):
  """Open a specific chat by its index."""
  try:
    print(f"Attempting to open chat at index {chat_index}...")

    # Find all chat elements
    chat_elements = await find_chat_elements(page)

    if chat_index >= len(chat_elements):
      print(
        f"Chat index {chat_index} out of range (only {len(chat_elements)} chats found)")
      return False

    chat_element = chat_elements[chat_index]

    # Extract message ID from the element for direct navigation
    chat_html = await page.evaluate("element => element.outerHTML", chat_element)

    # Look for message ID in the HTML
    message_id_match = re.search(r'/messages/(\d+)', chat_html)
    if message_id_match:
      message_id = message_id_match.group(1)
      print(f"Found message ID: {message_id}")

      # Navigate to the specific chat using the ID
      await page.goto(f"https://x.com/messages/{message_id}")
      print(f"Opened chat using extracted message ID: {message_id}")
      await asyncio.sleep(2)
      return True

    # Fallback to direct clicking if we couldn't find an ID
    try:
      # Try to find the main conversation element
      main_conversation = await chat_element.query_selector('[data-testid="conversation"]')
      if not main_conversation:
        main_conversation = chat_element

      await main_conversation.click()
      print("Opened chat by direct click")
      await asyncio.sleep(2)
      return True
    except Exception as e:
      print(f"Click failed: {e}")
      return False
  except Exception as e:
    print(f"Failed to open chat: {e}")
    return False


async def process_chat_tweets(context, page, chat_index):
  """Process all tweets in a single chat."""
  try:
    print(f"\n--- Processing Chat {chat_index + 1} ---")

    # Open the chat
    chat_opened = await open_chat_by_index(page, chat_index)

    if not chat_opened:
      print(f"Failed to open chat {chat_index + 1}")
      return 0

    # Wait for chat to load
    await asyncio.sleep(5)

    # Find Twitter posts in the chat
    post_elements = await find_tweets_in_chat(page)
    print(f"Found {len(post_elements)} tweet(s) in chat {chat_index + 1}")

    # Process each Twitter post
    tweets_opened = 0
    tweets_retweeted = 0
    for j, post_element in enumerate(post_elements):
      success = await open_tweet_in_new_tab(context, page, post_element, j + 1)
      if success:
        tweets_opened += 1
        # Note: We don't have direct feedback on whether the retweet was successful
        # But we're tracking it in the open_tweet_in_new_tab function with console output
      await asyncio.sleep(2)  # Delay between processing posts

    print(
      f"Finished processing chat {chat_index + 1} - Opened {tweets_opened} tweet(s)")
    return tweets_opened
  except Exception as e:
    print(f"Error processing chat {chat_index + 1}: {e}")
    return 0


async def find_chat_elements(page):
  """Find chat conversation elements using multiple strategies."""
  chat_elements = []

  # First attempt - try to find individual conversations with the conversation data-testid
  try:
    await page.wait_for_selector('[data-testid="conversation"]', timeout=15000, state='visible')
    print("Found conversation elements by data-testid")
    chat_elements = await page.query_selector_all('[data-testid="conversation"]')
    print(f"Found {len(chat_elements)} chat conversations by data-testid")
  except Exception as e:
    print(f"First attempt failed: {e}")
    try:
      # Second attempt - try to find based on cellInnerDiv
      await page.wait_for_selector('div[data-testid="cellInnerDiv"]', timeout=15000, state='visible')
      print("Found cellInnerDiv elements")
      chat_elements = await page.query_selector_all('div[data-testid="cellInnerDiv"]')
      print(f"Found {len(chat_elements)} cellInnerDiv elements")
    except Exception as e2:
      print(f"Second attempt failed: {e2}")
      # Third attempt - try a more general approach
      print("Trying a more general approach...")
      await asyncio.sleep(5)
      await page.screenshot(path="messages_page.png")
      print("Took screenshot of the page for debugging")
      chat_elements = await page.query_selector_all('div[role="none"][data-testid="conversation"], div[tabindex="0"][data-testid="conversation"]')
      print(
        f"Found {len(chat_elements)} conversation elements with general selector")

      # Fourth attempt - look for anything clickable in the chat list
      if not chat_elements:
        chat_elements = await page.query_selector_all('div[role="tablist"] > div')
        print(f"Found {len(chat_elements)} general div elements in tablist")

  return chat_elements


async def main():
  """Main function to run the Twitter automation script."""
  try:
    # Launch the browser
    async with async_playwright() as p:
      try:
        # Launch browser with error handling and fullscreen mode
        browser = await p.chromium.launch(
            headless=False,
            args=[                '--start-maximized',
                '--disable-gpu',
                '--no-sandbox',
                f'--window-size=1550,720',
                '--window-position=0,0'
            ]
        )
        
        # Create context with specific viewport settings
        context = await browser.new_context(
            viewport={"width": 1550, "height": 720},
            screen={"width": 1550, "height": 720}
        )
        
        # Set the window state to maximized explicitly
        default_page = await context.new_page()
        await default_page.evaluate("() => { window.moveTo(0,0); window.resizeTo(screen.width,screen.height); }")
        await default_page.close()

        # Load cookies from file
        try:
          # Get the path to the cookies.txt file
          cookies_file_path = os.path.join(os.path.dirname(
              os.path.abspath(__file__)), 'cookies.txt')

          # Parse all cookies from the file
          cookies = parse_cookies_from_file(cookies_file_path)
          print(f"Loaded {len(cookies)} cookies from the file")

          # Add cookies to the context
          await context.add_cookies(cookies)
          print("Cookies added to the browser context")
        except Exception as e:
          print(f"Error loading or applying cookies: {e}")
          return

        # Create a new page and navigate to messages
        page = await context.new_page()
        try:
          await page.goto('https://x.com/messages')
          print("X.com messages page opened with cookies")

          # Wait for page to load with more reliable approach
          try:
            # Wait for key elements indicating the page is loaded
            await page.wait_for_selector('[data-testid="conversation"], div[role="tablist"]',
                                         timeout=15000, state='visible')
            print("Messages page loaded successfully")
          except Exception as e:
            print(f"Timed out waiting for conversation elements: {e}")
            print("Will continue anyway")
            # Take extra time to load if needed
            await asyncio.sleep(5)

          # Take a screenshot for debugging
          await page.screenshot(path="messages_page_loaded.png")
          print("Looking for chat conversations...")

          # Find chat elements to determine how many chats there are
          initial_chat_elements = await find_chat_elements(page)
          chat_count = len(initial_chat_elements)

          if chat_count == 0:
            print("Could not find any chat elements. Trying direct URL approach...")
            try:
              # Get first DM by direct URL
              await page.goto('https://x.com/messages/all')
              print("Opened direct messages list page")
              await asyncio.sleep(5)
              await page.screenshot(path="dm_list_page.png")
              # Try to find chats in this new page
              initial_chat_elements = await find_chat_elements(page)
              chat_count = len(initial_chat_elements)
            except Exception as e:
              print(f"Direct messages list approach failed: {e}")

          if chat_count > 0:
            print(f"Found {chat_count} chats to process")
            total_tweets_opened = 0

            # Process each chat in sequence by its index
            for i in range(chat_count):
              # Go to messages page before each chat
              if i > 0:  # Not needed for the first chat
                await page.goto('https://x.com/messages')
                print("Returned to messages page")
                await asyncio.sleep(3)  # Give page time to load

              # Process the chat at the current index
              tweets_opened = await process_chat_tweets(context, page, i)
              total_tweets_opened += tweets_opened

            print(
              f"\nProcessing completed: Opened {total_tweets_opened} tweets from {chat_count} chats")
            print("Each opened tweet was attempted to be retweeted. Check the console logs for details on which tweets were successfully retweeted.")
          else:
            print("No chat elements found after all attempts")

          print("Chat and tweet processing completed. Press Ctrl+C to close the browser.")

          # Keep the script running
          try:
            # This will keep the script running until interrupted
            # Keep open for 1 hour (you can adjust this)
            await asyncio.sleep(3600)
          except KeyboardInterrupt:
            print("Closing browser...")

        except Exception as e:
          print(f"Error in page navigation or processing: {e}")
      except Exception as e:
        print(f"Error creating browser context: {e}")
  except Exception as e:
    print(f"Critical error in main function: {e}")


if __name__ == "__main__":
  asyncio.run(main())













# Reposting problem solved