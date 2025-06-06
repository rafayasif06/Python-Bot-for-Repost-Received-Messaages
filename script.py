import asyncio
import os
import re
from datetime import datetime
from playwright.async_api import async_playwright


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


async def retweet_post(page):
  """Retweets a post that's open in the current page."""
  try:
    print("Attempting to retweet the post...")

    # Wait a moment to make sure the page is fully loaded
    # Check if the tweet is already retweeted by looking for unretweet data-testid
    await asyncio.sleep(3)
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
              print(
                f"Found potential retweet button with aria-label: {aria_label}")
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
    await asyncio.sleep(1.5)

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
  """Find received Twitter posts in the chat that appear after the last 'Done' message."""
  print("Looking for received Twitter posts in the chat...")

  # Wait for messages container or chat content to be visible
  try:
    await page.wait_for_selector('div[data-testid="DMDrawer"], div[data-testid="conversation"]', timeout=10000)
    print("Chat content container found")
    # Give the page a little extra time to render content
    await asyncio.sleep(3)

    # First find the last "Done" message
    last_done_element, done_count = await find_done_messages(page)
    print(f"\nFound {done_count} 'Done' message(s) in this chat")
  except Exception as e:
    print(f"Wait for messages container timed out, continuing anyway: {e}")

  post_elements = []

  # Helper function to check if an element comes after the last Done message
  async def is_after_last_done(element):
    if not last_done_element:
      return True  # If no Done message found, include all tweets

    try:
      # Get the bounding boxes of both elements
      last_done_box = await page.evaluate("""
        (element) => {
          const rect = element.getBoundingClientRect();
          return {top: rect.top, bottom: rect.bottom};
        }
      """, last_done_element)

      element_box = await page.evaluate("""
        (element) => {
          const rect = element.getBoundingClientRect();
          return {top: rect.top, bottom: rect.bottom};
        }
      """, element)

      # Compare vertical positions - if element is below the Done message, it appears later
      return element_box['top'] > last_done_box['bottom']
    except Exception as e:
      print(f"Error comparing element positions: {e}")
      return True  # Include tweet if we can't determine position

  try:
    # Target divs with role="link" and specific classnames as mentioned
    # These are the tweet/post elements shared in chats
    selector = 'div[role="link"].css-175oi2r.r-adacv.r-1udh08x.r-1867qdf'
    all_link_elements = await page.query_selector_all(selector)
    print(
      f"Found {len(all_link_elements)} potential tweet links with specific classnames")

    # If none found with the specific class combination, try just role="link" as fallback
    if len(all_link_elements) == 0:
      all_link_elements = await page.query_selector_all('div[tabindex="0"][data-testid="messageEntry"] div[role="link"]')
      print(
        f"Found {len(all_link_elements)} potential tweet links with role=link")

    # Filter to only include links that appear after the last "Done" message
    for element in all_link_elements:
      if await is_after_last_done(element):
        # Verify it has the expected class names
        has_classes = await page.evaluate("""
          (element) => {
            const classes = element.className;
            return classes && classes.includes('css-175oi2r') && 
                   classes.includes('r-adacv') && 
                   classes.includes('r-1udh08x') && 
                   classes.includes('r-1867qdf');
          }
        """, element)

        if has_classes:
          post_elements.append(element)

    # As a backup, if we still found nothing, look for any role="link" elements
    if len(post_elements) == 0:
      print("No tweets with specific classnames found, using fallback method")
      all_links = await page.query_selector_all('div[role="link"]')
      for link in all_links:
        if await is_after_last_done(link):
          post_elements.append(link)
  except Exception as e:
    print(f"Error finding tweet links: {e}")

  print(f"Found {len(post_elements)} total received Twitter posts in the chat")
  return post_elements


async def open_tweet_in_new_tab(context, page, post_element, tweet_index):
  """Open a tweet in a new tab by clicking on the tweet element at the specified index."""
  try:
    print(f"Processing Twitter post at index {tweet_index}...")
    url_page = None
    max_retries = 3  # Increased retries for better reliability

    # Store original URL to detect navigation
    original_url = page.url
    print(f"Original URL before clicking: {original_url}")

    # Attempt to click all tweet-like elements directly using JavaScript
    # Instead of trying to use the passed element (which may get detached)
    for retry in range(max_retries):
      try:
        print(f"Attempt #{retry+1} to find and click tweet elements...")

        # First, ensure we're on the messages page
        if not page.url.startswith("https://x.com/messages"):
          print("Navigating back to messages page...")
          await page.goto(original_url)
          # Click the specific div element with role="link" based on index
          # Target specific tweet divs with role="link" and required classnames
          await asyncio.sleep(3)
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
          print("Clicked on a potential tweet element")
          await asyncio.sleep(3)  # Give it time to navigate

          # Check if we navigated to a tweet page
          current_url = page.url
          print(f"Current URL after clicking: {current_url}")

          if current_url != original_url and ('status' in current_url):
            print(f"Successfully navigated to tweet page: {current_url}")

            # Open in new tab
            url_page = await context.new_page()
            await url_page.goto(current_url, wait_until="domcontentloaded")
            await asyncio.sleep(2)

            # Return to messages page
            await page.goto(original_url)
            await asyncio.sleep(2)

            # Try to retweet
            retweet_result = await retweet_post(url_page)

            if retweet_result == "already_retweeted":
              print(f"Tweet already retweeted (index {tweet_index})")
            elif retweet_result:
              print(f"Successfully retweeted post (index {tweet_index})")
            else:
              print(f"Failed to retweet post (index {tweet_index})")

            if url_page:
              await url_page.close()
            return True
          else:
            print("Click didn't navigate to a tweet page")

        # If no click worked or we didn't navigate to a status page, try a different approach on next retry
        if retry < max_retries - 1:
          print(f"Retry {retry+1} failed, reloading page for next attempt...")
          await page.goto(original_url)  # Go back to original page
          await asyncio.sleep(5)  # Longer wait after reload

      except Exception as e:
        print(f"Error on attempt {retry+1}: {e}")
        if url_page:
          await url_page.close()
          url_page = None

        # On error, reload the page before next retry
        if retry < max_retries - 1:
          print(f"Error during attempt {retry+1}, reloading page...")
          try:
            await page.goto(original_url)
            await asyncio.sleep(5)
          except Exception:
            pass

    print(
      f"Could not process tweet {tweet_index} after {max_retries} attempts")
    return False

  except Exception as e:
    print(f"Failed to process Twitter post {tweet_index}: {e}")
    if url_page:
      await url_page.close()
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

    # Wait for chat to load with a reasonable delay
    await asyncio.sleep(5)    # Find Twitter posts in the chat
    post_elements = await find_tweets_in_chat(page)
    print(f"Found {len(post_elements)} tweet(s) in chat {chat_index + 1}")

    if len(post_elements) == 0:
      print("No tweets found. Refreshing page to try again...")
      await page.reload()
      await asyncio.sleep(5)
      post_elements = await find_tweets_in_chat(page)
      print(
        f"After refresh: found {len(post_elements)} tweet(s) in chat {chat_index + 1}")

    # Process each Twitter post
    tweets_opened = 0

    for j in range(len(post_elements)):
      post_element = post_elements[j]
      print(f"\n--- Processing Tweet {j + 1}/{len(post_elements)} ---")
      success = await open_tweet_in_new_tab(context, page, post_element, j)
      if success:
        tweets_opened += 1
      await asyncio.sleep(2)

    if tweets_opened > 0:
      print("Finished processing tweets - you can now send 'Done' message manually")
    else:
      print("No tweets were successfully processed")

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
      print(f"No conversation elements found: {e2}")
      return []
  return chat_elements


async def find_done_messages(page):
  """Find all 'Done' messages in the current chat and return the last one."""
  try:
    print("Looking for 'Done' messages in chat...")

    # Try to find all spans with the exact text "Done"
    done_messages = await page.query_selector_all('span.css-1jxf684.r-bcqeeo.r-1ttztb7.r-qvutc0.r-poiln3')

    done_count = 0
    # Verify each element has text that matches "done" (case-insensitive) and get the last one
    last_done_element = None
    for msg in done_messages:
      try:
        text = await page.evaluate('(element) => element.textContent', msg)
        if text.strip().lower() == "done":
          done_count += 1
          last_done_element = msg
      except Exception as e:
        print(f"Error checking message text: {e}")
        continue

    print(f"Found {done_count} 'Done' message(s) in chat")
    return last_done_element, done_count

  except Exception as e:
    print(f"Error finding 'Done' messages: {e}")
    return None, 0


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
        print(f"Loaded {len(cookies)} cookies")
      except Exception as e:
        print(f"Error loading cookies: {e}")
        return

      # Create main page
      page = await context.new_page()

      # Main program loop - will restart after each session
      while True:
        # Ask for execution mode at the beginning of each session
        print("\nHow would you like to start?")
        print("1 - Single iteration")
        print("2 - Multiple iterations with time interval")
        initial_choice = get_int_input("Enter your choice (1-2): ", [1, 2])

        hours = 0
        if initial_choice == 2:
          # Get interval in hours for multiple iterations
          while hours < 1 or hours > 5:
            hours = get_int_input("Enter time interval in hours (1-5): ")
            if hours < 1 or hours > 5:
              print("Please enter a value between 1 and 5 hours.")
          print(
            f"\nStarting multiple iterations mode with {hours} hour interval.")
          print("Press Ctrl+C to pause/stop.")

        # Session execution loop
        running_session = True
        while running_session:
          try:
            # Navigate to messages
            await page.goto('https://x.com/messages')
            print("X.com messages page opened")

            # Wait for page to load
            try:
              await page.wait_for_selector('[data-testid="conversation"], div[role="tablist"]',
                                           timeout=15000, state='visible')
            except Exception as e:
              print(f"Timed out waiting for conversations: {e}")
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
                  await asyncio.sleep(3)
                tweets_opened = await process_chat_tweets(context, page, i)
                total_tweets_opened += tweets_opened
              print(
                f"\nProcessing completed: {total_tweets_opened} tweets processed from {chat_count} chats")
            else:
              print("No chats found to process")

            # For multiple iterations mode, continue with the interval or handle interruption
            if initial_choice == 2:
              try:
                print(f"\nWaiting {hours} hour(s) before next iteration...")
                print("(Press Ctrl+C to interrupt)")
                await asyncio.sleep(hours * 3600)
                print("\nStarting next iteration...")
                continue
              except KeyboardInterrupt:
                print("\nMultiple iterations mode interrupted.")
                print("\nWhat would you like to do?")
                print("1 - Resume multiple iterations")
                print("2 - Return to main menu")
                print("3 - Stop and close browser")

                sub_choice = get_int_input(
                  "Enter your choice (1-3): ", [1, 2, 3])

                if sub_choice == 1:
                  print("\nResuming multiple iterations...")
                  continue
                elif sub_choice == 2:
                  print("\nReturning to main menu...")
                  running_session = False  # Exit the session loop to return to main menu
                else:
                  print("Closing browser...")
                  return

            # For single iteration mode or to handle completion
            # End the session and return to the initial menu
            print("\nSession completed!")
            print("\nWhat would you like to do next?")
            print("1 - Return to main menu")
            print("2 - Stop and close browser")

            choice = get_int_input("Enter your choice (1-2): ", [1, 2])

            if choice == 1:
              print("\nReturning to main menu...")
              running_session = False  # Exit the session loop to return to main menu
            else:
              print("Closing browser...")
              return

          except Exception as e:
            print(f"Error in iteration: {e}")
            choice = get_int_input("\nRetry? (1 for yes, 2 for no): ", [1, 2])
            if choice == 2:
              return

  except Exception as e:
    print(f"Critical error: {e}")

if __name__ == "__main__":
  asyncio.run(run_script())
