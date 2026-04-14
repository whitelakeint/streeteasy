/**
 * Content script - runs on StreetEasy pages.
 * Receives commands from background.js, interacts with the DOM.
 */

// Listen for commands from background service worker
chrome.runtime.onMessage.addListener((msg, sender, sendResponse) => {
  (async () => {
    try {
      switch (msg.type) {
        case "check_captcha":
          sendResponse(await handleCheckCaptcha());
          break;
        case "solve_captcha":
          sendResponse(await handleSolveCaptcha());
          break;
        case "search_and_navigate":
          sendResponse(await handleSearchAndNavigate(msg.query, msg.target_url));
          break;
        case "click_show_more":
          sendResponse(await handleClickShowMore());
          break;
        case "extract_data":
          sendResponse(await handleExtractData());
          break;
        default:
          sendResponse({ type: "error", message: `Unknown content command: ${msg.type}` });
      }
    } catch (err) {
      sendResponse({ type: "error", message: err.message });
    }
  })();
  return true; // keep message channel open for async response
});

// --- CAPTCHA Handling ---

/**
 * Check if the page has a PerimeterX captcha.
 */
async function handleCheckCaptcha() {
  const wrapper = document.getElementById("px-captcha-wrapper");
  return {
    type: "check_captcha_done",
    has_captcha: !!wrapper,
  };
}

/**
 * Generate a random number between min and max (inclusive).
 */
function randBetween(min, max) {
  return Math.random() * (max - min) + min;
}

/**
 * Simulate human-like mouse movement from a random starting position
 * to a random point within the target element's bounds.
 * Uses bezier-curved path with slight jitter for realism.
 */
async function simulateMouseMove(target) {
  const rect = target.getBoundingClientRect();

  // Random start position somewhere on the visible viewport
  const startX = randBetween(0, window.innerWidth);
  const startY = randBetween(0, window.innerHeight);

  // Random end position anywhere within the target div (not just center)
  const endX = randBetween(rect.left + 10, rect.right - 10);
  const endY = randBetween(rect.top + 5, rect.bottom - 5);

  // Bezier control points for a curved, human-like path
  const cp1x = startX + (endX - startX) * randBetween(0.2, 0.4) + randBetween(-50, 50);
  const cp1y = startY + (endY - startY) * randBetween(0.1, 0.3) + randBetween(-50, 50);
  const cp2x = startX + (endX - startX) * randBetween(0.6, 0.8) + randBetween(-30, 30);
  const cp2y = startY + (endY - startY) * randBetween(0.7, 0.9) + randBetween(-30, 30);

  // Number of steps — humans aren't perfectly smooth
  const steps = Math.floor(randBetween(40, 80));

  for (let i = 0; i <= steps; i++) {
    const t = i / steps;

    // Cubic bezier interpolation
    const u = 1 - t;
    const x = u * u * u * startX + 3 * u * u * t * cp1x + 3 * u * t * t * cp2x + t * t * t * endX;
    const y = u * u * u * startY + 3 * u * u * t * cp1y + 3 * u * t * t * cp2y + t * t * t * endY;

    // Add tiny jitter to mimic hand tremor
    const jitterX = x + randBetween(-1.5, 1.5);
    const jitterY = y + randBetween(-1.5, 1.5);

    const moveOpts = {
      bubbles: true,
      cancelable: true,
      view: window,
      clientX: jitterX,
      clientY: jitterY,
    };

    document.elementFromPoint(jitterX, jitterY)
      ?.dispatchEvent(new MouseEvent("mousemove", moveOpts));

    // Variable delay — humans move faster in the middle, slower at start/end
    const speedFactor = 1 - 4 * (t - 0.5) * (t - 0.5); // parabola peaking at t=0.5
    const delay = randBetween(5, 15) + (1 - speedFactor) * randBetween(5, 20);
    await sleep(delay);
  }

  // Return the final position (where we'll click)
  return { x: endX, y: endY };
}

/**
 * Solve the "Press & Hold" captcha with human-like mouse movement.
 * 1. Moves cursor naturally from a random point to the captcha button
 * 2. Pauses briefly (like a human aiming)
 * 3. Presses and holds until the UI changes
 */
async function handleSolveCaptcha() {
  const wrapper = document.getElementById("px-captcha-wrapper");
  if (!wrapper) {
    return { type: "solve_captcha_done", success: false, reason: "No captcha found" };
  }

  // Find the pressable element
  const target = wrapper.querySelector("[id='px-captcha']") || wrapper;

  // Scroll it into view smoothly
  target.scrollIntoView({ behavior: "smooth", block: "center" });
  await sleep(randBetween(600, 1200));

  // Simulate human mouse movement toward the target
  const { x, y } = await simulateMouseMove(target);

  // Small pause after arriving — human "aiming" hesitation
  await sleep(randBetween(150, 400));

  const eventOpts = {
    bubbles: true,
    cancelable: true,
    view: window,
    clientX: x,
    clientY: y,
    button: 0,
  };

  // Dispatch mousedown to begin the press-and-hold
  target.dispatchEvent(new MouseEvent("mousedown", eventOpts));
  target.dispatchEvent(new PointerEvent("pointerdown", { ...eventOpts, pointerId: 1 }));

  // Poll until the captcha resolves or we timeout (max 30 seconds)
  const maxWait = 30000;
  const pollInterval = 300;
  let elapsed = 0;
  let solved = false;

  while (elapsed < maxWait) {
    await sleep(pollInterval);
    elapsed += pollInterval;

    // Check if captcha wrapper disappeared (page redirected / captcha removed)
    if (!document.getElementById("px-captcha-wrapper")) {
      solved = true;
      break;
    }

    // Check if inner content changed from "Press & Hold" to something else
    // (tick mark, loader, or empty — all indicate progress)
    const currentText = (target.textContent || "").trim().toLowerCase();
    if (currentText !== "" && !currentText.includes("press") && !currentText.includes("hold")) {
      // Content changed — likely showing tick/loader, keep holding a bit more
      await sleep(3000);
      solved = true;
      break;
    }

    // Also check if "Press & Hold" text is gone entirely (replaced by SVG/icon)
    if (currentText === "" && elapsed > 2000) {
      await sleep(3000);
      solved = true;
      break;
    }
  }

  // Small human-like delay before releasing
  await sleep(randBetween(80, 250));

  // Release the mouse
  target.dispatchEvent(new MouseEvent("mouseup", eventOpts));
  target.dispatchEvent(new PointerEvent("pointerup", { ...eventOpts, pointerId: 1 }));

  // Wait for any page reload/redirect after captcha solve
  if (solved) {
    await sleep(randBetween(2000, 4000));
  }

  return {
    type: "solve_captcha_done",
    success: solved,
    elapsed,
    reason: solved ? "Captcha resolved" : "Timeout — captcha did not clear",
  };
}

// --- Search & Navigate ---

/**
 * Type a building name into the StreetEasy search box, submit,
 * then find and click the matching result from the dropdown/results.
 * Mimics human typing with variable delays between keystrokes.
 */
async function handleSearchAndNavigate(query, targetUrl) {
  if (!query) {
    return { type: "search_and_navigate_done", success: false, reason: "No query provided" };
  }

  // 1. Find the search input
  const searchInput = document.getElementById("search_nav-0");
  if (!searchInput) {
    return { type: "search_and_navigate_done", success: false, reason: "Search input not found" };
  }

  // Scroll to top where the search bar lives
  window.scrollTo({ top: 0, behavior: "smooth" });
  await sleep(randBetween(400, 800));

  // 2. Click/focus the search input
  searchInput.focus();
  searchInput.click();
  await sleep(randBetween(200, 500));

  // Clear any existing text
  searchInput.value = "";
  searchInput.dispatchEvent(new Event("input", { bubbles: true }));
  await sleep(randBetween(200, 400));

  // 3. Type the query character by character (human-like)
  for (let i = 0; i < query.length; i++) {
    const char = query[i];

    searchInput.value += char;
    searchInput.dispatchEvent(new Event("input", { bubbles: true }));
    searchInput.dispatchEvent(new KeyboardEvent("keydown", { key: char, bubbles: true }));
    searchInput.dispatchEvent(new KeyboardEvent("keyup", { key: char, bubbles: true }));

    // Variable typing speed — faster for middle chars, slower at start
    await sleep(randBetween(50, 180));
  }

  // 4. Wait for the search suggestions/results to appear
  await sleep(randBetween(1500, 2500));

  // 5. Look for the target URL in the search results
  // Search results are typically <a> tags in a dropdown/list
  const allLinks = document.querySelectorAll("a[href]");
  let matchedLink = null;

  // Normalize the target URL for comparison (strip trailing slashes, protocol)
  const normalizeUrl = (url) =>
    url.replace(/^https?:\/\//, "").replace(/\/+$/, "").toLowerCase();

  const normalizedTarget = normalizeUrl(targetUrl);

  for (const link of allLinks) {
    const href = normalizeUrl(link.href);
    // Match if the link contains the target path
    if (href === normalizedTarget || href.includes(normalizedTarget) || normalizedTarget.includes(href)) {
      matchedLink = link;
      break;
    }
  }

  // If no exact match, try partial match on the building name portion of the URL
  if (!matchedLink) {
    // Extract building slug from target URL (e.g., "the-brook" from ".../building/the-brook")
    const slugMatch = targetUrl.match(/\/building\/([^/?#]+)/);
    if (slugMatch) {
      const slug = slugMatch[1].toLowerCase();
      for (const link of allLinks) {
        if (link.href.toLowerCase().includes(slug)) {
          matchedLink = link;
          break;
        }
      }
    }
  }

  if (!matchedLink) {
    // Fallback: press Enter to trigger a full search, then look again
    searchInput.dispatchEvent(
      new KeyboardEvent("keydown", { key: "Enter", code: "Enter", keyCode: 13, bubbles: true })
    );
    await sleep(randBetween(3000, 5000));

    // Re-scan after full page search results load
    const retryLinks = document.querySelectorAll("a[href]");
    for (const link of retryLinks) {
      const href = normalizeUrl(link.href);
      if (href === normalizedTarget || normalizedTarget.includes(href) || href.includes(normalizedTarget)) {
        matchedLink = link;
        break;
      }
    }
  }

  if (!matchedLink) {
    return {
      type: "search_and_navigate_done",
      success: false,
      reason: `No matching result found for "${query}"`,
    };
  }

  // 6. Return the URL — don't click it.
  // Clicking would navigate the page and kill this content script mid-response.
  // The background script will handle the actual navigation.
  return {
    type: "search_and_navigate_done",
    success: true,
    matched_url: matchedLink.href,
  };
}

// --- Show More & Data Extraction ---

/**
 * Find and click "Show X more" buttons.
 * Returns how many buttons were clicked and if more remain.
 */
async function handleClickShowMore() {
  let totalClicked = 0;
  let hasMore = true;
  let captchaDetected = false;

  while (hasMore) {
    hasMore = false;

    // Check for captcha before each click attempt
    if (document.getElementById("px-captcha-wrapper")) {
      captchaDetected = true;
      break;
    }

    const buttons = document.querySelectorAll("button");

    for (const btn of buttons) {
      const text = btn.textContent.trim();

      if (/Show\s+\d+\s+more/i.test(text)) {
        btn.scrollIntoView({ behavior: "smooth", block: "center" });
        await sleep(500);
        btn.click();
        totalClicked++;
        hasMore = true;
        await sleep(2000);

        // Check for captcha after each click
        if (document.getElementById("px-captcha-wrapper")) {
          captchaDetected = true;
          hasMore = false;
        }

        break;
      }
    }
  }

  return {
    type: "click_show_more_done",
    clicked: totalClicked,
    captcha_detected: captchaDetected,
  };
}

/**
 * Extract all property data from InventoryCard components on the page.
 */
async function handleExtractData() {
  const cards = document.querySelectorAll('[data-testid="inventory-card-component"]');
  const properties = [];

  for (const card of cards) {
    const prop = extractCardData(card);
    if (prop) properties.push(prop);
  }

  return {
    type: "extract_data_done",
    count: properties.length,
    properties,
  };
}

/**
 * Extract data from a single InventoryCard element.
 */
function extractCardData(card) {
  const data = {};

  // 1. Property Name + listing URL
  const unitLink = card.querySelector("a[class*='InventoryCard_unit']");
  data.property_name = unitLink ? unitLink.textContent.trim() : "";
  data.listing_url = unitLink ? unitLink.href : "";

  // 2. Rent
  const priceEl = card.querySelector("p[class*='InventoryCard_price']");
  data.rent = priceEl ? priceEl.textContent.trim() : "";

  // 3. Beds, Baths, Area - from listing description icons
  data.beds = "";
  data.baths = "";
  data.area = "";

  const iconsSection = card.querySelector('[data-testid="listing-description-icons"]');
  if (iconsSection) {
    const items = iconsSection.querySelectorAll("div[class*='ListingDescriptionIcons_iconItem']");
    for (const item of items) {
      const svg = item.querySelector("svg");
      const textEl = item.querySelector("p");
      if (!svg || !textEl) continue;

      const testId = svg.getAttribute("data-testid") || "";
      const text = textEl.textContent.trim();

      if (testId === "bed-icon") data.beds = text;
      else if (testId === "bath-icon") data.baths = text;
      else if (testId === "ft-icon") data.area = text;
    }
  }

  // 4. Listed By
  const listedByEl = card.querySelector('[data-testid="sg-label"]');
  if (listedByEl) {
    data.listed_by = listedByEl.textContent.trim().replace(/^Listing by\s*/i, "");
  } else {
    data.listed_by = "";
  }

  // 5. Availability
  const availEl = card.querySelector('[data-testid="listingLabel-availability"]');
  data.availability = availEl ? availEl.textContent.trim() : "";

  // 6. Specials
  const specialEls = card.querySelectorAll("div[class*='InventoryCard_cardListContainer'] li p");
  if (specialEls.length > 0) {
    data.specials = Array.from(specialEls).map((p) => p.textContent.trim()).join("; ");
  } else {
    data.specials = "";
  }

  return data;
}

function sleep(ms) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}
