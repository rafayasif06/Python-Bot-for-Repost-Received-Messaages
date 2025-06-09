import asyncio
import os
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


async def undo_retweets(page):
  """Undo all retweets on the profile page."""
  try:
    print("Looking for undo retweet buttons...")

    # Wait for the page to load
    await page.wait_for_selector('div[data-testid="primaryColumn"]', timeout=10000)

    total_undo_count = 0

    while True:
      # Debug: Log the page content to verify structure
      page_content = await page.content()
      with open("logs/debug_page_content.html", "w", encoding="utf-8") as f:
        f.write(page_content)
      print("Page content saved to logs/debug_page_content.html for debugging.")

      # Find all undo retweet buttons
      undo_buttons = await page.query_selector_all('button[data-testid="unretweet"]')
      print(f"Found {len(undo_buttons)} undo retweet buttons")

      if not undo_buttons:
        print("No more undo retweet buttons found.")
        break      # Click all undo buttons in parallel
      tasks = []
      for index, button in enumerate(undo_buttons):
        async def click_undo_button(button, index):
          try:
            print(f"Clicking undo retweet button {index + 1}...")
            await button.click()
            await asyncio.sleep(1)  # Wait for the modal to appear

            # Confirm undo repost in the modal
            confirm_button = await page.query_selector('div[data-testid="unretweetConfirm"]')
            if confirm_button:
              print("Clicking confirm undo repost button...")
              await confirm_button.click()
              await asyncio.sleep(1)  # Wait for the action to complete
              return 1
            else:
              print(
                f"No confirm button found for undo retweet button {index + 1}")
              return 0
          except Exception as e:
            print(f"Failed to click undo retweet button {index + 1}: {e}")
            return 0

        tasks.append(click_undo_button(button, index))

      results = await asyncio.gather(*tasks)
      # Filter out None values and sum the results
      valid_results = [result for result in results if result is not None]
      total_undo_count += sum(valid_results)

      # Scroll down to load more tweets
      await page.evaluate("window.scrollBy(0, window.innerHeight)")
      await asyncio.sleep(2)  # Wait for new content to load

    print(f"Finished undoing retweets. Total undo count: {total_undo_count}")
  except Exception as e:
    print(f"Error while undoing retweets: {e}")


async def run_script():
  """Main function to run the undo retweets script."""
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

      # Navigate to the profile page
      await page.goto('https://x.com/asif_abulkalam')
      print("Navigated to profile page.")

      # Undo all retweets
      await undo_retweets(page)

      # Close browser
      await browser.close()

  except Exception as e:
    print(f"Critical error: {e}")

if __name__ == "__main__":
  asyncio.run(run_script())
