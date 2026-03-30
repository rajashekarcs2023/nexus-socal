# ASI:One — Luma Checkout Integration

## Summary

We need ASI:One to support **Luma event registration** alongside the existing Eventbrite integration. When an agent returns a booking action with a Luma URL, ASI:One should open Luma's checkout modal — which handles registration questions, payment (if applicable), and confirmation automatically.

**This does NOT affect existing Eventbrite functionality.** It's a new code path triggered by a different field (`luma_url` vs `event_id`).

---

## What Luma Provides

Luma has an official embeddable checkout widget, similar to Eventbrite's:
- **Script:** `https://embed.lu.ma/checkout-button.js`
- **Behavior:** Intercepts clicks on elements with `data-luma-action="checkout"` and opens a registration overlay (modal)
- **Includes:** Name, email, and all custom registration questions configured on the event
- **Docs:** https://help.luma.com/p/embed-our-checkout-registration-button-on-your-website
- **Live demo:** https://luma-embed-examples.vercel.app/

---

## Implementation Steps

### Step 1: Add the Luma checkout script

Add this script tag to the ASI:One page (once, globally):

```html
<script id="luma-checkout" src="https://embed.lu.ma/checkout-button.js"></script>
```

This is lightweight and only activates when it detects Luma checkout elements on the page.

### Step 2: Update the booking action handler

Currently, ASI:One detects agent booking responses like:

```json
{"action": "Click Here to book", "event_id": "1985241779604"}
```

and opens an Eventbrite checkout modal using the numeric `event_id`.

**For Luma**, agents will return:

```json
{"action": "Click Here to book", "luma_url": "https://luma.com/dj0aohkq"}
```

The detection logic should be:

```javascript
const payload = JSON.parse(agentMessage);

if (payload.action && payload.luma_url) {
  // NEW: Luma checkout
  renderLumaCheckoutButton(payload.luma_url);
} else if (payload.action && payload.event_id) {
  // EXISTING: Eventbrite modal (unchanged)
  renderEventbriteModal(payload.event_id);
}
```

### Step 3: Render the Luma checkout button

When `luma_url` is detected, dynamically create a Luma checkout element:

```javascript
function renderLumaCheckoutButton(lumaUrl) {
  const button = document.createElement('a');
  button.href = lumaUrl;
  button.className = 'luma-checkout--button';
  button.setAttribute('data-luma-action', 'checkout');
  button.textContent = 'Register';

  // Append to the chat message area
  chatMessageContainer.appendChild(button);

  // Re-initialize Luma's script to pick up the new element
  // Option A: The script auto-detects new elements via MutationObserver
  // Option B: If needed, reload the script:
  //   const script = document.createElement('script');
  //   script.src = 'https://embed.lu.ma/checkout-button.js';
  //   document.body.appendChild(script);
}
```

**Note:** The Luma script may need to be re-initialized after dynamically adding elements. Test whether it auto-detects new elements. If not, re-appending the script tag will re-scan the DOM.

---

## Backward Compatibility

| Agent sends | Field present | ASI:One behavior | Status |
|---|---|---|---|
| `{"action": "...", "event_id": "123456"}` | `event_id` (numeric) | Opens Eventbrite modal | **Unchanged** |
| `{"action": "...", "luma_url": "https://luma.com/..."}` | `luma_url` | Opens Luma modal | **New** |

- Existing Eventbrite agents do NOT send `luma_url` → Eventbrite path is never affected
- New Luma agents do NOT send a numeric `event_id` → no conflict
- **100% backward compatible**

---

## What the Luma Modal Handles Automatically

Once the modal opens, Luma handles everything:
- Displays Name + Email fields
- Displays all custom registration questions (text, dropdown, LinkedIn, etc.)
- Handles validation (required fields)
- Processes registration
- Sends confirmation email + calendar invite to the guest
- Sends QR code for check-in (for in-person events)

**No additional frontend work needed per event.** The modal dynamically loads the registration form for whatever event URL is provided.

---

## Testing

A working demo page is available in the repo:

```
nexus-socal/luma-demo.html
```

Open it locally to see two Luma checkout buttons in action. Click either button to see the Luma registration modal with registration questions.

To test manually, paste this into any HTML page:

```html
<a href="https://luma.com/dj0aohkq"
   class="luma-checkout--button"
   data-luma-action="checkout">
  Register
</a>
<script id="luma-checkout" src="https://embed.lu.ma/checkout-button.js"></script>
```

---

## Questions?

- **Luma embed docs:** https://help.luma.com/p/embed-our-checkout-registration-button-on-your-website
- **Luma API docs:** https://docs.luma.com
- **Demo repo:** https://github.com/luma-dev/embed-examples
