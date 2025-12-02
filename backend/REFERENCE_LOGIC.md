# Product Reference Logic: Previous Results vs Tagged Products

## Decision Flow

The backend uses a **priority-based check system** to determine whether to use `last_displayed_products` (previous results) or `tagged_products` (explicitly tagged products).

### Priority 1: Filter Previous Results (Lines 202-271)

**Triggered when:**
- Query contains **"these"**, **"those"**, or **"them"** OR contains **"which"**/**"what"**
- **AND** query has a filter pattern (negative filter like "do not have" OR contains "have")
- **AND** `last_displayed_products` is provided and non-empty

**Examples:**
- ✅ "which of these do not have buttons"
- ✅ "which of those have buttons"
- ✅ "what of these don't have patterns"
- ❌ "show me more like this" (no "which"/"these"/"those", goes to Priority 2)

**Action:** Filters the `last_displayed_products` array based on feature keywords (buttons, patterns, hoods, etc.) and returns filtered results.

---

### Priority 2: Use Tagged Products (Lines 273-289)

**Triggered when:**
- Query contains **"this"**, **"that"**, **"it"**, **"this one"**, **"that one"** OR
- Query contains **"more like"**, **"similar"**, **"like this"**, **"like that"**, **"same style"** OR
- Query contains **"accessories"**, **"accessory"**, **"wear with"**, **"goes with"**, **"pair with"**, **"match with"**
- **AND** `tagged_products` is provided and non-empty

**Examples:**
- ✅ "show me more like this" (if product is tagged)
- ✅ "show me accessories to wear with this" (if product is tagged)
- ✅ "find similar items" (if product is tagged)
- ❌ "show me more like this" (if no tagged products, falls through to regular search)

**Action:** Uses the first tagged product (`tagged_products[0]`) as a reference for:
- Similar product search (semantic similarity)
- Accessories search (complementary items)
- Style-based filtering

---

## Frontend Logic (extension/sidepanel.js)

The frontend determines what to send:

### Tagged Products (`tagged_products`)
Sent when query contains:
- Pronouns: "this", "that", "it", "this one", "that one"
- Similar patterns: "more like", "similar", "like this", "like that"

**Priority:**
1. If user clicked '@' button → use `taggedProducts` array
2. Otherwise → use last displayed product (most recent)

### Last Displayed Products (`last_displayed_products`)
**Always sent** with every query (contains all products from the last search result).

---

## Edge Cases & Ambiguity

### Case 1: "which of these" with tagged product
- **Current behavior:** Uses `last_displayed_products` (Priority 1 wins)
- **Reason:** "which of these" explicitly references the previous results list

### Case 2: "show me more like this" with no tagged product
- **Current behavior:** Falls through to regular search
- **Reason:** Tagged products check requires `tagged_products` to be non-empty

### Case 3: "which of these" without filter
- **Current behavior:** Falls through to Priority 2 or regular search
- **Reason:** Requires filter pattern ("have", "do not have", etc.)

---

## Summary Table

| Query Pattern | Uses | Condition |
|--------------|------|-----------|
| "which of these do not have X" | `last_displayed_products` | Must have filter + last_displayed_products |
| "which of those have X" | `last_displayed_products` | Must have filter + last_displayed_products |
| "show me more like this" | `tagged_products` | Must have tagged_products |
| "show me accessories to wear with this" | `tagged_products` | Must have tagged_products |
| "show me similar items" | `tagged_products` | Must have tagged_products |
| "show me black sweaters" | Neither | Regular search |

---

## Code Locations

- **Backend Priority 1:** `backend/app.py` lines 202-271
- **Backend Priority 2:** `backend/app.py` lines 273-289
- **Frontend tagged products:** `extension/sidepanel.js` lines 53-79
- **Frontend last displayed:** `extension/sidepanel.js` lines 135-141, 97

