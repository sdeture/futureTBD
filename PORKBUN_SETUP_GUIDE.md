# Porkbun Setup Guide for futuretbd.ai

## Step-by-Step Instructions with Pictures of What to Click

### 🔵 Step 1: Log into Porkbun
1. Go to https://porkbun.com
2. Click "SIGN IN" in the top right corner
3. Enter your username and password

### 🔵 Step 2: Find Your Domain
1. After logging in, you'll see your dashboard
2. Look for **futuretbd.ai** in your domain list
3. Click the **DNS** button next to it (it might say "DNS" or "Manage" or have a gear icon)

### 🔵 Step 3: You're Now on the DNS Records Page
This page might look intimidating but we're just going to add a few lines. Think of it like a phone book - we're telling the internet where to find your website.

### 🔵 Step 4: Delete Any Existing A Records (if any)
- If you see any records with Type "A" that have just "futuretbd.ai" as the host, delete them
- Click the trash can icon next to them
- This is just cleaning up before we add the correct ones

### 🔵 Step 5: Add the First A Record
Look for a section that says "Add a new record" or "Quick DNS Config" or just empty fields. You'll see boxes labeled something like:

1. **Type**: Select **A** from the dropdown menu
2. **Host**: Leave this **completely empty** (or it might show futuretbd.ai - that's fine)
3. **Answer/Value/Points to**: Type `185.199.108.153`
4. **TTL**: Leave as default (probably 600 or 3600)
5. Click **Add** or **Save**

### 🔵 Step 6: Add Three More A Records
Repeat Step 5 three more times with these IP addresses:
- `185.199.109.153`
- `185.199.110.153`  
- `185.199.111.153`

So you'll have 4 total A records, all with:
- Type: A
- Host: (empty)
- One of the four IP addresses above

### 🔵 Step 7: Add the WWW Record
Now let's make www.futuretbd.ai work too:

1. **Type**: Select **CNAME** from the dropdown
2. **Host**: Type `www` (just those three letters)
3. **Answer/Value/Points to**: Type `sdeture.github.io`
4. **TTL**: Leave as default
5. Click **Add** or **Save**

### 🔵 Step 8: Your DNS Records Should Now Look Like This:

```
Type    Host              Answer/Value
----    ----              ------------
A       futuretbd.ai      185.199.108.153
A       futuretbd.ai      185.199.109.153
A       futuretbd.ai      185.199.110.153
A       futuretbd.ai      185.199.111.153
CNAME   www.futuretbd.ai  sdeture.github.io
```

(Plus maybe some other records for email - those are fine to leave)

### 🔵 Step 9: Save Everything
- Look for a big "SAVE" or "UPDATE" button
- Click it!
- You might see a success message

### 🎉 Step 10: You're Done with Porkbun!

## Now Check GitHub:

1. Go to https://github.com/sdeture/futureTBD/settings/pages
2. You should see a box that says "Custom domain"
3. It should already show `futuretbd.ai` (we added this earlier)
4. If there's a checkbox for "Enforce HTTPS", check it (might take 10 minutes to appear)

## Testing Your New Domain:

The DNS changes need time to spread across the internet (like news traveling):
- **Quick check** (5-10 minutes): Try visiting http://futuretbd.ai
- **SSL certificate** (up to 1 hour): GitHub needs time to set up https://
- **Full propagation** (up to 24 hours): For everyone worldwide to see it

You can check progress here: https://www.whatsmydns.net/#A/futuretbd.ai
- Type your domain and click search
- Green checkmarks = it's working in that location!

## 🚨 Common Porkbun Interface Variations:

Porkbun sometimes updates their interface. If you see:
- **"DNS Records"** instead of just "DNS" - click that
- **"Quick DNS Config"** - you can use that for the A records
- **"Type/Host/Answer/TTL/Priority"** - Priority can be left empty
- **A "Parking" page** - Delete any records pointing to Porkbun's parking page

## If Something Goes Wrong:

1. **Double-check the IP addresses** - they must be exactly:
   - 185.199.108.153
   - 185.199.109.153
   - 185.199.110.153
   - 185.199.111.153

2. **Make sure the Host field for A records is empty** (or shows your domain)

3. **The www CNAME must point to**: sdeture.github.io (not github.com)

4. **Wait a bit longer** - DNS can be slow sometimes

## Need More Help?

- Porkbun has great support - they can help with the DNS setup
- The magic words: "I need to point my domain to GitHub Pages with these A records"
- Or let me know what you're seeing and I can help troubleshoot!

---

Remember: You're not breaking anything! DNS records can always be changed if needed. The worst that happens is the domain doesn't work for a bit while we fix it. 

You've got this! 🎉